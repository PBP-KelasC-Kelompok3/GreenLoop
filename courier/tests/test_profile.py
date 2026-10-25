from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import resolve, reverse

from ..forms import CourierPasswordForm, CourierProfileForm
from ..models import CourierProfile
from ..utils import (
    build_topbar_sub,
    format_date_id,
    get_courier_stats,
    get_display_name,
    get_initials,
    profile_payload,
)
from .helpers import PLAIN_STATIC, make_user

VALID_PROFILE = {
    "full_name": "Budi Santoso",
    "email": "budi@greenloop.id",
    "plate_number": "B 1234 KZT",
    "vehicle_type": "pickup_bak",
}

NEW_PASSWORD = "Sandi-Baru-9876"


# ======================================================================
# Model
# ======================================================================
class CourierProfileModelTests(TestCase):
    def setUp(self):
        self.user = make_user(first_name="Budi Santoso")

    def test_default_values(self):
        profile = CourierProfile.objects.create(user=self.user)
        self.assertEqual(profile.vehicle_type, CourierProfile.VehicleType.PICKUP_BAK)
        self.assertFalse(profile.is_on_duty)
        self.assertEqual(profile.plate_number, "")

    def test_str_with_and_without_plate(self):
        profile = CourierProfile.objects.create(user=self.user, plate_number="B 1234 KZT")
        self.assertEqual(str(profile), "budi (B 1234 KZT)")
        profile.plate_number = ""
        self.assertEqual(str(profile), "budi (-)")

    def test_one_profile_per_user(self):
        CourierProfile.objects.create(user=self.user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CourierProfile.objects.create(user=self.user)

    def test_deleted_with_user(self):
        CourierProfile.objects.create(user=self.user)
        self.user.delete()
        self.assertEqual(CourierProfile.objects.count(), 0)

    def test_vehicle_labels(self):
        profile = CourierProfile.objects.create(user=self.user, vehicle_type="motor_box")
        self.assertEqual(profile.get_vehicle_type_display(), "Motor Box")


# ======================================================================
# Fungsi bantu (utils.py)
# ======================================================================
class UtilsTests(TestCase):
    def test_display_name_prefers_full_name(self):
        user = make_user(first_name="Budi", last_name="Santoso")
        self.assertEqual(get_display_name(user), "Budi Santoso")

    def test_display_name_falls_back_to_username(self):
        self.assertEqual(get_display_name(make_user("budi123")), "budi123")

    def test_initials(self):
        cases = [
            ({"first_name": "Budi", "last_name": "Santoso"}, "BS"),
            ({"first_name": "Budi Eko Santoso"}, "BS"),   # kata pertama + terakhir
            ({"first_name": "budi"}, "BU"),               # satu kata -> 2 huruf
        ]
        for i, (fields, expected) in enumerate(cases):
            with self.subTest(expected=expected):
                user = make_user(f"u{i}", **fields)
                self.assertEqual(get_initials(user), expected)

    def test_initials_falls_back_to_username(self):
        self.assertEqual(get_initials(make_user("rina")), "RI")

    def test_format_date_id_uses_indonesian_month(self):
        self.assertEqual(format_date_id(datetime(2026, 10, 20)), "20 Okt 2026")
        self.assertEqual(format_date_id(datetime(2026, 5, 1)), "1 Mei 2026")
        self.assertEqual(format_date_id(datetime(2026, 8, 17)), "17 Agu 2026")

    def test_topbar_sub(self):
        user = make_user()
        with_plate = CourierProfile(user=user, plate_number="B 1234 KZT")
        no_plate = CourierProfile(user=user, plate_number="")
        self.assertEqual(build_topbar_sub(with_plate), "Kurir · B 1234 KZT")
        self.assertEqual(build_topbar_sub(no_plate), "Kurir")

    def test_profile_payload_keys_match_template_bindings(self):
        user = make_user(first_name="Budi Santoso")
        profile = CourierProfile.objects.create(
            user=user, plate_number="B 1234 KZT", vehicle_type="motor_box")
        payload = profile_payload(user, profile)
        self.assertEqual(payload["display_name"], "Budi Santoso")
        self.assertEqual(payload["initials"], "BS")
        self.assertEqual(payload["email"], "budi@greenloop.id")
        self.assertEqual(payload["plate_number"], "B 1234 KZT")
        self.assertEqual(payload["vehicle_label"], "Motor Box")
        self.assertEqual(payload["topbar_sub"], "Kurir · B 1234 KZT")

    def test_stats_placeholder_shape(self):
        stats = get_courier_stats(make_user())
        self.assertEqual(set(stats), {"pickups_done", "total_kg", "points"})


# ======================================================================
# Form edit profil
# ======================================================================
class CourierProfileFormTests(TestCase):
    def setUp(self):
        self.user = make_user(first_name="Budi Santoso")

    def form(self, **overrides):
        return CourierProfileForm({**VALID_PROFILE, **overrides}, user=self.user)

    def test_valid_data(self):
        self.assertTrue(self.form().is_valid())

    def test_required_fields_have_indonesian_messages(self):
        form = CourierProfileForm({}, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["full_name"], ["Nama lengkap wajib diisi."])
        self.assertEqual(form.errors["email"], ["Email wajib diisi."])
        self.assertEqual(form.errors["plate_number"], ["Plat nomor wajib diisi."])
        self.assertEqual(form.errors["vehicle_type"], ["Jenis armada wajib dipilih."])

    def test_full_name_whitespace_is_collapsed(self):
        form = self.form(full_name="  Budi    Santoso  ")
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["full_name"], "Budi Santoso")

    def test_email_is_lowercased(self):
        form = self.form(email="BUDI@GreenLoop.ID")
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["email"], "budi@greenloop.id")

    def test_invalid_email_format(self):
        form = self.form(email="bukan-email")
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["email"], ["Format email tidak valid."])

    def test_email_used_by_other_user_is_rejected(self):
        make_user("lain")
        form = self.form(email="LAIN@greenloop.id")   
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["email"], ["Email sudah dipakai akun lain."])

    def test_own_email_is_allowed(self):
        self.assertTrue(self.form(email=self.user.email).is_valid())

    def test_plate_is_normalized(self):
        form = self.form(plate_number="  b   1234  kzt ")
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["plate_number"], "B 1234 KZT")

    def test_plate_formats(self):
        for plate, ok in [
            ("B 1234 KZT", True), ("D 12 AB", True), ("B1234KZT", True),
            ("1234 B", False), ("ABC", False), ("B 12345678", False), ("B-1234", False),
        ]:
            with self.subTest(plate=plate):
                self.assertEqual(self.form(plate_number=plate).is_valid(), ok)

    def test_invalid_plate_message(self):
        form = self.form(plate_number="????")
        self.assertFalse(form.is_valid())
        self.assertIn("Format plat nomor tidak valid", form.errors["plate_number"][0])

    def test_invalid_vehicle_choice(self):
        form = self.form(vehicle_type="helikopter")
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["vehicle_type"], ["Pilih jenis armada yang tersedia."])

    def test_save_updates_user_and_creates_profile(self):
        form = self.form(full_name="Budi Eko", email="baru@greenloop.id",
                         plate_number="d 12 ab", vehicle_type="motor_box")
        self.assertTrue(form.is_valid())
        profile = form.save()

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Budi Eko")
        self.assertEqual(self.user.last_name, "")
        self.assertEqual(self.user.email, "baru@greenloop.id")
        self.assertEqual(profile.plate_number, "D 12 AB")
        self.assertEqual(profile.vehicle_type, "motor_box")
        self.assertEqual(CourierProfile.objects.filter(user=self.user).count(), 1)


