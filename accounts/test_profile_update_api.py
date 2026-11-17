from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from courier.models import CourierProfile
from scheduling.models import MitraProfile


PASSWORD = 'Update-profile-password-91!'


class ProfileUpdateAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.url = reverse('accounts_api:profile')
        self.csrf_url = reverse('accounts_api:csrf')
        self.user = self.create_user('profile_user')

    def create_user(self, username, role='consumer', email=None, superuser=False):
        User = get_user_model()
        if superuser:
            user = User.objects.create_superuser(
                username=username,
                email=email or f'{username}@example.com',
                password=PASSWORD,
            )
        else:
            user = User.objects.create_user(
                username=username,
                email=email or f'{username}@example.com',
                password=PASSWORD,
            )
            user.userprofile.role = role
            user.userprofile.save(update_fields=('role',))
        return user

    def csrf_token(self):
        response = self.client.get(self.csrf_url, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.json()['csrf_token']

    def login(self, user=None):
        self.client.force_login(user or self.user)
        return self.csrf_token()

    def patch_with_csrf(self, data, token=None):
        token = token or self.csrf_token()
        return self.client.patch(
            self.url,
            data,
            format='json',
            HTTP_X_CSRFTOKEN=token,
        )

    def test_username_change_keeps_session_and_profile_response_current(self):
        self.login()

        response = self.patch_with_csrf({'username': 'renamed_user'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'renamed_user')
        self.assertEqual(
            self.client.session.get('_auth_user_id'),
            str(self.user.pk),
        )
        get_response = self.client.get(self.url, HTTP_ACCEPT='application/json')
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.json()['user']['username'], 'renamed_user')

    def test_email_change_is_normalized_and_returned(self):
        self.login()

        response = self.patch_with_csrf({'email': '  NEW@Example.COM  '})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['user']['email'], 'new@example.com')

    def test_first_and_last_name_can_be_updated(self):
        self.login()

        response = self.patch_with_csrf({
            'first_name': 'Afiqah',
            'last_name': 'GreenLoop',
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['user']['first_name'], 'Afiqah')
        self.assertEqual(response.json()['user']['last_name'], 'GreenLoop')

    def test_partial_update_changes_only_submitted_fields(self):
        self.user.first_name = 'Old'
        self.user.last_name = 'Name'
        self.user.save(update_fields=('first_name', 'last_name'))
        self.login()

        response = self.patch_with_csrf({'first_name': 'New'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'New')
        self.assertEqual(self.user.last_name, 'Name')
        self.assertEqual(self.user.email, 'profile_user@example.com')

    def test_same_username_is_valid(self):
        self.login()

        response = self.patch_with_csrf({'username': self.user.username})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['user']['username'], 'profile_user')

    def test_username_owned_by_another_user_is_rejected(self):
        self.create_user('taken_name')
        self.login()

        response = self.patch_with_csrf({'username': 'taken_name'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.json())
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'profile_user')

    def test_duplicate_email_is_rejected_case_insensitively(self):
        self.create_user('email_owner', email='taken@example.com')
        self.login()

        response = self.patch_with_csrf({'email': 'TAKEN@example.com'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.json())
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'profile_user@example.com')

    def test_anonymous_user_cannot_patch_profile(self):
        response = self.client.patch(
            self.url,
            {'username': 'anonymous_change'},
            format='json',
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(response['Content-Type'].startswith('application/json'))

    def test_role_password_and_access_fields_are_rejected(self):
        self.login()

        for forbidden_data in (
            {'role': 'admin'},
            {'password': 'New-password-123!'},
            {'is_staff': True},
            {'is_superuser': True},
        ):
            with self.subTest(field=next(iter(forbidden_data))):
                response = self.patch_with_csrf(forbidden_data)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(next(iter(forbidden_data)), response.json())

        self.user.refresh_from_db()
        self.user.userprofile.refresh_from_db()
        self.assertEqual(self.user.userprofile.role, 'consumer')
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)

    def test_request_cannot_choose_another_users_id(self):
        other = self.create_user('other_profile')
        self.login()

        response = self.patch_with_csrf({
            'user_id': other.pk,
            'email': 'attempt@example.com',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.user.email, 'profile_user@example.com')
        self.assertEqual(other.email, 'other_profile@example.com')

    def test_patch_without_csrf_token_is_rejected(self):
        self.client.force_login(self.user)

        response = self.client.patch(
            self.url,
            {'first_name': 'No CSRF'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, '')

    def test_common_profile_fields_are_available_for_each_role(self):
        users = [
            self.user,
            self.create_user('mitra_user', role='mitra'),
            self.create_user('courier_user', role='courier'),
            self.create_user('admin_user', superuser=True),
        ]

        for user in users:
            with self.subTest(role=user.userprofile.role):
                token = self.login(user)
                response = self.patch_with_csrf(
                    {'first_name': 'Updated'},
                    token=token,
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.json()['user']['first_name'], 'Updated')
                self.assertEqual(response.json()['role'], user.userprofile.role)
                self.client.logout()

    def test_mitra_can_update_safe_business_profile_fields(self):
        mitra = self.create_user('mitra_profile', role='mitra')
        profile = MitraProfile.objects.create(
            user=mitra,
            business_name='Old Business',
            business_type='Restoran',
            phone_number='08123456789',
        )
        self.login(mitra)

        response = self.patch_with_csrf({
            'business_name': 'New Business',
            'phone_number': '+62 812-3456-789',
            'operational_hours': '08.00-17.00 WIB',
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile.refresh_from_db()
        self.assertEqual(profile.business_name, 'New Business')
        self.assertEqual(profile.phone_number, '+62 812-3456-789')
        self.assertEqual(response.json()['mitra_profile']['business_name'], 'New Business')

    def test_mitra_address_and_location_state_cannot_be_changed_here(self):
        mitra = self.create_user('mitra_location', role='mitra')
        MitraProfile.objects.create(user=mitra, location_locked=True)
        self.login(mitra)

        response = self.patch_with_csrf({'latitude': -6.4, 'longitude': 106.8})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('latitude', response.json())

    def test_mitra_phone_validation_matches_website_form(self):
        mitra = self.create_user('mitra_phone', role='mitra')
        MitraProfile.objects.create(user=mitra)
        self.login(mitra)

        response = self.patch_with_csrf({'phone_number': 'phone-call'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('phone_number', response.json())

    def test_courier_can_update_vehicle_fields_without_changing_approval(self):
        courier = self.create_user('courier_profile', role='courier')
        profile = CourierProfile.objects.create(
            user=courier,
            plate_number='B 1234 KZT',
            is_approved=False,
        )
        self.login(courier)

        response = self.patch_with_csrf({
            'plate_number': 'd 12 ab',
            'vehicle_type': CourierProfile.VehicleType.MOTOR_BOX,
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile.refresh_from_db()
        self.assertEqual(profile.plate_number, 'D 12 AB')
        self.assertEqual(profile.vehicle_type, CourierProfile.VehicleType.MOTOR_BOX)
        self.assertFalse(profile.is_approved)
        self.assertEqual(response.json()['courier_profile']['plate_number'], 'D 12 AB')

    def test_courier_invalid_plate_is_rejected(self):
        courier = self.create_user('courier_plate', role='courier')
        CourierProfile.objects.create(user=courier)
        self.login(courier)

        response = self.patch_with_csrf({'plate_number': 'NOT-A-PLATE'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('plate_number', response.json())

    def test_role_specific_fields_are_rejected_for_other_roles(self):
        self.login()

        response = self.patch_with_csrf({'plate_number': 'B 1234 KZT'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('plate_number', response.json())
