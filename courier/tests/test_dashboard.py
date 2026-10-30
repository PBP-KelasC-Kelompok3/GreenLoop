"""Test Dashboard Kurir: perhitungan data per periode dan halamannya."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from courier.dashboard import (
    WIB, build_chart, build_composition, build_dashboard, build_map, delta_badge,
    fmt_number, period_bounds, _nice_step,
)
from courier.models import PickupRecord
from courier.route_state import Stop
from scheduling.models import MitraProfile, PickupSchedule

from .helpers import PLAIN_STATIC, make_user
from .test_route import RouteTestBase

TODAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 25, 7, 9, tzinfo=WIB)


def rec(user, code, day, kg, status="done", partner="Kafe A", **extra):
    return PickupRecord.objects.create(
        courier=user, code=code, date=day, partner_name=partner, status=status,
        actual_kg=None if kg is None else Decimal(str(kg)), est_kg=5, **extra)


class FormatTests(TestCase):
    def test_indonesian_number_format(self):
        self.assertEqual(fmt_number(12480), "12.480")
        self.assertEqual(fmt_number(Decimal("7.5")), "7,5")
        self.assertEqual(fmt_number(Decimal("58.60")), "58,6")
        self.assertEqual(fmt_number(0), "0")
        self.assertEqual(fmt_number(Decimal("1234.567"), 1), "1.234,6")

    def test_delta_badge(self):
        self.assertEqual(delta_badge(110, 100), {"text": "+10,0%", "tone": "up"})
        self.assertEqual(delta_badge(Decimal("90"), Decimal("100")), {"text": "−10,0%", "tone": "down"})
        self.assertEqual(delta_badge(100, 100), {"text": "+0,0%", "tone": "up"})
        self.assertIsNone(delta_badge(5, 0))     # tanpa pembanding: tidak ada lencana
        self.assertIsNone(delta_badge(0, 0))

    def test_nice_step(self):
        self.assertEqual(_nice_step(3), 5)
        self.assertEqual(_nice_step(7), 10)
        self.assertEqual(_nice_step(0.3), 0.5)
        self.assertEqual(_nice_step(1200), 2000)
        self.assertEqual(_nice_step(0), 1)


class PeriodTests(TestCase):
    def test_seven_days(self):
        start, end, ps, pe, monthly = period_bounds("7", TODAY)
        self.assertEqual((start, end), (date(2026, 10, 19), TODAY))
        self.assertEqual((ps, pe), (date(2026, 10, 12), date(2026, 10, 18)))
        self.assertFalse(monthly)

    def test_thirty_days(self):
        start, _, ps, pe, _ = period_bounds("30", TODAY)
        self.assertEqual((TODAY - start).days, 29)
        self.assertEqual(pe, start - timedelta(days=1))
        self.assertEqual((pe - ps).days, 29)

    def test_twelve_months_cross_year(self):
        start, end, ps, pe, monthly = period_bounds("365", date(2026, 2, 10))
        self.assertEqual(start, date(2025, 3, 1))
        self.assertEqual(ps, date(2024, 3, 1))
        self.assertEqual(pe, date(2025, 2, 28))
        self.assertTrue(monthly)


class ChartTests(TestCase):
    def setUp(self):
        self.user = make_user("sari")

    def test_monthly_bars_sum_per_month(self):
        rec(self.user, "A", date(2026, 10, 3), 10)
        rec(self.user, "B", date(2026, 10, 20), 15)
        rec(self.user, "C", date(2026, 9, 1), 4)
        start, end, *_ = period_bounds("365", TODAY)
        chart = build_chart(list(PickupRecord.objects.all()), start, end, True)
        self.assertEqual(len(chart["bars"]), 12)
        last, before = chart["bars"][-1], chart["bars"][-2]
        self.assertEqual(last["tip_value"], "25 kg")
        self.assertEqual(last["tip_title"], "Oktober 2026")
        self.assertTrue(last["is_last"])
        self.assertEqual(before["tip_value"], "4 kg")
        self.assertEqual([b["label"] for b in chart["bars"]][-2:], ["Sep", "Okt"])
        self.assertEqual(sum(1 for b in chart["bars"] if b["is_last"]), 1)

    def test_tallest_bar_fits_in_axis_and_ticks_cover_it(self):
        rec(self.user, "A", date(2026, 10, 3), 30)
        start, end, *_ = period_bounds("365", TODAY)
        chart = build_chart(list(PickupRecord.objects.all()), start, end, True)
        self.assertEqual([t["value"] for t in chart["ticks"]], ["0", "10", "20", "30", "40"])
        self.assertAlmostEqual(chart["bars"][-1]["height"], 75, places=1)

    def test_daily_bars(self):
        rec(self.user, "A", TODAY, 2)
        start, end, *_ = period_bounds("7", TODAY)
        chart = build_chart(list(PickupRecord.objects.all()), start, end, False)
        self.assertEqual(len(chart["bars"]), 7)
        self.assertEqual(chart["bars"][-1]["tip_value"], "2 kg")
        self.assertEqual(chart["bars"][0]["tip_title"], "19 Okt 2026")

    def test_thirty_day_labels_are_thinned(self):
        start, end, *_ = period_bounds("30", TODAY)
        chart = build_chart([], start, end, False)
        shown = [b["label"] for b in chart["bars"] if b["label"]]
        self.assertLess(len(shown), 10)
        self.assertEqual(chart["bars"][-1]["label"], "25 Okt")   # hari terakhir selalu berlabel

    def test_empty_chart_still_has_axis(self):
        start, end, *_ = period_bounds("365", TODAY)
        chart = build_chart([], start, end, True)
        self.assertEqual(len(chart["ticks"]), 5)
        self.assertTrue(all(b["height"] == 0 for b in chart["bars"]))


class CompositionTests(TestCase):
    def setUp(self):
        self.user = make_user("sari")
        self.schedules = {}
        for code, cat in (("T1", "Kafe"), ("T2", "Restoran"), ("T3", "Hotel"), ("T4", "Toko roti"), ("T5", "Pujasera")):
            mitra = make_user(f"mitra_{code}", role="mitra")
            MitraProfile.objects.create(user=mitra, business_name=code, business_type=cat)
            self.schedules[code] = PickupSchedule.objects.create(
                mitra=mitra, estimated_weight=5, pickup_date=TODAY,
                pickup_time_slot="08:00-10:00", status="COMPLETED",
            )

    def pickup_record(self, code, day, kg):
        source = self.schedules[code]
        # PickupRecord has a OneToOne link to a single real pickup schedule.
        # Each historical record therefore needs its own schedule fixture.
        schedule = PickupSchedule.objects.create(
            mitra=source.mitra,
            estimated_weight=source.estimated_weight,
            pickup_date=day,
            pickup_time_slot=source.pickup_time_slot,
            status="COMPLETED",
        )
        return rec(self.user, code, day, kg, pickup_schedule=schedule)

    def test_groups_by_partner_type_not_waste_type(self):
        self.pickup_record("T1", date(2026, 10, 1), 6)
        self.pickup_record("T2", date(2026, 10, 2), 3)
        self.pickup_record("T2", date(2026, 10, 3), 1)
        comp = build_composition(list(PickupRecord.objects.all()))
        self.assertEqual(comp, [{"label": "Kafe", "percent": 60}, {"label": "Restoran", "percent": 40}])

    def test_extra_types_folded_into_lainnya(self):
        for i, code in enumerate(("T1", "T2", "T3", "T4", "T5")):
            self.pickup_record(code, date(2026, 10, 1 + i), 10 - i)
        comp = build_composition(list(PickupRecord.objects.all()))
        self.assertEqual(len(comp), 4)
        self.assertEqual(comp[-1]["label"], "Lainnya")
        self.assertEqual(sum(c["percent"] for c in comp), 100)

    def test_unknown_code_goes_to_lainnya_and_empty_is_empty(self):
        rec(self.user, "ZZZ", date(2026, 10, 1), 5)
        self.assertEqual(build_composition(list(PickupRecord.objects.all())), [{"label": "Lainnya", "percent": 100}])
        self.assertEqual(build_composition([]), [])

    def test_percentages_always_total_100(self):
        from courier.dashboard import _percentages
        for values in ([1, 1, 1], [1, 1, 1, 1, 1, 1, 1], [Decimal("3.3"), Decimal("3.3"), Decimal("3.4")], [5], [2, 1]):
            result = _percentages([Decimal(str(v)) for v in values])
            self.assertEqual(sum(result), 100, values)
        self.assertEqual(_percentages([Decimal(1)]), [100])

    def test_no_waste_type_wording(self):
        from courier import dashboard
        self.assertFalse(hasattr(dashboard, "WASTE_BY_CATEGORY"))


def stop(i, lat, lng, status="approved"):
    from datetime import time
    return Stop(pk=i, code=f"T{i}", name=f"Mitra {i}", address="x", slot_start=time(8), slot_end=time(10),
                est_kg=3, vehicle="Motor Box", latitude=lat, longitude=lng, photo_note="", status=status)


class MapTests(TestCase):
    def test_empty(self):
        self.assertEqual(build_map([]), {"pins": [], "path": ""})

    def test_pins_stay_inside_free_area(self):
        stops = [stop(1, -6.37, 106.80), stop(2, -6.42, 106.86), stop(3, -6.39, 106.83), stop(4, -6.41, 106.88)]
        pins = build_map(stops)["pins"]
        self.assertEqual([p["num"] for p in pins], [1, 2, 3, 4])
        for p in pins:
            self.assertTrue(8 <= p["x"] <= 92, p)
            self.assertTrue(24 <= p["y"] <= 60, p)   # tidak menabrak label atas dan kartu bawah

    def test_north_is_up_and_east_is_right(self):
        pins = build_map([stop(1, -6.37, 106.80), stop(2, -6.40, 106.85)])["pins"]
        self.assertLess(pins[0]["y"], pins[1]["y"])     # lebih utara = lebih atas
        self.assertLess(pins[0]["x"], pins[1]["x"])     # lebih timur = lebih kanan

    def test_single_stop_is_centered_and_path_has_all_points(self):
        data = build_map([stop(1, -6.37, 106.82)])
        self.assertEqual(len(data["pins"]), 1)
        self.assertEqual(len(build_map([stop(1, -6.37, 106.82), stop(2, -6.4, 106.85)])["path"].split()), 2)


class BuildDashboardTests(TestCase):
    def setUp(self):
        self.user = make_user("sari")
        self.other = make_user("andi")

    def build(self, key="30"):
        return build_dashboard(self.user, key, today=TODAY, now=NOW)

    def kpi(self, data, key):
        return next(k for k in data["kpis"] if k["key"] == key)

    def test_only_finished_pickups_of_this_courier_count(self):
        rec(self.user, "A", TODAY, 10)
        rec(self.user, "B", TODAY, 5, status="ongoing")
        rec(self.user, "C", TODAY, 7, status="cancelled")
        rec(self.user, "D", TODAY, None, status="done")          # tanpa berat tidak dihitung
        rec(self.other, "E", TODAY, 99)
        data = self.build()
        self.assertEqual(self.kpi(data, "kg")["value"], "10 kg")
        self.assertEqual(self.kpi(data, "pickups")["value"], "1")
        self.assertEqual(self.kpi(data, "points")["value"], "50")

    def test_period_filters_records(self):
        rec(self.user, "A", TODAY - timedelta(days=3), 4)
        rec(self.user, "B", TODAY - timedelta(days=20), 6)
        rec(self.user, "C", TODAY - timedelta(days=100), 8)
        self.assertEqual(self.kpi(self.build("7"), "kg")["value"], "4 kg")
        self.assertEqual(self.kpi(self.build("30"), "kg")["value"], "10 kg")
        self.assertEqual(self.kpi(self.build("365"), "kg")["value"], "18 kg")

    def test_period_edges(self):
        rec(self.user, "A", TODAY - timedelta(days=29), 3)     # hari pertama periode 30 hari: masuk
        rec(self.user, "B", TODAY - timedelta(days=30), 100)   # sehari sebelumnya: periode sebelumnya
        rec(self.user, "C", TODAY + timedelta(days=1), 100)    # besok: belum masuk
        data = self.build("30")
        self.assertEqual(self.kpi(data, "kg")["value"], "3 kg")
        self.assertEqual(self.kpi(data, "kg")["delta"]["tone"], "down")   # dibanding 100 kg sebelumnya

    def test_unknown_range_falls_back_to_default(self):
        self.assertEqual(self.build("abc")["range_key"], "365")
        self.assertEqual(build_dashboard(self.user, "", today=TODAY, now=NOW)["range_key"], "365")

    def test_partners_count_is_distinct(self):
        rec(self.user, "A", TODAY, 1, partner="Kafe A")
        rec(self.user, "B", TODAY - timedelta(days=1), 1, partner="Kafe A")
        rec(self.user, "C", TODAY - timedelta(days=2), 1, partner="Resto B")
        self.assertEqual(self.kpi(self.build(), "partners")["value"], "2")

    def test_delta_compares_with_previous_period(self):
        rec(self.user, "A", TODAY - timedelta(days=2), 12)      # 7 hari terakhir
        rec(self.user, "B", TODAY - timedelta(days=9), 10)      # 7 hari sebelumnya
        delta = self.kpi(self.build("7"), "kg")["delta"]
        self.assertEqual(delta, {"text": "+20,0%", "tone": "up"})
        self.assertIsNone(self.kpi(self.build("365"), "kg")["delta"])

    def test_summary_values(self):
        rec(self.user, "A", TODAY, 4)
        rec(self.user, "B", TODAY, 2, partner="Resto B")
        rec(self.user, "C", TODAY - timedelta(days=1), 6, partner="Hotel C")
        s = self.build()["summary"]
        self.assertEqual(s[0]["value"], "4 kg")                  # rata-rata 12 / 3
        self.assertEqual(s[1]["value"], "6 kg")
        self.assertIn("Hotel C", s[1]["caption"])
        self.assertEqual(s[2]["value"], "2 hari")

    def test_empty_account(self):
        data = self.build()
        self.assertEqual(self.kpi(data, "kg")["value"], "0 kg")
        self.assertEqual([x["value"] for x in data["summary"]], ["–", "–", "0 hari"])
        self.assertEqual(data["composition"], [])

    def test_updated_label_is_wib(self):
        self.assertEqual(self.build()["updated_display"], "25 Okt 2026, 07.09 WIB")


@override_settings(STORAGES=PLAIN_STATIC)
class DashboardPageTests(RouteTestBase):
    def setUp(self):
        super().setUp()
        p = patch("courier.views.current_weather", return_value={"temperature": 30, "text": "Berawan", "icon": "cloud", "rain": False})
        p.start()
        self.addCleanup(p.stop)
        self.url = reverse("courier:show_dashboard")

    def test_requires_courier_login(self):
        self.client.logout()
        self.assertNotEqual(self.client.get(self.url).status_code, 200)
        self.client.force_login(make_user("mitra1", role="partner"))
        self.assertNotEqual(self.client.get(self.url).status_code, 200)

    def test_renders_for_each_period(self):
        for key in ("7", "30", "365", "abc"):
            res = self.client.get(self.url, {"periode": key})
            self.assertEqual(res.status_code, 200, key)
            self.assertContains(res, "Kinerja nyata, diperbarui setiap pikap")
        res = self.client.get(self.url, {"periode": "7"})
        self.assertContains(res, 'class="is-active" aria-current="true">7 Hari')

    def test_empty_state(self):
        res = self.client.get(self.url)
        self.assertContains(res, "Belum ada pikap selesai pada periode ini.")
        self.assertContains(res, "0 dari 4 titik selesai")
        self.assertNotContains(res, "Komposisi limbah")
        self.assertContains(res, "Sumber limbah")

    def test_finishing_a_stop_updates_dashboard(self):
        pk = self.ids()[0]
        self.finish(pk, "4,5")
        res = self.client.get(self.url)
        self.assertContains(res, "4,5 kg")
        self.assertContains(res, "1 dari 4 titik selesai")
        self.assertContains(res, "Kafe")                      # kategori titik tampil di sumber limbah
        self.assertNotContains(res, "Belum ada pikap selesai pada periode ini.")
        self.assertEqual(res.context["done_stops"], 1)
        self.assertNotEqual(res.context["next_stop"].pk, pk)

    def test_next_stop_card_and_route_link(self):
        res = self.client.get(self.url)
        self.assertIsNotNone(res.context["next_stop"])
        self.assertContains(res, res.context["next_stop"].name)
        self.assertContains(res, reverse("courier:show_route_today"))
        self.assertContains(res, "Buka Rute")
        self.assertEqual(len(res.context["map"]["pins"]), 4)

    def test_all_done_shows_history_link(self):
        for pk in self.ids():
            self.finish(pk, "1")
        res = self.client.get(self.url)
        self.assertContains(res, "Kerja bagus hari ini!")
        self.assertContains(res, reverse("courier:show_history"))
        self.assertIsNone(res.context["next_stop"])

    def test_weather_missing_does_not_break_page(self):
        with patch("courier.views.current_weather", return_value=None):
            self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_page_shows_only_own_data(self):
        other = make_user("andi")
        rec(other, "X", date.today(), 77)
        res = self.client.get(self.url)
        self.assertNotContains(res, "77 kg")

    def test_dashboard_styles_exist(self):
        from pathlib import Path
        from django.conf import settings
        css = (Path(settings.BASE_DIR) / "static/courier/css/courier.css").read_text(encoding="utf-8")
        for cls in (".dash-kpis", ".dash-chart", ".dash-tip", ".dash-route", ".dash-banner", ".dash-tabs"):
            self.assertIn(cls, css)
