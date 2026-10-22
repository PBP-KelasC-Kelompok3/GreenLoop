from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from .helpers import PLAIN_STATIC, make_user


@override_settings(STORAGES=PLAIN_STATIC)
class PickupHistoryTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user("sari"))
        self.res = self.client.get(reverse("courier:show_history"))

    def test_page_renders_rows_and_filters(self):
        self.assertEqual(self.res.status_code, 200)
        self.assertContains(self.res, "PK-0941")
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
        self.assertContains(self.res, "PK-0917 dibatalkan")

    def test_static_files_and_styles_exist(self):
        base = Path(settings.BASE_DIR) / "static" / "courier"
        self.assertTrue((base / "js/history.js").exists())
        css = (base / "css/courier.css").read_text(encoding="utf-8")
        for cls in (".hist-table", ".hist-chip", ".status--done", ".hist-note"):
            self.assertIn(cls, css)

    def test_no_separate_history_stylesheet(self):
        self.assertNotContains(self.res, "history.css")