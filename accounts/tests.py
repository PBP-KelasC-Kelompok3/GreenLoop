from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import UserProfile


PLAIN_STATIC = {
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
}


def make_user(username, role, password="testpass123"):
    user = User.objects.create_user(
        username=username,
        password=password,
    )
    user.userprofile.role = role
    user.userprofile.save()
    return user


class LoginRedirectTests(TestCase):

    def test_admin_redirects_to_admin_dashboard(self):
        user = make_user("adminuser", "admin")

        response = self.client.post(
            reverse("login"),
            {
                "username": user.username,
                "password": "testpass123",
            },
        )

        self.assertRedirects(
            response,
            reverse("admin_dashboard"),
        )

    def test_courier_redirects_to_courier_dashboard(self):
        user = make_user("courieruser", "courier")

        response = self.client.post(
            reverse("login"),
            {
                "username": user.username,
                "password": "testpass123",
            },
        )

        self.assertRedirects(
            response,
            reverse("courier:show_dashboard"),
        )

    def test_other_roles_redirect_home(self):
        for role in ["consumer", "mitra"]:
            user = make_user(f"{role}user", role)

            response = self.client.post(
                reverse("login"),
                {
                    "username": user.username,
                    "password": "testpass123",
                },
            )

            self.assertRedirects(
                response,
                reverse("home"),
            )

    def test_wrong_password_shows_error(self):
        make_user("wrongpassuser", "consumer")

        response = self.client.post(
            reverse("login"),
            {
                "username": "wrongpassuser",
                "password": "wrongpassword",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Username atau password salah.",
        )

    def test_register_courier(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "newcourier",
                "email": "courier@example.com",
                "password1": "testpass123",
                "password2": "testpass123",
                "role": "courier",
            },
        )

        self.assertRedirects(
            response,
            reverse("courier:show_dashboard"),
        )

        user = User.objects.get(username="newcourier")
        self.assertEqual(user.userprofile.role, "courier")

    def test_register_consumer(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "newconsumer",
                "email": "consumer@example.com",
                "password1": "testpass123",
                "password2": "testpass123",
                "role": "consumer",
            },
        )

        self.assertRedirects(
            response,
            reverse("home"),
        )

        user = User.objects.get(username="newconsumer")
        self.assertEqual(user.userprofile.role, "consumer")


MITRA_DATA = {
    "business_name": "Green Business",
    "business_type": "Restaurant",
    "responsible_person": "Afiqah",
    "whatsapp": "08123456789",
    "province": "Jawa Barat",
    "city": "Depok",
    "district": "Beji",
    "address": "Jl. Margonda Raya",
}


class RegisterProfileTests(TestCase):

    def test_admin_not_available_in_public_registration(self):
        from .forms import RegisterForm

        form = RegisterForm()

        role_choices = [
            value
            for value, label in form.fields["role"].choices
        ]

        self.assertNotIn("admin", role_choices)

    def test_mitra_profile_saves(self):
        data = {
            "username": "mitrauser",
            "email": "mitra@example.com",
            "password1": "testpass123",
            "password2": "testpass123",
            "role": "mitra",
            **MITRA_DATA,
        }

        response = self.client.post(
            reverse("register"),
            data,
        )

        self.assertEqual(response.status_code, 302)

        user = User.objects.get(username="mitrauser")
        self.assertEqual(user.userprofile.role, "mitra")

    def test_mitra_depok_restriction(self):
        data = {
            "username": "mitraoutside",
            "email": "outside@example.com",
            "password1": "testpass123",
            "password2": "testpass123",
            "role": "mitra",
            **MITRA_DATA,
            "city": "Jakarta Selatan",
        }

        response = self.client.post(
            reverse("register"),
            data,
        )

        self.assertEqual(response.status_code, 200)

    def test_mitra_business_fields_required(self):
        from .forms import RegisterForm

        form = RegisterForm(
            data={
                "username": "mitrarequired",
                "email": "required@example.com",
                "password1": "testpass123",
                "password2": "testpass123",
                "role": "mitra",
            }
        )

        self.assertFalse(form.is_valid())

    def test_courier_vehicle_data(self):
        data = {
            "username": "couriervehicle",
            "email": "vehicle@example.com",
            "password1": "testpass123",
            "password2": "testpass123",
            "role": "courier",
            "vehicle_type": "Motor",
            "plate_number": "B1234XYZ",
        }

        response = self.client.post(
            reverse("register"),
            data,
        )

        self.assertEqual(response.status_code, 302)

    def test_invalid_plate(self):
        from .forms import RegisterForm

        data = {
            "username": "invalidplate",
            "email": "invalid@example.com",
            "password1": "testpass123",
            "password2": "testpass123",
            "role": "courier",
            "vehicle_type": "Motor",
            "plate_number": "INVALID",
        }

        form = RegisterForm(data=data)

        self.assertFalse(form.is_valid())


class PublicPagesTests(TestCase):

    @override_settings(STATICFILES_STORAGE=PLAIN_STATIC)
    def test_home_contains_impact_context(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "12.480")
        self.assertContains(response, "8.740")

    @override_settings(STATICFILES_STORAGE=PLAIN_STATIC)
    def test_guest_navigation_only_shows_catalog(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, "Katalog")
        self.assertNotContains(response, "Dashboard Mitra")
        self.assertNotContains(response, "Dashboard Courier")
        self.assertNotContains(response, "Rewards")

    @override_settings(STATICFILES_STORAGE=PLAIN_STATIC)
    def test_role_navigation_preserved(self):
        courier = make_user("navcourier", "courier")
        self.client.force_login(courier)

        response = self.client.get(reverse("home"))

        self.assertContains(
            response,
            reverse("courier:show_dashboard"),
        )
        self.assertContains(
            response,
            reverse("courier:show_route_today"),
        )

        self.client.logout()

        mitra = make_user("navmitra", "mitra")
        self.client.force_login(mitra)

        response = self.client.get(reverse("home"))

        self.assertContains(
            response,
            reverse("waste_reward:dashboard"),
        )

    @override_settings(STATICFILES_STORAGE=PLAIN_STATIC)
    def test_login_page(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Masuk")

    @override_settings(STATICFILES_STORAGE=PLAIN_STATIC)
    def test_login_error(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": "doesnotexist",
                "password": "wrongpassword",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Username atau password salah.",
        )