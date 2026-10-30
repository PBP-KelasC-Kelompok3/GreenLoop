from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.db import transaction
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from scheduling.models import PickupSchedule

from .models import RewardTransaction, RewardVoucher, UserVoucher
from .services import (
    InsufficientPoints,
    VoucherUnavailable,
    apply_voucher_at_checkout,
    award_verified_pickup,
    get_balance,
    redeem_voucher,
)
from .points import membership_tier, points_for_weight


User = get_user_model()


class WasteRewardTestCase(TestCase):
    def make_user(self, username, role='mitra'):
        user = User.objects.create_user(username=username, password='test-password')
        user.userprofile.role = role
        user.userprofile.save(update_fields=('role',))
        return user

    def make_voucher(
        self,
        *,
        code=None,
        title='Voucher tes',
        kind=RewardVoucher.Kind.DISCOUNT,
        value_label='Rp 10.000',
        points_cost=200,
        valid_days=30,
        is_active=True,
    ):
        code = code or f'diskon-test-{uuid4().hex[:10]}'
        return RewardVoucher.objects.create(
            code=code,
            title=title,
            kind=kind,
            value_label=value_label,
            points_cost=points_cost,
            valid_days=valid_days,
            is_active=is_active,
        )

    def add_points(self, user, points, reference='pickup-test', description='Setoran tes'):
        return RewardTransaction.objects.create(
            user=user,
            kind=RewardTransaction.Kind.PICKUP,
            points_delta=points,
            balance_after=points,
            weight_kg=Decimal('1.0'),
            description=description,
            source_reference=reference,
        )

    def make_owned_voucher(self, user, voucher, *, expires_at=None, code='GLV-TESTCODE'):
        return UserVoucher.objects.create(
            user=user,
            voucher=voucher,
            code=code,
            points_spent=voucher.points_cost,
            expires_at=expires_at or timezone.now() + timedelta(days=30),
        )


class MembershipTierTests(WasteRewardTestCase):
    def test_membership_thresholds_are_consistent(self):
        for points, expected in (
            (0, 'Bronze'), (999, 'Bronze'), (1000, 'Silver'),
            (2999, 'Silver'), (3000, 'Gold'), (4999, 'Gold'),
            (5000, 'Platinum'), (9000, 'Platinum'),
        ):
            with self.subTest(points=points):
                self.assertEqual(membership_tier(points), expected)

    def test_weight_conversion_floors_to_tenths_and_whole_points(self):
        self.assertEqual(points_for_weight('0.1'), 0)
        self.assertEqual(points_for_weight('1.29'), 6)


class PickupRewardSignalTests(WasteRewardTestCase):
    def make_pickup(self, mitra, *, status='COMPLETED', actual_weight='3.2'):
        return PickupSchedule.objects.create(
            mitra=mitra,
            estimated_weight=3.2,
            pickup_date=timezone.localdate(),
            pickup_time_slot='09:00 - 12:00',
            status=status,
            actual_weight=actual_weight,
        )

    def test_completed_weighed_pickup_awards_once_and_syncs_history_points(self):
        mitra = self.make_user('mitra-signal-complete')

        pickup = self.make_pickup(mitra)
        pickup.notes = 'Disimpan ulang setelah verifikasi'
        pickup.save(update_fields=('notes',))

        self.assertEqual(pickup.points, 16)
        self.assertEqual(get_balance(mitra), 16)
        self.assertEqual(
            RewardTransaction.objects.filter(
                source_reference=f'scheduling.pickupschedule:{pickup.pk}'
            ).count(),
            1,
        )

    def test_incomplete_or_unweighed_pickup_does_not_award_points(self):
        mitra = self.make_user('mitra-signal-pending')
        pending = self.make_pickup(mitra, status='IN_PROGRESS')
        unweighed = self.make_pickup(mitra, actual_weight=None)

        self.assertEqual(pending.points, 0)
        self.assertEqual(unweighed.points, 0)
        self.assertEqual(get_balance(mitra), 0)

    def test_signal_connection_is_optional_when_pickup_app_is_unavailable(self):
        from .signals import connect_pickup_signals

        with patch('waste_reward.signals.apps.get_model', side_effect=LookupError):
            connect_pickup_signals()