# ======================================================================
# Form ganti kata sandi
# ======================================================================
class CourierPasswordFormTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_valid(self):
        form = CourierPasswordForm(self.user, {
            "old_password": "pw12345!",
            "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})
        self.assertTrue(form.is_valid())

    def test_error_messages_are_indonesian(self):
        form = CourierPasswordForm(self.user, {
            "old_password": "salah",
            "new_password1": NEW_PASSWORD, "new_password2": "beda-sekali-1"})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["old_password"], ["Kata sandi saat ini salah."])
        self.assertEqual(form.errors["new_password2"],
                         ["Kata sandi baru dan konfirmasi tidak sama."])

    def test_required_message(self):
        form = CourierPasswordForm(self.user, {})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["old_password"], ["Wajib diisi."])


# ======================================================================
# URL
# ======================================================================
class CourierUrlTests(TestCase):
    def test_reverse_paths(self):
        self.assertEqual(reverse("courier:show_profile"), "/courier/profile/")
        self.assertEqual(reverse("courier:update_profile"), "/courier/profile/edit/")
        self.assertEqual(reverse("courier:change_password"), "/courier/profile/password/")

    def test_paths_resolve_to_views(self):
        for path, name in [
            ("/courier/profile/", "show_profile"),
            ("/courier/profile/edit/", "update_profile"),
            ("/courier/profile/password/", "change_password"),
        ]:
            with self.subTest(path=path):
                self.assertEqual(resolve(path).func.__name__, name)


