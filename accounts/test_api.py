from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import UserProfile


class ReadProfileAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='profile_owner',
            email='owner@example.com',
            password='Safe-test-password-123!',
        )
        self.user.userprofile.role = 'mitra'
        self.user.userprofile.save(update_fields=('role',))
        self.url = reverse('accounts_api:profile')

    def test_authenticated_user_reads_own_profile(self):
        self.client.login(username='profile_owner', password='Safe-test-password-123!')

        response = self.client.get(self.url, HTTP_ACCEPT='application/json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['user']['id'], self.user.id)

    def test_response_contains_username_email_and_role(self):
        self.client.login(username='profile_owner', password='Safe-test-password-123!')

        response = self.client.get(self.url, HTTP_ACCEPT='application/json')

        self.assertEqual(
            response.json(),
            {
                'user': {
                    'id': self.user.id,
                    'username': 'profile_owner',
                    'email': 'owner@example.com',
                    'first_name': '',
                    'last_name': '',
                },
                'role': 'mitra',
                'mitra_profile': None,
                'courier_profile': None,
            },
        )

    def test_anonymous_user_gets_json_forbidden_response(self):
        response = self.client.get(self.url, HTTP_ACCEPT='application/json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json(), {'detail': 'Authentication credentials were not provided.'})
        self.assertTrue(response['Content-Type'].startswith('application/json'))

    def test_response_does_not_expose_password(self):
        self.client.login(username='profile_owner', password='Safe-test-password-123!')

        response = self.client.get(self.url, HTTP_ACCEPT='application/json')
        response_text = response.content.decode('utf-8').lower()

        self.assertNotIn('password', response_text)
        self.assertNotIn(self.user.password, response_text)

    def test_request_id_cannot_select_another_users_profile(self):
        other_user = get_user_model().objects.create_user(
            username='another_user',
            email='another@example.com',
            password='Another-safe-password-123!',
        )
        self.client.login(username='profile_owner', password='Safe-test-password-123!')

        response = self.client.get(
            self.url,
            {'user_id': other_user.id},
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['user']['id'], self.user.id)

    def test_response_schema_is_stable_json_and_role_is_read_only(self):
        self.client.login(username='profile_owner', password='Safe-test-password-123!')

        response = self.client.get(self.url, HTTP_ACCEPT='application/json')

        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(
            set(response.json().keys()),
            {'user', 'role', 'mitra_profile', 'courier_profile'},
        )
        self.assertEqual(
            set(response.json()['user'].keys()),
            {'id', 'username', 'email', 'first_name', 'last_name'},
        )

        update_response = self.client.patch(
            self.url,
            {'role': 'admin'},
            format='json',
        )

        self.assertEqual(update_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.userprofile.refresh_from_db()
        self.assertEqual(self.user.userprofile.role, 'mitra')

    def test_missing_user_profile_returns_json_not_found(self):
        self.client.login(username='profile_owner', password='Safe-test-password-123!')
        UserProfile.objects.filter(user=self.user).delete()

        response = self.client.get(self.url, HTTP_ACCEPT='application/json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.json(), {'detail': 'Profil pengguna tidak tersedia.'})

    def test_pending_courier_can_reach_read_profile_api(self):
        courier = get_user_model().objects.create_user(
            username='pending_courier',
            email='courier@example.com',
            password='Courier-safe-password-123!',
        )
        courier.userprofile.role = 'courier'
        courier.userprofile.save(update_fields=('role',))
        self.client.login(username='pending_courier', password='Courier-safe-password-123!')

        response = self.client.get(self.url, HTTP_ACCEPT='application/json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['user']['username'], 'pending_courier')
        self.assertEqual(response.json()['role'], 'courier')
