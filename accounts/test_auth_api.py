from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from courier.models import CourierProfile
from scheduling.models import MitraProfile


PASSWORD = 'Valid-api-password-93!'
MITRA_FIELDS = {
    'business_name': 'Green Business',
    'business_type': 'restaurant',
    'pic_name': 'Afiqah',
    'phone_number': '08123456789',
    'provinsi': 'Jawa Barat',
    'kota': 'Depok',
    'kecamatan': 'Beji',
    'kelurahan': 'Pondok Cina',
    'address_detail': 'Jl. Margonda Raya',
}


def registration_data(username, role='consumer', **extra):
    return {
        'username': username,
        'email': f'{username}@example.com',
        'password1': PASSWORD,
        'password2': PASSWORD,
        'role': role,
        **extra,
    }


class SessionAuthAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.csrf_url = reverse('accounts_api:csrf')
        self.register_url = reverse('accounts_api:register')
        self.login_url = reverse('accounts_api:login')
        self.logout_url = reverse('accounts_api:logout')
        self.profile_url = reverse('accounts_api:profile')

    def csrf_token(self):
        response = self.client.get(self.csrf_url, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('csrftoken', self.client.cookies)
        return response.json()['csrf_token']

    def post_with_csrf(self, url, data):
        token = self.csrf_token()
        return self.client.post(
            url,
            data,
            format='json',
            HTTP_X_CSRFTOKEN=token,
        )

    def create_user(self, username, role='consumer', password=PASSWORD):
        user = get_user_model().objects.create_user(
            username=username,
            email=f'{username}@example.com',
            password=password,
        )
        user.userprofile.role = role
        user.userprofile.save(update_fields=('role',))
        return user

    def test_csrf_bootstrap_sets_cookie_and_returns_token(self):
        response = self.client.get(self.csrf_url, HTTP_ACCEPT='application/json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()['csrf_token'])
        self.assertIn('csrftoken', self.client.cookies)

    def test_all_auth_post_endpoints_reject_missing_csrf_token(self):
        requests = (
            (self.register_url, registration_data('csrf_missing')),
            (self.login_url, {'username': 'missing', 'password': PASSWORD}),
            (self.logout_url, {}),
        )

        for url, data in requests:
            with self.subTest(url=url):
                response = self.client.post(url, data, format='json')
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertTrue(response['Content-Type'].startswith('application/json'))

    def test_register_consumer_creates_profile_and_starts_session(self):
        response = self.post_with_csrf(
            self.register_url,
            registration_data('new_consumer'),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()['profile']['user']['username'], 'new_consumer')
        self.assertEqual(response.json()['profile']['role'], 'consumer')
        self.assertNotIn('password', response.content.decode().lower())
        self.assertTrue(response.json()['csrf_token'])
        self.assertEqual(self.client.get(self.profile_url).status_code, status.HTTP_200_OK)

    def test_register_mitra_creates_role_profile(self):
        response = self.post_with_csrf(
            self.register_url,
            registration_data('new_mitra', role='mitra', **MITRA_FIELDS),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = get_user_model().objects.get(username='new_mitra')
        self.assertEqual(user.userprofile.role, 'mitra')
        self.assertTrue(MitraProfile.objects.filter(user=user).exists())
        self.assertEqual(MitraProfile.objects.get(user=user).business_type, 'Restoran')

    def test_register_courier_creates_role_profile(self):
        response = self.post_with_csrf(
            self.register_url,
            registration_data(
                'new_courier',
                role='courier',
                full_name='Kurir Baru',
                plate_number='B 1234 KZT',
                vehicle_type='motor',
            ),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = get_user_model().objects.get(username='new_courier')
        self.assertEqual(user.userprofile.role, 'courier')
        courier_profile = CourierProfile.objects.get(user=user)
        self.assertEqual(courier_profile.plate_number, 'B 1234 KZT')
        self.assertEqual(courier_profile.vehicle_type, CourierProfile.VehicleType.MOTOR_BOX)
        self.assertEqual(user.first_name, 'Kurir Baru')

    def test_register_duplicate_username_is_rejected(self):
        self.create_user('existing_user')

        response = self.post_with_csrf(
            self.register_url,
            registration_data('existing_user'),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.json()['errors'])

    def test_register_invalid_password_is_rejected(self):
        data = registration_data('weak_password')
        data.update(password1='123', password2='123')

        response = self.post_with_csrf(self.register_url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue({'password1', 'password2'} & set(response.json()['errors']))

    def test_register_admin_role_is_rejected(self):
        response = self.post_with_csrf(
            self.register_url,
            registration_data('public_admin', role='admin'),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('role', response.json()['errors'])
        self.assertFalse(get_user_model().objects.filter(username='public_admin').exists())

    def test_register_mitra_and_courier_specific_validation(self):
        missing_mitra_fields = self.post_with_csrf(
            self.register_url,
            registration_data('missing_mitra', role='mitra'),
        )
        self.assertEqual(missing_mitra_fields.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('business_name', missing_mitra_fields.json()['errors'])
        self.assertIn('kota', missing_mitra_fields.json()['errors'])

        invalid_courier = self.post_with_csrf(
            self.register_url,
            registration_data(
                'invalid_courier',
                role='courier',
                plate_number='not-a-plate',
            ),
        )
        self.assertEqual(invalid_courier.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('plate_number', invalid_courier.json()['errors'])
        self.assertIn('vehicle_type', invalid_courier.json()['errors'])

    def test_login_success_creates_session_usable_by_profile_api(self):
        user = self.create_user('login_user')

        response = self.post_with_csrf(
            self.login_url,
            {'username': user.username, 'password': PASSWORD},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['profile']['user']['username'], user.username)
        self.assertNotIn('password', response.content.decode().lower())
        self.assertTrue(response.json()['csrf_token'])
        profile_response = self.client.get(self.profile_url, HTTP_ACCEPT='application/json')
        self.assertEqual(profile_response.status_code, status.HTTP_200_OK)
        self.assertEqual(profile_response.json()['user']['id'], user.id)

    def test_login_wrong_password_and_unknown_username_are_rejected(self):
        self.create_user('known_user')

        for credentials in (
            {'username': 'known_user', 'password': 'wrong-password'},
            {'username': 'unknown_user', 'password': PASSWORD},
        ):
            with self.subTest(username=credentials['username']):
                response = self.post_with_csrf(self.login_url, credentials)
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
                self.assertEqual(
                    response.json(),
                    {'detail': 'Username atau password salah.'},
                )

    def test_login_requires_csrf_even_for_anonymous_request(self):
        response = self.client.post(
            self.login_url,
            {'username': 'known_user', 'password': PASSWORD},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_authenticated_user_can_logout_and_profile_session_ends(self):
        user = self.create_user('logout_user')
        self.client.force_login(user)
        token = self.csrf_token()

        response = self.client.post(
            self.logout_url,
            {},
            format='json',
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {'detail': 'Logout berhasil.'})
        self.assertEqual(
            self.client.get(self.profile_url, HTTP_ACCEPT='application/json').status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_pending_courier_can_logout_and_cannot_open_restricted_page(self):
        courier = self.create_user('pending_logout', role='courier')
        self.client.force_login(courier)
        token = self.csrf_token()

        restricted_page = self.client.get(reverse('courier:show_profile'))
        self.assertEqual(restricted_page.status_code, status.HTTP_302_FOUND)
        self.assertIn(reverse('courier:pending_verification'), restricted_page.url)

        logout_response = self.client.post(
            self.logout_url,
            {},
            format='json',
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)
        self.assertTrue(logout_response['Content-Type'].startswith('application/json'))
        profile_response = self.client.get(self.profile_url, HTTP_ACCEPT='application/json')
        self.assertEqual(profile_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(profile_response['Content-Type'].startswith('application/json'))

    def test_logged_out_pending_courier_gets_json_forbidden_from_profile(self):
        courier = self.create_user('logged_out_courier', role='courier')
        self.client.force_login(courier)
        self.client.logout()

        response = self.client.get(self.profile_url, HTTP_ACCEPT='application/json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(response['Content-Type'].startswith('application/json'))

    def test_anonymous_logout_is_idempotent_json_success(self):
        response = self.post_with_csrf(self.logout_url, {})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {'detail': 'Logout berhasil.'})