# ======================================================================
# Akses (login + role)
# ======================================================================
@override_settings(STORAGES=PLAIN_STATIC)
class ProfileAccessTests(TestCase):
    URLS = ["courier:show_profile", "courier:update_profile", "courier:change_password"]

    def test_anonymous_is_sent_to_login(self):
        for name in self.URLS:
            with self.subTest(url=name):
                res = self.client.get(reverse(name))
                self.assertEqual(res.status_code, 302)
                self.assertIn("login", res.url)

    def test_non_courier_roles_are_redirected_home(self):
        for role in ("consumer", "mitra"):
            user = make_user(f"u_{role}", role=role)
            self.client.force_login(user)
            for name in self.URLS:
                with self.subTest(role=role, url=name):
                    self.assertRedirects(
                        self.client.get(reverse(name)), reverse("home"),
                        fetch_redirect_response=False)

    def test_non_courier_cannot_post_edits(self):
        user = make_user("mitra1", role="mitra", first_name="Asli")
        self.client.force_login(user)
        self.client.post(reverse("courier:update_profile"), VALID_PROFILE)
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Asli")
        self.assertFalse(CourierProfile.objects.filter(user=user).exists())

    def test_courier_can_open_page(self):
        self.client.force_login(make_user())
        self.assertEqual(self.client.get(reverse("courier:show_profile")).status_code, 200)


