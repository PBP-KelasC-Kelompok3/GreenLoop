from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import RewardTransaction, RewardVoucher, UserVoucher
from .services import (
    InsufficientPoints,
    VoucherUnavailable,
    apply_voucher_at_checkout,
    award_verified_pickup,
    get_balance,
    redeem_voucher,
)


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
        kind=RewardVoucher.Kind.DISCOUNT,
        value_label='Rp 10.000',
        points_cost=200,
        valid_days=30,
        is_active=True,
    ):
        code = code or f'diskon-test-{uuid4().hex[:10]}'
        return RewardVoucher.objects.create(
            code=code,
            title='Voucher tes',
            kind=kind,
            value_label=value_label,
            points_cost=points_cost,
            valid_days=valid_days,
            is_active=is_active,
        )

    def add_points(self, user, points, reference='pickup-test'):
        return RewardTransaction.objects.create(
            user=user,
            kind=RewardTransaction.Kind.PICKUP,
            points_delta=points,
            balance_after=points,
            weight_kg=Decimal('1.0'),
            description='Setoran tes',
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


class PointServiceTests(WasteRewardTestCase):
    def test_verified_pickup_awards_five_points_per_kilogram(self):
        mitra = self.make_user('mitra-points')

        entry = award_verified_pickup(mitra, '35.29', 'PK-001')

        self.assertEqual(entry.weight_kg, Decimal('35.2'))
        self.assertEqual(entry.points_delta, 176)
        self.assertEqual(entry.balance_after, 176)
        self.assertEqual(get_balance(mitra), 176)

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
    def test_mitra_can_open_dashboard_and_consumer_cannot(self):
        mitra = self.make_user('mitra-dashboard-access')
        consumer = self.make_user('consumer-dashboard-access', role='consumer')
        client = Client()

        client.force_login(mitra)
        mitra_response = client.get(reverse('waste_reward:dashboard'))
        self.assertEqual(mitra_response.status_code, 200)

        client.force_login(consumer)
        consumer_response = client.get(reverse('waste_reward:dashboard'))
        self.assertRedirects(consumer_response, reverse('home'))

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
        self.assertRedirects(post_response, reverse('home'))
