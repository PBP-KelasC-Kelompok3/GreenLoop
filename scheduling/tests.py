from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from .models import MitraProfile, PickupSchedule


PLAIN_STATIC = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


@override_settings(STORAGES=PLAIN_STATIC)
class MitraProfileCrudTests(TestCase):
    def setUp(self):
        self.mitra = User.objects.create_user(username='mitra-crud', password='pw12345!')
        UserProfile.objects.filter(user=self.mitra).update(role='mitra')
        self.client.force_login(self.mitra)
        self.url = reverse('mitra_profile')

    def test_read_profile_creates_missing_profile_for_mitra(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(MitraProfile.objects.filter(user=self.mitra).exists())

    def test_update_profile_persists_validated_fields(self):
        MitraProfile.objects.create(user=self.mitra, location_locked=True)

        response = self.client.post(self.url, {
            'business_name': 'Kafe Hijau',
            'business_type': 'Kafe / Coffee Shop',
            'pic_name': 'Ayu',
            'phone_number': '+62 812-3456-7890',
            'operational_hours': '07.00-20.00',
            'provinsi': 'Jawa Barat',
            'kota': 'Depok',
            'kecamatan': 'Beji',
            'kelurahan': 'Kukusan',
            'address_detail': 'Jl. Contoh No. 1',
            'courier_notes': 'Hubungi PIC saat tiba',
            'latitude': '',
            'longitude': '',
        })

        self.assertRedirects(response, self.url)
        profile = MitraProfile.objects.get(user=self.mitra)
        self.assertEqual(profile.business_name, 'Kafe Hijau')
        self.assertEqual(profile.phone_number, '+62 812-3456-7890')

    def test_invalid_profile_data_is_not_saved(self):
        profile = MitraProfile.objects.create(
            user=self.mitra,
            business_name='Nama Lama',
            location_locked=True,
        )

        response = self.client.post(self.url, {
            'business_name': 'Nama Baru',
            'business_type': 'Jenis Tidak Valid',
            'phone_number': 'nomor-tidak-valid',
            'latitude': '',
            'longitude': '',
        })

        self.assertEqual(response.status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.business_name, 'Nama Lama')

    def test_delete_removes_only_profile_and_keeps_user(self):
        MitraProfile.objects.create(user=self.mitra)

        response = self.client.post(reverse('delete_mitra_profile'))

        self.assertRedirects(response, reverse('mitra_dashboard'))
        self.assertFalse(MitraProfile.objects.filter(user=self.mitra).exists())
        self.assertTrue(User.objects.filter(pk=self.mitra.pk).exists())

    def test_non_mitra_cannot_view_update_or_delete_profile(self):
        other = User.objects.create_user(username='consumer-crud', password='pw12345!')
        self.client.force_login(other)

        response = self.client.get(self.url)
        self.assertRedirects(response, reverse('home'))

        response = self.client.post(self.url, {'business_name': 'Tidak boleh'})
        self.assertRedirects(response, reverse('home'))
        self.assertFalse(MitraProfile.objects.filter(user=other).exists())

        response = self.client.post(reverse('delete_mitra_profile'))
        self.assertRedirects(response, reverse('home'))

    def make_pending_pickup(self, mitra=None, status='PENDING'):
        return PickupSchedule.objects.create(
            mitra=mitra or self.mitra,
            estimated_weight=2,
            pickup_date=timezone.localdate() + timedelta(days=1),
            pickup_time_slot='08:00 - 10:00 WIB',
            status=status,
        )

    @patch('courier.maps.in_depok', return_value=True)
    def test_mitra_can_create_pickup(self, _in_depok):
        MitraProfile.objects.create(
            user=self.mitra,
            latitude=-6.4,
            longitude=106.8,
            location_locked=True,
        )
        response = self.client.post(reverse('create_pickup'), {
            'waste_type': 'FRUIT_VEG',
            'estimated_weight': '4.5',
            'pickup_date': (timezone.localdate() + timedelta(days=1)).isoformat(),
            'pickup_time_slot': '08:00 - 10:00 WIB',
            'armada': 'Motor Box',
            'notes': 'Hubungi PIC',
        })

        self.assertRedirects(response, reverse('mitra_dashboard'))
        pickup = PickupSchedule.objects.get(mitra=self.mitra)
        self.assertEqual(pickup.status, 'PENDING')
        self.assertEqual(pickup.estimated_weight, 4.5)

    def test_mitra_can_update_own_pending_pickup(self):
        pickup = self.make_pending_pickup()
        response = self.client.post(reverse('edit_pickup', args=[pickup.pk]), {
            'pickup_date': (timezone.localdate() + timedelta(days=2)).isoformat(),
            'time_slot': '10:00 - 12:00 WIB',
            'notes': 'Catatan diperbarui',
        })

        self.assertRedirects(response, reverse('mitra_dashboard'))
        pickup.refresh_from_db()
        self.assertEqual(pickup.notes, 'Catatan diperbarui')
        self.assertEqual(pickup.pickup_time_slot, '10:00 - 12:00 WIB')

    def test_mitra_can_delete_own_pending_pickup(self):
        pickup = self.make_pending_pickup()

        response = self.client.post(reverse('delete_pickup', args=[pickup.pk]))

        self.assertRedirects(response, reverse('pickup_history'))
        self.assertFalse(PickupSchedule.objects.filter(pk=pickup.pk).exists())

    def test_mitra_cannot_delete_processed_or_another_users_pickup(self):
        processed = self.make_pending_pickup(status='APPROVED')
        other = User.objects.create_user(username='other-mitra', password='pw12345!')
        UserProfile.objects.filter(user=other).update(role='mitra')
        other_pickup = self.make_pending_pickup(mitra=other)

        response = self.client.post(reverse('delete_pickup', args=[processed.pk]))
        self.assertRedirects(response, reverse('pickup_history'))
        self.assertTrue(PickupSchedule.objects.filter(pk=processed.pk).exists())

        response = self.client.post(reverse('delete_pickup', args=[other_pickup.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(PickupSchedule.objects.filter(pk=other_pickup.pk).exists())