# ======================================================================
# Halaman profil (view + template)
# ======================================================================
@override_settings(STORAGES=PLAIN_STATIC)
class ShowProfileTests(TestCase):
    def setUp(self):
        self.user = make_user(first_name="Budi Santoso")
        self.profile = CourierProfile.objects.create(
            user=self.user, plate_number="B 1234 KZT",
            vehicle_type="motor_box", is_on_duty=True)
        User.objects.filter(pk=self.user.pk).update(
            date_joined=datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc))
        self.client.force_login(self.user)
        self.res = self.client.get(reverse("courier:show_profile"))

    def test_uses_profile_template(self):
        self.assertTemplateUsed(self.res, "courier/profile.html")
        self.assertTemplateUsed(self.res, "courier/base_courier.html")

    def test_context(self):
        ctx = self.res.context
        self.assertEqual(ctx["profile"], self.profile)
        self.assertEqual(ctx["display_name"], "Budi Santoso")
        self.assertEqual(ctx["joined_display"], "20 Okt 2026")
        self.assertEqual(ctx["stats"], get_courier_stats(self.user))
        self.assertEqual(list(ctx["vehicle_choices"]),
                         list(CourierProfile.VehicleType.choices))

    def test_shows_user_data(self):
        for text in ("Budi Santoso", "@budi", "budi@greenloop.id",
                     "B 1234 KZT", "Motor Box", "20 Okt 2026", "Kurir Lapangan"):
            with self.subTest(text=text):
                self.assertContains(self.res, text)

    def test_avatar_shows_initials(self):
        self.assertContains(self.res, ">BS</div>")

    def test_status_pill_on_duty(self):
        self.assertContains(self.res, "Sedang Bertugas")
        self.assertNotContains(self.res, "Tidak Bertugas")

    def test_status_pill_off_duty(self):
        self.profile.is_on_duty = False
        self.profile.save()
        res = self.client.get(reverse("courier:show_profile"))
        self.assertContains(res, "Tidak Bertugas")
        self.assertNotContains(res, "Sedang Bertugas")

    def test_stats_cards_present(self):
        for label in ("Pikap selesai", "Total kg", "Waste Points"):
            self.assertContains(self.res, label)

    def test_accordion_sections_start_closed(self):
        self.assertContains(self.res, "Akun &amp; Keamanan")
        self.assertContains(self.res, "Edit Profil")
        self.assertContains(self.res, "Ganti Kata Sandi")
        self.assertContains(self.res, 'aria-expanded="false"', count=3)
        self.assertContains(self.res, 'id="panel-security" class="accordion-group" hidden')

    def test_forms_point_to_endpoints_and_have_csrf(self):
        self.assertContains(self.res, f'action="{reverse("courier:update_profile")}"')
        self.assertContains(self.res, f'action="{reverse("courier:change_password")}"')
        self.assertContains(self.res, "csrfmiddlewaretoken", count=2)

    def test_edit_form_is_prefilled(self):
        self.assertContains(self.res, 'name="full_name"')
        self.assertContains(self.res, 'value="Budi Santoso"')
        self.assertContains(self.res, 'value="B 1234 KZT"')

    def test_current_vehicle_is_selected(self):
        self.assertContains(self.res, '<option value="motor_box" selected>Motor Box</option>')
        self.assertNotContains(self.res, '<option value="pickup_bak" selected>')

    def test_page_works_without_existing_profile(self):
        """CourierProfile dibuat otomatis saat halaman pertama dibuka."""
        user = make_user("baru")
        self.client.force_login(user)
        res = self.client.get(reverse("courier:show_profile"))
        self.assertEqual(res.status_code, 200)
        self.assertTrue(CourierProfile.objects.filter(user=user).exists())
        self.assertContains(res, "Tidak Bertugas")

    def test_empty_email_and_plate_show_dash(self):
        user = make_user("kosong")
        User.objects.filter(pk=user.pk).update(email="")
        self.client.force_login(user)
        res = self.client.get(reverse("courier:show_profile"))
        self.assertContains(res, 'data-bind="email">-</dd>')
        self.assertContains(res, 'data-bind="plate_number">-</dd>')

    def test_binding_hooks_match_payload_keys(self):
        """Setiap data-bind di template harus ada di data yang dikirim AJAX."""
        payload = profile_payload(self.user, self.profile)
        for key in ("initials", "display_name", "email", "plate_number", "vehicle_label"):
            with self.subTest(key=key):
                self.assertIn(key, payload)
                self.assertContains(self.res, f'data-bind="{key}"')

    def test_loads_profile_script(self):
        self.assertContains(self.res, "courier/js/profile.js")


