"""Test Rekap Timbangan: tambah, lihat, ubah, hapus catatan timbangan (CRUD) milik kurir."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from courier.models import WeightLog, points_for
from courier.views import RECAP_PAGE_SIZE

from .helpers import PLAIN_STATIC, make_user


def valid_data(**override):
    data = {
        "partner_name": "Kafe Senja Margonda",
        "collected_at": timezone.localdate().isoformat(),
        "weight_kg": "58.6",
        "notes": "Pagi hari",
    }
    data.update(override)
    return data


def make_log(user, partner="Kafe Senja", kg="10.0", day=None, notes=""):
    return WeightLog.objects.create(
        courier=user, partner_name=partner, weight_kg=Decimal(kg),
        collected_at=day or timezone.localdate(), notes=notes)


@override_settings(STORAGES=PLAIN_STATIC)
class RecapTestBase(TestCase):
    def setUp(self):
        self.user = make_user("sari")
        self.other = make_user("andi")
        self.client.force_login(self.user)

    def create(self, **override):
        return self.client.post(reverse("courier:create_weight_log"), valid_data(**override))

    def update(self, pk, **override):
        return self.client.post(reverse("courier:update_weight_log", args=[pk]), valid_data(**override))

    def delete(self, pk):
        return self.client.post(reverse("courier:delete_weight_log", args=[pk]))


# ======================================================================
# Akses
# ======================================================================
class RecapAccessTests(RecapTestBase):
    URLS = (
        ("courier:show_recap", None),
        ("courier:recap_list", None),
        ("courier:create_weight_log", None),
        ("courier:update_weight_log", 1),
        ("courier:delete_weight_log", 1),
    )

    def url(self, name, arg):
        return reverse(name, args=[arg] if arg else [])

    def test_anonymous_cannot_access(self):
        self.client.logout()
        for name, arg in self.URLS:
            res = self.client.post(self.url(name, arg)) if "create" in name or "update" in name or "delete" in name \
                else self.client.get(self.url(name, arg))
            self.assertNotEqual(res.status_code, 200, name)
        self.assertEqual(WeightLog.objects.count(), 0)

    def test_non_courier_role_cannot_access(self):
        self.client.force_login(make_user("mitra1", role="partner"))
        self.assertNotEqual(self.client.get(reverse("courier:show_recap")).status_code, 200)
        self.assertNotEqual(self.create().status_code, 200)
        self.assertEqual(WeightLog.objects.count(), 0)

    def test_write_endpoints_reject_get(self):
        log = make_log(self.user)
        for name, arg in (("courier:create_weight_log", None), ("courier:update_weight_log", log.pk),
                          ("courier:delete_weight_log", log.pk)):
            self.assertEqual(self.client.get(self.url(name, arg)).status_code, 405, name)
        self.assertTrue(WeightLog.objects.filter(pk=log.pk).exists())

    def test_list_endpoint_rejects_post(self):
        self.assertEqual(self.client.post(reverse("courier:recap_list")).status_code, 405)


# ======================================================================
# Create
# ======================================================================
class CreateWeightLogTests(RecapTestBase):
    def test_creates_log_for_logged_in_courier(self):
        res = self.create()
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertIn("ditambahkan", data["message"])
        log = WeightLog.objects.get(pk=data["id"])
        self.assertEqual(log.courier, self.user)
        self.assertEqual(log.partner_name, "Kafe Senja Margonda")
        self.assertEqual(log.weight_kg, Decimal("58.6"))
        self.assertEqual(log.notes, "Pagi hari")
        self.assertEqual(log.points, 293)      # 58,6 x 5 seperti di desain

    def test_owner_cannot_be_forged_from_form(self):
        res = self.create(courier=self.other.pk)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(WeightLog.objects.get().courier, self.user)

    def test_notes_are_optional(self):
        self.assertEqual(self.create(notes="").status_code, 200)
        self.assertEqual(WeightLog.objects.get().notes, "")

    def test_invalid_weight_is_rejected(self):
        for bad in ("", "abc", "0", "0.0", "-5", "5000.1", "5001", "12.34"):
            res = self.create(weight_kg=bad)
            self.assertEqual(res.status_code, 400, bad)
            body = res.json()
            self.assertFalse(body["ok"])
            self.assertIn("weight_kg", body["errors"], bad)
        self.assertEqual(WeightLog.objects.count(), 0)

    def test_weight_boundaries_are_accepted(self):
        for ok in ("0.1", "5000"):
            self.assertEqual(self.create(weight_kg=ok).status_code, 200, ok)
        self.assertEqual(WeightLog.objects.count(), 2)

    def test_partner_name_required(self):
        res = self.create(partner_name="")
        self.assertEqual(res.status_code, 400)
        self.assertIn("partner_name", res.json()["errors"])
        self.assertEqual(WeightLog.objects.count(), 0)

    def test_date_required_and_must_be_valid(self):
        for bad in ("", "bukan-tanggal", "2026-13-40"):
            res = self.create(collected_at=bad)
            self.assertEqual(res.status_code, 400, bad)
            self.assertIn("collected_at", res.json()["errors"], bad)
        self.assertEqual(WeightLog.objects.count(), 0)

    def test_too_long_text_is_rejected(self):
        self.assertEqual(self.create(partner_name="x" * 121).status_code, 400)
        self.assertEqual(self.create(notes="x" * 201).status_code, 400)
        self.assertEqual(WeightLog.objects.count(), 0)


# ======================================================================
# Update
# ======================================================================
class UpdateWeightLogTests(RecapTestBase):
    def test_updates_own_log(self):
        log = make_log(self.user, "Lama", "10.0", notes="awal")
        res = self.update(log.pk, partner_name="Baru", weight_kg="12.5", notes="revisi")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])
        log.refresh_from_db()
        self.assertEqual((log.partner_name, log.weight_kg, log.notes), ("Baru", Decimal("12.5"), "revisi"))
        self.assertEqual(log.courier, self.user)
        self.assertEqual(WeightLog.objects.count(), 1)   # diubah, bukan dibuat baru

    def test_other_couriers_log_is_404_and_unchanged(self):
        log = make_log(self.other, "Milik andi", "10.0")
        res = self.update(log.pk, partner_name="Dibajak", weight_kg="99")
        self.assertEqual(res.status_code, 404)
        log.refresh_from_db()
        self.assertEqual((log.partner_name, log.weight_kg, log.courier), ("Milik andi", Decimal("10.0"), self.other))

    def test_unknown_id_is_404(self):
        self.assertEqual(self.update(9999).status_code, 404)

    def test_invalid_update_keeps_old_values(self):
        log = make_log(self.user, "Lama", "10.0")
        res = self.update(log.pk, weight_kg="0")
        self.assertEqual(res.status_code, 400)
        self.assertIn("weight_kg", res.json()["errors"])
        log.refresh_from_db()
        self.assertEqual(log.weight_kg, Decimal("10.0"))

    def test_owner_cannot_be_changed_by_update(self):
        log = make_log(self.user)
        self.update(log.pk, courier=self.other.pk)
        log.refresh_from_db()
        self.assertEqual(log.courier, self.user)


# ======================================================================
# Delete
# ======================================================================
class DeleteWeightLogTests(RecapTestBase):
    def test_deletes_own_log_only_that_one(self):
        keep, gone = make_log(self.user, "Tetap"), make_log(self.user, "Hapus")
        res = self.delete(gone.pk)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])
        self.assertFalse(WeightLog.objects.filter(pk=gone.pk).exists())
        self.assertTrue(WeightLog.objects.filter(pk=keep.pk).exists())

    def test_other_couriers_log_is_404_and_kept(self):
        log = make_log(self.other)
        self.assertEqual(self.delete(log.pk).status_code, 404)
        self.assertTrue(WeightLog.objects.filter(pk=log.pk).exists())

    def test_deleting_twice_gives_404(self):
        log = make_log(self.user)
        self.delete(log.pk)
        self.assertEqual(self.delete(log.pk).status_code, 404)


# ======================================================================
# Read: halaman, ringkasan, daftar per halaman
# (bagian ini membaca hasil filter dari recap.py; semua catatan memakai tanggal hari ini
#  supaya tetap masuk periode bawaan apa pun)
# ======================================================================
class RecapPageTests(RecapTestBase):
    def page(self, **params):
        return self.client.get(reverse("courier:show_recap"), params)

    def test_page_renders(self):
        res = self.page()
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "courier/weight_recap.html")

    def test_shows_only_own_logs(self):
        make_log(self.user, "Milik Sari", "5.0")
        make_log(self.other, "Milik Andi", "7.0")
        res = self.page()
        self.assertContains(res, "Milik Sari")
        self.assertNotContains(res, "Milik Andi")

    def test_summary_counts_only_own_logs(self):
        make_log(self.user, "A", "10.0")
        make_log(self.user, "B", "5.5")
        make_log(self.other, "C", "100.0")
        summary = self.page().context["summary"]
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["total"], Decimal("15.5"))
        self.assertEqual(summary["points"], points_for(Decimal("10.0")) + points_for(Decimal("5.5")))   # 50 + 28 (27,5 dibulatkan ke atas)
        self.assertEqual(summary["average"], Decimal("7.8"))     # 15,5 / 2 = 7,75 -> 7,8

    def test_points_round_half_up_in_page(self):
        make_log(self.user, "A", "0.5")      # 2,5 poin -> 3
        self.assertContains(self.page(), "+3")

    def test_empty_state(self):
        res = self.page()
        self.assertEqual(res.context["summary"]["count"], 0)
        self.assertEqual(len(res.context["page_obj"].object_list), 0)

    def test_numbers_use_indonesian_format(self):
        make_log(self.user, "A", "1234.5")
        res = self.page()
        self.assertContains(res, "1.234,5")
        self.assertNotContains(res, "1234.5 kg")

    def test_newest_first(self):
        today = timezone.localdate()
        make_log(self.user, "Kemarin", "1.0", day=today - timedelta(days=1))
        make_log(self.user, "Hari ini", "1.0", day=today)
        names = [log.partner_name for log in self.page().context["page_obj"]]
        self.assertEqual(names[:2], ["Hari ini", "Kemarin"])

    def test_pagination(self):
        for i in range(RECAP_PAGE_SIZE + 1):
            make_log(self.user, f"Mitra {i}", "1.0")
        first, second = self.page().context["page_obj"], self.page(page=2).context["page_obj"]
        self.assertEqual(len(first.object_list), RECAP_PAGE_SIZE)
        self.assertEqual(len(second.object_list), 1)
        self.assertEqual(first.paginator.count, RECAP_PAGE_SIZE + 1)
        self.assertEqual(self.page().context["summary"]["count"], RECAP_PAGE_SIZE + 1)   # ringkasan = semua halaman

    def test_bad_page_numbers_do_not_crash(self):
        make_log(self.user)
        for bad in ("abc", "0", "-1", "999", ""):
            self.assertEqual(self.page(page=bad).status_code, 200, bad)

    def test_new_log_appears_on_page_after_create(self):
        self.create(partner_name="Warung Baru", weight_kg="3.3")
        res = self.page()
        self.assertContains(res, "Warung Baru")
        self.assertContains(res, "3,3 kg")

    def test_edit_and_delete_buttons_point_to_own_endpoints(self):
        log = make_log(self.user, "Kafe X")
        res = self.page()
        self.assertContains(res, reverse("courier:update_weight_log", args=[log.pk]))
        self.assertContains(res, reverse("courier:delete_weight_log", args=[log.pk]))


class RecapListAjaxTests(RecapTestBase):
    def test_returns_html_fragment_with_own_data_only(self):
        make_log(self.user, "Milik Sari", "5.0")
        make_log(self.other, "Milik Andi", "7.0")
        res = self.client.get(reverse("courier:recap_list"))
        self.assertEqual(res.status_code, 200)
        html = res.json()["html"]
        self.assertIn("Milik Sari", html)
        self.assertNotIn("Milik Andi", html)

    def test_fragment_matches_summary(self):
        make_log(self.user, "A", "10.0")
        html = self.client.get(reverse("courier:recap_list")).json()["html"]
        self.assertIn("10,0 kg", html)
        self.assertIn("Jumlah penimbangan", html)


# ======================================================================
# Hubungan dengan fitur lain
# ======================================================================
class RecapIntegrationTests(RecapTestBase):
    def test_profile_stats_follow_recap_changes(self):
        from courier.utils import get_courier_stats
        res = self.create(weight_kg="10.0")
        self.assertEqual(get_courier_stats(self.user)["pickups_done"], 1)
        self.update(res.json()["id"], weight_kg="20.0")
        self.assertEqual(get_courier_stats(self.user)["total_kg"], Decimal("20.0"))
        self.delete(res.json()["id"])
        self.assertEqual(get_courier_stats(self.user)["pickups_done"], 0)

    def test_deleting_user_removes_logs(self):
        make_log(self.user)
        self.user.delete()
        self.assertEqual(WeightLog.objects.count(), 0)