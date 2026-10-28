from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from courier.models import PickupRecord

from .helpers import PLAIN_STATIC, make_user


def make_record(courier, code, date, status, actual=None, note="", **extra):
    values = dict(slot="08.00–10.00", partner_name="Kafe Senja", area="Beji", est_kg=5, vehicle="Motor Box")
    values.update(extra)
    return PickupRecord.objects.create(
        courier=courier, code=code, date=date, status=status, actual_kg=actual, note=note, **values)


@override_settings(STORAGES=PLAIN_STATIC)
class PickupHistoryTests(TestCase):
    def setUp(self):
        self.user = make_user("sari")
        self.client.force_login(self.user)
        make_record(self.user, "TJ-0001", "2026-10-06", "scheduled")
        make_record(self.user, "TJ-0002", "2026-09-26", "done", actual="35.2")
        make_record(self.user, "TJ-0003", "2026-09-12", "cancelled", note="Foto limbah tercampur plastik.",
                    partner_name="Resto Sari Rasa")
        self.res = self.client.get(reverse("courier:show_history"))

    def test_page_renders_rows_and_filters(self):
        self.assertEqual(self.res.status_code, 200)
        self.assertContains(self.res, "TJ-0001")
        for key in ("all", "scheduled", "ongoing", "done", "cancelled"):
            self.assertContains(self.res, f'data-filter="{key}"')

    def test_counts_match_rows(self):
        total = len(self.res.context["rows"])
        self.assertEqual(self.res.context["total"], total)
        self.assertEqual(sum(n for _, _, n in self.res.context["filters"]), total)

    def test_weight_uses_decimal_comma(self):
        self.assertContains(self.res, "35,2 kg")
        self.assertNotContains(self.res, "35.2 kg")

    def test_cancelled_note_shown(self):
        self.assertContains(self.res, "TJ-0003 dibatalkan")
        self.assertContains(self.res, "Foto limbah tercampur plastik.")

    def test_static_files_and_styles_exist(self):
        base = Path(settings.BASE_DIR) / "static" / "courier"
        self.assertTrue((base / "js/history.js").exists())
        css = (base / "css/courier.css").read_text(encoding="utf-8")
        for cls in (".hist-table", ".hist-chip", ".status--done", ".hist-note"):
            self.assertIn(cls, css)

    def test_no_separate_history_stylesheet(self):
        self.assertNotContains(self.res, "history.css")

    def test_empty_history_has_no_dummy_rows(self):
        PickupRecord.objects.all().delete()
        res = self.client.get(reverse("courier:show_history"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["total"], 0)
        self.assertNotContains(res, "PK-0")
        self.assertNotContains(res, "dibatalkan ·")