# ======================================================================
# Endpoint AJAX edit profil
# ======================================================================
@override_settings(STORAGES=PLAIN_STATIC)
class UpdateProfileEndpointTests(TestCase):
    def setUp(self):
        self.user = make_user(first_name="Budi Santoso")
        self.client.force_login(self.user)
        self.url = reverse("courier:update_profile")

    def test_success_saves_and_returns_payload(self):
        res = self.client.post(self.url, {
            "full_name": "Budi Eko", "email": "Baru@GreenLoop.id",
            "plate_number": "d 12 ab", "vehicle_type": "motor_box"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["message"], "Profil berhasil diperbarui.")
        self.assertEqual(body["data"]["display_name"], "Budi Eko")
        self.assertEqual(body["data"]["initials"], "BE")
        self.assertEqual(body["data"]["email"], "baru@greenloop.id")
        self.assertEqual(body["data"]["plate_number"], "D 12 AB")
        self.assertEqual(body["data"]["vehicle_label"], "Motor Box")
        self.assertEqual(body["data"]["topbar_sub"], "Kurir · D 12 AB")

        self.user.refresh_from_db()
        profile = CourierProfile.objects.get(user=self.user)
        self.assertEqual(self.user.first_name, "Budi Eko")
        self.assertEqual(profile.plate_number, "D 12 AB")
        self.assertEqual(profile.vehicle_type, "motor_box")

    def test_invalid_returns_400_with_errors_per_field(self):
        res = self.client.post(self.url, {
            "full_name": "", "email": "salah", "plate_number": "????",
            "vehicle_type": "x"})
        self.assertEqual(res.status_code, 400)
        body = res.json()
        self.assertFalse(body["ok"])
        self.assertEqual(set(body["errors"]),
                         {"full_name", "email", "plate_number", "vehicle_type"})
        self.assertIsInstance(body["errors"]["email"], list)

    def test_invalid_does_not_change_data(self):
        self.client.post(self.url, {**VALID_PROFILE, "plate_number": "????"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Budi Santoso")
        self.assertFalse(CourierProfile.objects.filter(user=self.user).exists())

    def test_email_taken_by_other_user(self):
        make_user("lain", first_name="Lain")
        res = self.client.post(self.url, {**VALID_PROFILE, "email": "lain@greenloop.id"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["errors"]["email"], ["Email sudah dipakai akun lain."])

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_updated_name_shows_on_page(self):
        self.client.post(self.url, {**VALID_PROFILE, "full_name": "Rina Wati"})
        res = self.client.get(reverse("courier:show_profile"))
        self.assertContains(res, "Rina Wati")
        self.assertContains(res, ">RW</div>")


# ======================================================================
# Endpoint AJAX ganti kata sandi
# ======================================================================
@override_settings(STORAGES=PLAIN_STATIC)
class ChangePasswordEndpointTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.url = reverse("courier:change_password")

    def post(self, **overrides):
        data = {"old_password": "pw12345!",
                "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
        return self.client.post(self.url, {**data, **overrides})

    def test_success_changes_password(self):
        res = self.post()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"ok": True, "message": "Kata sandi berhasil diganti."})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_session_stays_logged_in(self):
        self.post()
        self.assertEqual(self.client.get(reverse("courier:show_profile")).status_code, 200)

    def test_wrong_old_password(self):
        res = self.post(old_password="salah")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["errors"]["old_password"], ["Kata sandi saat ini salah."])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("pw12345!"))

    def test_confirmation_mismatch(self):
        res = self.post(new_password2="beda-sekali-1")
        self.assertEqual(res.status_code, 400)
        self.assertIn("new_password2", res.json()["errors"])

    def test_weak_password_rejected(self):
        res = self.post(new_password1="12345", new_password2="12345")
        self.assertEqual(res.status_code, 400)
        self.assertIn("new_password2", res.json()["errors"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("pw12345!"))

    def test_missing_fields(self):
        res = self.client.post(self.url, {})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(set(res.json()["errors"]),
                         {"old_password", "new_password1", "new_password2"})

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)


# ======================================================================
# File statis & komponen
# ======================================================================
class ProfileStaticFilesTests(TestCase):
    def test_static_files_exist(self):
        base = Path(settings.BASE_DIR) / "static" / "courier"
        for rel in ("css/courier.css", "js/profile.js", "js/layout.js"):
            with self.subTest(file=rel):
                self.assertTrue((base / rel).exists())

    def test_profile_css_has_main_classes(self):
        css = (Path(settings.BASE_DIR) / "static/courier/css/courier.css").read_text(encoding="utf-8")
        for cls in (".profile-card", ".profile-header", ".accordion-toggle",
                    ".form-message", ".field-input", ".btn-submit"):
            with self.subTest(cls=cls):
                self.assertIn(cls, css)

    def test_profile_js_targets_exist_in_template(self):
        """Selector penting di JavaScript harus ada di template."""
        tpl = (Path(settings.BASE_DIR) / "templates/courier/profile.html").read_text(encoding="utf-8")
        for hook in ("data-accordion-toggle", "data-ajax-form",
                     "data-form-message", "data-error-for", "data-reset-on-success"):
            with self.subTest(hook=hook):
                self.assertIn(hook, tpl)