from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import UserProfile

# Test runner memakai DEBUG=False; storage manifest butuh collectstatic.
PLAIN_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def make_user(username, role):
    user = User.objects.create_user(username, password="pw12345!")
    UserProfile.objects.filter(user=user).update(role=role)
    return user


@override_settings(STORAGES=PLAIN_STATIC)
class LoginRedirectTests(TestCase):
    def login(self, username, password="pw12345!"):
        return self.client.post(
            reverse("login"), {"username": username, "password": password})

    def test_courier_goes_straight_to_courier_dashboard(self):
        make_user("kurir1", "courier")
        res = self.login("kurir1")
        self.assertRedirects(res, reverse("courier:show_dashboard"),
                             fetch_redirect_response=False)

    def test_courier_dashboard_opens_after_login(self):
        make_user("kurir1", "courier")
        res = self.client.post(
            reverse("login"), {"username": "kurir1", "password": "pw12345!"},
            follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "courier/dashboard.html")

    def test_other_roles_go_home(self):
        for role in ("consumer", "mitra"):
            with self.subTest(role=role):
                make_user(f"u_{role}", role)
                self.assertRedirects(self.login(f"u_{role}"), reverse("home"),
                                     fetch_redirect_response=False)
                self.client.logout()

    def test_wrong_password_stays_on_login(self):
        make_user("kurir1", "courier")
        res = self.login("kurir1", password="salah")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Username atau password salah.")

    def register(self, role):
        return self.client.post(reverse("register"), {
            "username": f"baru_{role}", "email": f"baru_{role}@x.id", "role": role,
            "password1": "Sandi-Baru-9876", "password2": "Sandi-Baru-9876"})

    def test_register_as_courier_goes_to_courier_dashboard(self):
        self.assertRedirects(self.register("courier"),
                             reverse("courier:show_dashboard"),
                             fetch_redirect_response=False)

    def test_register_as_consumer_goes_home(self):
        self.assertRedirects(self.register("consumer"), reverse("home"),
                             fetch_redirect_response=False)