class PointServiceTests(WasteRewardTestCase):
    def test_verified_pickup_awards_five_points_per_kilogram(self):
        mitra = self.make_user('mitra-points')

        entry = award_verified_pickup(mitra, '35.29', 'PK-001')

        self.assertEqual(entry.weight_kg, Decimal('35.2'))
        self.assertEqual(entry.points_delta, 176)
        self.assertEqual(entry.balance_after, 176)
        self.assertEqual(get_balance(mitra), 176)

    def test_small_positive_pickup_is_recorded_when_rounding_yields_zero_points(self):
        mitra = self.make_user('mitra-small-pickup')

        entry = award_verified_pickup(mitra, '0.01', 'PK-SMALL')

        self.assertEqual(entry.weight_kg, Decimal('0.0'))
        self.assertEqual(entry.points_delta, 0)
        self.assertEqual(get_balance(mitra), 0)

    def test_retry_for_same_pickup_does_not_award_points_twice(self):
        mitra = self.make_user('mitra-retry')

        first = award_verified_pickup(mitra, '10', 'PK-RETRY')
        retry = award_verified_pickup(mitra, '99', 'PK-RETRY')

        self.assertEqual(retry.pk, first.pk)
        self.assertEqual(RewardTransaction.objects.filter(user=mitra).count(), 1)
        self.assertEqual(get_balance(mitra), 50)

    def test_pickup_reference_cannot_be_reused_by_another_mitra(self):
        first_mitra = self.make_user('mitra-first')
        second_mitra = self.make_user('mitra-second')
        award_verified_pickup(first_mitra, '2', 'PK-SHARED')

        with self.assertRaisesMessage(ValueError, 'sudah digunakan'):
            award_verified_pickup(second_mitra, '2', 'PK-SHARED')

    def test_invalid_weight_and_missing_reference_are_rejected(self):
        mitra = self.make_user('mitra-invalid')

        for weight in ('0', '-1', 'not-a-weight'):
            with self.subTest(weight=weight), self.assertRaises(ValueError):
                award_verified_pickup(mitra, weight, 'PK-INVALID')

        with self.assertRaisesMessage(ValueError, 'Referensi'):
            award_verified_pickup(mitra, '1', '')

    def test_non_mitra_cannot_receive_or_redeem_reward_points(self):
        consumer = self.make_user('consumer-reward', role='consumer')
        voucher = self.make_voucher()

        with self.assertRaises(PermissionDenied):
            award_verified_pickup(consumer, '1', 'PK-CONSUMER')
        with self.assertRaises(PermissionDenied):
            redeem_voucher(consumer, voucher.pk)

    def test_user_without_role_profile_cannot_receive_points(self):
        user = self.make_user('mitra-without-reward-profile')
        user.userprofile.delete()
        user._state.fields_cache.pop('userprofile', None)
        with self.assertRaises(PermissionDenied):
            award_verified_pickup(user, '1', 'PK-NO-PROFILE')


class VoucherRedemptionTests(WasteRewardTestCase):
    def test_redeeming_voucher_debits_points_and_creates_owned_voucher(self):
        mitra = self.make_user('mitra-redeem')
        voucher = self.make_voucher(points_cost=200)
        self.add_points(mitra, 500, 'PK-REDEEM')

        owned = redeem_voucher(mitra, voucher.pk)

        self.assertEqual(owned.user, mitra)
        self.assertEqual(owned.voucher, voucher)
        self.assertEqual(len(owned.code), 16)
        self.assertEqual(get_balance(mitra), 300)
        transaction_entry = RewardTransaction.objects.get(
            user=mitra,
            kind=RewardTransaction.Kind.REDEMPTION,
        )
        self.assertEqual(transaction_entry.points_delta, -200)
        self.assertEqual(transaction_entry.balance_after, 300)

    def test_insufficient_points_do_not_create_voucher_or_debit(self):
        mitra = self.make_user('mitra-low-balance')
        voucher = self.make_voucher(points_cost=200)
        self.add_points(mitra, 100, 'PK-LOW')

        with self.assertRaises(InsufficientPoints):
            redeem_voucher(mitra, voucher.pk)

        self.assertFalse(UserVoucher.objects.filter(user=mitra).exists())
        self.assertEqual(get_balance(mitra), 100)

    def test_inactive_or_missing_catalog_voucher_cannot_be_redeemed(self):
        mitra = self.make_user('mitra-inactive')
        inactive = self.make_voucher(code='inactive', is_active=False)
        self.add_points(mitra, 1000, 'PK-INACTIVE')

        with self.assertRaises(VoucherUnavailable):
            redeem_voucher(mitra, inactive.pk)
        with self.assertRaises(VoucherUnavailable):
            redeem_voucher(mitra, 99999)

    def test_owned_voucher_availability_tracks_expiration_and_use(self):
        mitra = self.make_user('mitra-voucher-availability')
        voucher = self.make_voucher()
        available = self.make_owned_voucher(mitra, voucher)
        expired = self.make_owned_voucher(
            mitra,
            voucher,
            expires_at=timezone.now() - timedelta(seconds=1),
            code='GLV-EXPIRED-PROP',
        )
        used = self.make_owned_voucher(mitra, voucher, code='GLV-USED-PROP')
        used.used_at = timezone.now()
        used.save(update_fields=('used_at',))

        self.assertTrue(available.is_available)
        self.assertFalse(expired.is_available)
        self.assertFalse(used.is_available)


