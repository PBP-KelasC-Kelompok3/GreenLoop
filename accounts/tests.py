from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import UserProfile
from courier.models import CourierProfile


PLAIN_STATIC = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage"
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}


def make_user(username, role, password="pw12345!"):
    user = User.objects.create_user(
        username=username,
        password=password,
    )
    UserProfile.objects.filter(user=user).update(role=role)
    return user


@override_settings(STORAGES=PLAIN_STATIC)
class LoginRedirectTests(TestCase):

    def login(self, username, password="pw12345!"):
        return self.client.post(
            reverse("login"),
            {
                "username": username,
                "password": password,
            },
        )

    def test_admin_redirects_to_admin_dashboard(self):
        user = make_user("adminuser", "admin")

        response = self.login(user.username)

        self.assertRedirects(
            response,
            reverse("admin_dashboard"),
            fetch_redirect_response=False,
        )

    def test_pending_courier_goes_to_approval_page(self):
        make_user("courieruser", "courier")

        response = self.login("courieruser")

        self.assertRedirects(
            response,
            reverse("courier:show_dashboard"),
            fetch_redirect_response=False,
        )
        pending = self.client.get(response.url)
        self.assertRedirects(
            pending,
            reverse("courier:pending_verification"),
            fetch_redirect_response=False,
        )

    def test_courier_dashboard_opens_after_login(self):
        courier = make_user("courierdashboard", "courier")
        CourierProfile.objects.create(user=courier, is_approved=True)

        response = self.client.post(
            reverse("login"),
            {
                "username": "courierdashboard",
                "password": "pw12345!",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "courier/dashboard.html",
        )

    def test_other_roles_go_home(self):
        for role in ("consumer", "mitra"):
            with self.subTest(role=role):
                make_user(f"user_{role}", role)

                response = self.login(f"user_{role}")

                self.assertRedirects(
                    response,
                    reverse("mitra_dashboard") if role == "mitra" else reverse("home"),
                    fetch_redirect_response=False,
                )

                self.client.logout()

    def test_wrong_password_stays_on_login(self):
        make_user("wrongpassuser", "consumer")

        response = self.login(
            "wrongpassuser",
            password="wrongpassword",
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
                "full_name": "Kurir Baru",
                "plate_number": "B 1234 KZT",
                "vehicle_type": "motor",
            },
        )

        self.assertRedirects(
            response,
            reverse("courier:show_dashboard"),
            fetch_redirect_response=False,
        )

        user = User.objects.get(username="newcourier")
        self.assertEqual(
            user.userprofile.role,
            "courier",
        )
        pending = self.client.get(response.url)
        self.assertRedirects(
            pending,
            reverse("courier:pending_verification"),
            fetch_redirect_response=False,
        )

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
            fetch_redirect_response=False,
        )

        user = User.objects.get(username="newconsumer")
        self.assertEqual(
            user.userprofile.role,
            "consumer",
        )


MITRA_DATA = {
    "business_name": "Green Business",
    "business_type": "restaurant",
    "pic_name": "Afiqah",
    "phone_number": "08123456789",
    "provinsi": "Jawa Barat",
    "kota": "Depok",
    "kecamatan": "Beji",
    "kelurahan": "Pondok Cina",
    "address_detail": "Jl. Margonda Raya",
}


@override_settings(STORAGES=PLAIN_STATIC)
class RegisterProfileTests(TestCase):

    def test_admin_not_available_in_public_registration(self):
        from .forms import RegisterForm

        form = RegisterForm()

        role_choices = [
            value
            for value, label in form.fields["role"].choices
        ]

        self.assertNotIn(
            "admin",
            role_choices,
        )

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

        user = User.objects.get(
            username="mitrauser"
        )

        self.assertEqual(
            user.userprofile.role,
            "mitra",
        )

    def test_mitra_depok_restriction(self):
        data = {
            "username": "mitraoutside",
            "email": "outside@example.com",
            "password1": "testpass123",
            "password2": "testpass123",
            "role": "mitra",
            **MITRA_DATA,
            "kota": "Jakarta Selatan",
        }

        response = self.client.post(
            reverse("register"),
            data,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

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

        self.assertFalse(
            form.is_valid()
        )

    def test_courier_vehicle_data(self):
        data = {
            "username": "couriervehicle",
            "email": "vehicle@example.com",
            "password1": "testpass123",
            "password2": "testpass123",
            "role": "courier",
            "vehicle_type": "motor",
            "plate_number": "B1234XY",
        }

        response = self.client.post(
            reverse("register"),
            data,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

    def test_invalid_plate(self):
        from .forms import RegisterForm

        data = {
            "username": "invalidplate",
            "email": "invalid@example.com",
            "password1": "testpass123",
            "password2": "testpass123",
            "role": "courier",
            "vehicle_type": "motor",
            "plate_number": "INVALID",
        }

        form = RegisterForm(data=data)

        self.assertFalse(
            form.is_valid()
        )


@override_settings(STORAGES=PLAIN_STATIC)
class PublicPagesTests(TestCase):

    def test_home_contains_impact_context(self):
        response = self.client.get(
            reverse("home")
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "12.480",
        )

        self.assertContains(
            response,
            "6.240",
        )

    def test_guest_navigation_only_shows_catalog(self):
        response = self.client.get(
            reverse("home")
        )

        self.assertContains(
            response,
            "Katalog",
        )

        self.assertNotContains(
            response,
            "Dashboard Mitra",
        )

        self.assertNotContains(
            response,
            "Dashboard Courier",
        )

        self.assertNotContains(
            response,
            "Rewards",
        )

    def test_role_navigation_preserved(self):
        courier = make_user(
            "navcourier",
            "courier",
        )
        CourierProfile.objects.create(user=courier, is_approved=True)

        self.client.force_login(courier)

        response = self.client.get(
            reverse("home")
        )

        self.assertContains(
            response,
            reverse("courier:show_dashboard"),
        )

        self.client.logout()

        mitra = make_user(
            "navmitra",
            "mitra",
        )

        self.client.force_login(mitra)

        response = self.client.get(
            reverse("home")
        )

        self.assertContains(
            response,
            reverse("mitra_dashboard"),
        )

    def test_login_page(self):
        response = self.client.get(
            reverse("login")
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Masuk",
        )

    def test_login_error(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": "doesnotexist",
                "password": "wrongpassword",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Username atau password salah.",
        )