class CheckoutVoucherTests(WasteRewardTestCase):
    def test_fixed_discount_is_capped_at_subtotal_and_consumes_voucher(self):
        mitra = self.make_user('mitra-checkout-fixed')
        voucher = self.make_voucher()
        owned = self.make_owned_voucher(mitra, voucher)

        result = apply_voucher_at_checkout(
            mitra, owned.code, 'ORDER-FIXED', subtotal='8000', shipping_cost='2000'
        )

        self.assertEqual(result['goods_discount'], Decimal('8000'))
        self.assertEqual(result['shipping_discount'], Decimal('0'))
        self.assertEqual(result['total_due'], Decimal('2000'))
        owned.refresh_from_db()
        self.assertIsNotNone(owned.used_at)
        self.assertEqual(owned.used_order_reference, 'ORDER-FIXED')

    def test_shipping_discount_is_capped_at_shipping_cost(self):
        mitra = self.make_user('mitra-checkout-shipping')
        voucher = self.make_voucher(
            code='gratis-ongkir-test',
            kind=RewardVoucher.Kind.SHIPPING,
            value_label='s.d. Rp 15.000',
        )
        owned = self.make_owned_voucher(mitra, voucher, code='GLV-SHIPTEST')

        result = apply_voucher_at_checkout(
            mitra, owned.code, 'ORDER-SHIP', subtotal='50000', shipping_cost='8000'
        )

        self.assertEqual(result['shipping_discount'], Decimal('8000'))
        self.assertEqual(result['total_due'], Decimal('50000'))

    def test_wholesale_discount_requires_wholesale_order(self):
        mitra = self.make_user('mitra-checkout-wholesale')
        voucher = self.make_voucher(
            code='diskon-grosir-test',
            kind=RewardVoucher.Kind.WHOLESALE,
            value_label='15%',
        )
        owned = self.make_owned_voucher(mitra, voucher, code='GLV-WHOLESALE')

        with self.assertRaisesMessage(VoucherUnavailable, 'grosir B2B'):
            apply_voucher_at_checkout(
                mitra, owned.code, 'ORDER-NOT-WHOLESALE', subtotal='1000000'
            )
        self.assertIsNone(owned.used_at)

        result = apply_voucher_at_checkout(
            mitra,
            owned.code,
            'ORDER-WHOLESALE',
            subtotal='1000001',
            wholesale_order=True,
        )
        self.assertEqual(result['goods_discount'], Decimal('150000'))
        self.assertEqual(result['total_due'], Decimal('850001'))

    def test_cannot_apply_another_voucher_to_same_order(self):
        mitra = self.make_user('mitra-one-voucher')
        first = self.make_owned_voucher(
            mitra,
            self.make_voucher(code='first-voucher'),
            code='GLV-FIRST',
        )
        second = self.make_owned_voucher(
            mitra,
            self.make_voucher(code='second-voucher'),
            code='GLV-SECOND',
        )
        apply_voucher_at_checkout(mitra, first.code, 'ORDER-ONE', subtotal='30000')

        with self.assertRaisesMessage(VoucherUnavailable, 'sudah menggunakan'):
            apply_voucher_at_checkout(mitra, second.code, 'ORDER-ONE', subtotal='30000')
        self.assertIsNone(second.used_at)

    def test_foreign_expired_used_and_non_mitra_vouchers_are_rejected(self):
        mitra = self.make_user('mitra-voucher-owner')
        other_mitra = self.make_user('mitra-voucher-other')
        consumer = self.make_user('consumer-voucher', role='consumer')
        voucher = self.make_voucher()
        foreign = self.make_owned_voucher(other_mitra, voucher, code='GLV-FOREIGN')
        expired = self.make_owned_voucher(
            mitra,
            voucher,
            expires_at=timezone.now() - timedelta(seconds=1),
            code='GLV-EXPIRED',
        )
        used = self.make_owned_voucher(mitra, voucher, code='GLV-USED')
        used.used_at = timezone.now()
        used.used_order_reference = 'ORDER-ALREADY-USED'
        used.save(update_fields=('used_at', 'used_order_reference'))
        available = self.make_owned_voucher(mitra, voucher, code='GLV-AVAILABLE')

        for user, code, order_ref in (
            (mitra, foreign.code, 'ORDER-FOREIGN'),
            (mitra, expired.code, 'ORDER-EXPIRED'),
            (mitra, used.code, 'ORDER-USED'),
        ):
            with self.subTest(code=code), self.assertRaises(VoucherUnavailable):
                apply_voucher_at_checkout(user, code, order_ref, subtotal='10000')

        with self.assertRaises(PermissionDenied):
            apply_voucher_at_checkout(
                consumer, available.code, 'ORDER-CONSUMER', subtotal='10000'
            )

    def test_invalid_checkout_amount_or_reference_is_rejected_without_consumption(self):
        mitra = self.make_user('mitra-invalid-checkout')
        voucher = self.make_voucher()
        owned = self.make_owned_voucher(mitra, voucher)

        for subtotal, order_reference in (
            ('-1', 'ORDER-NEGATIVE'),
            ('NaN', 'ORDER-NAN'),
            ('not-an-amount', 'ORDER-NOT-AMOUNT'),
            ('not-an-amount', 'ORDER-NOT-AMOUNT'),
            ('10000', ''),
            ('10000', 'x' * 81),
        ):
            with self.subTest(subtotal=subtotal, order_reference=order_reference):
                with self.assertRaises(ValueError):
                    apply_voucher_at_checkout(
                        mitra, owned.code, order_reference, subtotal=subtotal
                    )
        owned.refresh_from_db()
        self.assertIsNone(owned.used_at)

    def test_malformed_and_unknown_voucher_values_are_rejected(self):
        mitra = self.make_user('mitra-malformed-voucher')
        malformed_discount = self.make_voucher(
            code='bad-discount-label', value_label='Tidak terbaca'
        )
        malformed_wholesale = self.make_voucher(
            code='bad-wholesale-label',
            kind=RewardVoucher.Kind.WHOLESALE,
            value_label='Lima belas persen',
        )
        unknown_kind = self.make_voucher(code='unknown-kind', kind='other')
        discount = self.make_owned_voucher(mitra, malformed_discount, code='GLV-BAD-DISCOUNT')
        wholesale = self.make_owned_voucher(mitra, malformed_wholesale, code='GLV-BAD-WHOLESALE')
        unknown = self.make_owned_voucher(mitra, unknown_kind, code='GLV-UNKNOWN-KIND')

        with self.assertRaises(ValueError):
            apply_voucher_at_checkout(mitra, discount.code, 'ORDER-BAD-DISCOUNT', '10000')
        with self.assertRaises(ValueError):
            apply_voucher_at_checkout(
                mitra, wholesale.code, 'ORDER-BAD-WHOLESALE', '10000', wholesale_order=True
            )
        with self.assertRaises(VoucherUnavailable):
            apply_voucher_at_checkout(mitra, unknown.code, 'ORDER-UNKNOWN', '10000')

        for owned in (discount, wholesale, unknown):
            owned.refresh_from_db()
            self.assertIsNone(owned.used_at)

    def test_unique_order_race_is_translated_to_voucher_unavailable(self):
        mitra = self.make_user('mitra-unique-race')
        other_mitra = self.make_user('mitra-unique-race-other')
        voucher = self.make_voucher()
        owned = self.make_owned_voucher(mitra, voucher, code='GLV-RACE-OWNER')
        conflict = self.make_owned_voucher(
            other_mitra, voucher, code='GLV-RACE-CONFLICT'
        )
        conflict.used_at = timezone.now()
        conflict.used_order_reference = 'ORDER-RACE-CHECK'
        conflict.save(update_fields=('used_at', 'used_order_reference'))

        with patch.object(UserVoucher.objects, 'filter') as mocked_filter:
            mocked_filter.return_value.exists.return_value = False
            with self.assertRaisesMessage(VoucherUnavailable, 'sudah menggunakan'):
                apply_voucher_at_checkout(
                    mitra, owned.code, 'ORDER-RACE-CHECK', subtotal='10000'
                )

    def test_order_rollback_also_rolls_back_voucher_consumption(self):
        mitra = self.make_user('mitra-checkout-rollback')
        voucher = self.make_voucher()
        owned = self.make_owned_voucher(mitra, voucher)

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                apply_voucher_at_checkout(
                    mitra, owned.code, 'ORDER-ROLLBACK', subtotal='10000'
                )
                raise RuntimeError('Simulated order save failure')

        owned.refresh_from_db()
        self.assertIsNone(owned.used_at)
        self.assertIsNone(owned.used_order_reference)


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class WasteRewardViewAccessTests(WasteRewardTestCase):
    def test_dashboard_requires_mitra_role_and_returns_clear_forbidden(self):
        mitra = self.make_user('mitra-dashboard-access')
        consumer = self.make_user('consumer-dashboard-access', role='consumer')
        client = Client()

        client.force_login(mitra)
        mitra_response = client.get(reverse('waste_reward:dashboard'))
        self.assertEqual(mitra_response.status_code, 200)

        client.force_login(consumer)
        consumer_response = client.get(reverse('waste_reward:dashboard'))
        self.assertEqual(consumer_response.status_code, 403)

    def test_dashboard_denies_users_without_a_role_profile(self):
        user = self.make_user('mitra-profile-removed')
        user.userprofile.delete()
        user._state.fields_cache.pop('userprofile', None)
        client = Client()
        client.force_login(user)
        self.assertEqual(client.get(reverse('waste_reward:dashboard')).status_code, 403)

    def test_dashboard_renders_each_membership_tier(self):
        for points, expected in (
            (0, 'Bronze'), (1000, 'Silver'), (3000, 'Gold'), (5000, 'Platinum'),
        ):
            with self.subTest(points=points):
                user = self.make_user(f'mitra-tier-{points}')
                if points:
                    self.add_points(user, points, f'PK-TIER-{points}')
                client = Client()
                client.force_login(user)
                response = client.get(reverse('waste_reward:dashboard'))
                self.assertEqual(response.context['level'], expected)
                if expected == 'Platinum':
                    self.assertEqual(response.context['progress'], 100)

    def test_dashboard_searches_transactions_and_vouchers(self):
        mitra = self.make_user('mitra-dashboard-search')
        self.add_points(mitra, 50, 'PK-SEARCH', description='Setoran kopi terverifikasi')
        voucher = self.make_voucher(
            code='kopi-reward', title='Hadiah Kopi', value_label='Rp 5.000', points_cost=10
        )
        client = Client()
        client.force_login(mitra)

        transaction_match = client.get(reverse('waste_reward:dashboard'), {'q': 'kopi'})
        voucher_match = client.get(reverse('waste_reward:dashboard'), {'q': 'Hadiah Kopi'})

        self.assertEqual([item.pk for item in transaction_match.context['transactions']], [
            RewardTransaction.objects.get(source_reference='PK-SEARCH').pk
        ])
        self.assertEqual([item.pk for item in voucher_match.context['vouchers']], [voucher.pk])

    def test_dashboard_marks_owned_voucher_availability(self):
        mitra = self.make_user('mitra-dashboard-owned')
        voucher = self.make_voucher(code='dashboard-owned')
        self.make_owned_voucher(mitra, voucher, code='GLV-DASHBOARD-ACTIVE')
        self.make_owned_voucher(
            mitra, voucher,
            expires_at=timezone.now() - timedelta(days=1),
            code='GLV-DASHBOARD-EXPIRED',
        )
        client = Client()
        client.force_login(mitra)

        response = client.get(reverse('waste_reward:dashboard'))

        owned = response.context['owned_vouchers']
        self.assertEqual([item.available for item in owned], [False, True])
        self.assertEqual(response.context['available_voucher_count'], 1)

    def test_anonymous_dashboard_access_redirects_to_login(self):
        response = Client().get(reverse('waste_reward:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_redemption_endpoint_requires_post_and_mitra_role(self):
        mitra = self.make_user('mitra-redeem-access')
        consumer = self.make_user('consumer-redeem-access', role='consumer')
        voucher = self.make_voucher()
        client = Client()

        client.force_login(mitra)
        get_response = client.get(reverse('waste_reward:redeem', args=[voucher.pk]))
        self.assertEqual(get_response.status_code, 405)

        client.force_login(consumer)
        post_response = client.post(reverse('waste_reward:redeem', args=[voucher.pk]))
        self.assertEqual(post_response.status_code, 403)

    def test_ajax_redemption_updates_balance_and_returns_voucher(self):
        mitra = self.make_user('mitra-ajax-redeem')
        voucher = self.make_voucher(points_cost=200)
        self.add_points(mitra, 500, 'PK-AJAX')
        client = Client()
        client.force_login(mitra)

        response = client.post(
            reverse('waste_reward:redeem', args=[voucher.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'redeemed')
        self.assertEqual(payload['balance'], 300)
        self.assertTrue(payload['voucher']['code'].startswith('GLV-'))
        self.assertEqual(get_balance(mitra), 300)

    def test_ajax_redemption_keeps_platinum_progress_at_one_hundred(self):
        mitra = self.make_user('mitra-ajax-platinum')
        voucher = self.make_voucher(code='platinum-redeem', points_cost=200)
        self.add_points(mitra, 5200, 'PK-PLATINUM')
        client = Client()
        client.force_login(mitra)

        response = client.post(
            reverse('waste_reward:redeem', args=[voucher.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.json()['balance'], 5000)
        self.assertEqual(response.json()['progress'], 100)
        self.assertTrue(response.json()['is_max_level'])

    def test_ajax_insufficient_points_returns_conflict_without_spending(self):
        mitra = self.make_user('mitra-ajax-insufficient')
        voucher = self.make_voucher(points_cost=200)
        self.add_points(mitra, 100, 'PK-AJAX-LOW')
        client = Client()
        client.force_login(mitra)

        response = client.post(
            reverse('waste_reward:redeem', args=[voucher.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn('error', response.json())
        self.assertEqual(get_balance(mitra), 100)
        self.assertFalse(UserVoucher.objects.filter(user=mitra).exists())

    def test_ajax_voucher_race_returns_a_clear_conflict(self):
        mitra = self.make_user('mitra-ajax-voucher-race')
        voucher = self.make_voucher(code='ajax-race')
        client = Client()
        client.force_login(mitra)
        with patch('waste_reward.views.redeem_voucher', side_effect=VoucherUnavailable('Voucher berubah.')):
            response = client.post(
                reverse('waste_reward:redeem', args=[voucher.pk]),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error'], 'Voucher berubah.')

    def test_transaction_history_filters_and_paginates_per_member(self):
        mitra = self.make_user('mitra-history-pagination')
        other = self.make_user('mitra-history-other')
        for index in range(12):
            self.add_points(mitra, 5, f'PK-HISTORY-{index}')
        self.add_points(other, 500, 'PK-HISTORY-OTHER')
        RewardTransaction.objects.filter(source_reference='PK-HISTORY-0').update(
            created_at=timezone.now() - timedelta(days=40)
        )
        client = Client()
        client.force_login(mitra)

        first_page = client.get(reverse('waste_reward:dashboard'), {'kind': 'pickup'})
        second_page = client.get(
            reverse('waste_reward:dashboard'), {'kind': 'pickup', 'page': 2}
        )

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(first_page.context['transaction_page'].paginator.count, 12)
        self.assertEqual(len(first_page.context['transactions']), 10)
        self.assertEqual(len(second_page.context['transactions']), 2)
        self.assertContains(first_page, 'name="kind"')
        recent = client.get(
            reverse('waste_reward:dashboard'), {'kind': 'pickup', 'period': '30'}
        )
        self.assertEqual(recent.context['transaction_page'].paginator.count, 11)

    def test_html_redemption_handles_insufficient_and_unavailable_vouchers(self):
        mitra = self.make_user('mitra-html-redemption')
        low_cost_voucher = self.make_voucher(code='not-enough-points', points_cost=200)
        inactive = self.make_voucher(code='inactive-html', is_active=False)
        self.add_points(mitra, 50, 'PK-HTML-LOW')
        client = Client()
        client.force_login(mitra)

        low = client.post(reverse('waste_reward:redeem', args=[low_cost_voucher.pk]))
        inactive_response = client.post(reverse('waste_reward:redeem', args=[inactive.pk]))

        self.assertRedirects(low, reverse('waste_reward:dashboard'))
        self.assertEqual(inactive_response.status_code, 404)
        self.assertEqual(get_balance(mitra), 50)

    def test_html_redemption_handles_service_error_and_success(self):
        mitra = self.make_user('mitra-html-redemption-result')
        voucher = self.make_voucher(code='html-redeem-result', points_cost=20)
        self.add_points(mitra, 100, 'PK-HTML-SUCCESS')
        client = Client()
        client.force_login(mitra)

        with patch('waste_reward.views.redeem_voucher', side_effect=VoucherUnavailable('Voucher berubah.')):
            unavailable = client.post(reverse('waste_reward:redeem', args=[voucher.pk]))
        success = client.post(reverse('waste_reward:redeem', args=[voucher.pk]))

        self.assertRedirects(unavailable, reverse('waste_reward:dashboard'))
        self.assertRedirects(success, reverse('waste_reward:dashboard'))
        self.assertEqual(get_balance(mitra), 80)


class RewardLedgerIntegrityTests(WasteRewardTestCase):
    def test_database_rejects_zero_cost_vouchers(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_voucher(code='zero-cost-voucher', points_cost=0)

    def test_database_rejects_inconsistent_reward_transaction(self):
        mitra = self.make_user('mitra-invalid-ledger')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RewardTransaction.objects.create(
                    user=mitra,
                    kind=RewardTransaction.Kind.PICKUP,
                    points_delta=-10,
                    balance_after=0,
                    weight_kg=Decimal('2.0'),
                    description='Invalid pickup ledger row',
                )

    def test_reward_transaction_has_a_human_readable_label(self):
        mitra = self.make_user('mitra-ledger-label')
        entry = self.add_points(mitra, 10, 'PK-LEDGER-LABEL')
        self.assertIn('10 poin', str(entry))


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class RewardAdminSecurityTests(WasteRewardTestCase):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_superuser(
            username='reward-admin', email='admin@example.test', password='test-password'
        )
        self.client.force_login(self.staff)

    def test_voucher_admin_supports_catalog_crud_and_bulk_archive(self):
        response = self.client.get(reverse('admin:waste_reward_rewardvoucher_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Aktifkan voucher terpilih')
        self.assertContains(response, 'Nonaktifkan voucher terpilih')
        self.assertContains(response, 'Penukaran')

    def test_reward_ledger_and_owned_vouchers_are_read_only_in_admin(self):
        transaction_admin = admin.site._registry[RewardTransaction]
        user_voucher_admin = admin.site._registry[UserVoucher]
        request = RequestFactory().get('/admin/')
        request.user = self.staff

        for model_admin in (transaction_admin, user_voucher_admin):
            with self.subTest(model=model_admin.model.__name__):
                self.assertFalse(model_admin.has_add_permission(request))
                self.assertFalse(model_admin.has_change_permission(request))
                self.assertFalse(model_admin.has_delete_permission(request))

    def test_voucher_history_is_archived_instead_of_deleted(self):
        voucher_admin = admin.site._registry[RewardVoucher]
        request = RequestFactory().get('/admin/')
        request.user = self.staff
        self.assertTrue(voucher_admin.has_add_permission(request))
        self.assertTrue(voucher_admin.has_change_permission(request))
        self.assertFalse(voucher_admin.has_delete_permission(request))

    def test_bulk_actions_activate_and_archive_without_deleting(self):
        voucher_admin = admin.site._registry[RewardVoucher]
        request = RequestFactory().post('/admin/')
        request.user = self.staff
        request.session = {}
        request._messages = FallbackStorage(request)
        voucher = self.make_voucher(code='bulk-action-voucher')
        vouchers = RewardVoucher.objects.filter(pk=voucher.pk)

        voucher_admin.deactivate_vouchers(request, vouchers)
        voucher.refresh_from_db()
        self.assertFalse(voucher.is_active)
        voucher_admin.activate_vouchers(request, RewardVoucher.objects.filter(pk=voucher.pk))
        voucher.refresh_from_db()
        self.assertTrue(voucher.is_active)
