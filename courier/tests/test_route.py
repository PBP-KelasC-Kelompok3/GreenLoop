"""Test halaman Rute Hari Ini: tampilan, lokasi kurir, mulai perjalanan, selesai pikap, status bertugas."""
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from courier.maps import RoutingError, estimate_route
from courier.models import CourierAssignment, CourierProfile, PickupRecord, WeightLog
from courier.route_state import get_today_stops
from courier.utils import get_courier_stats
from scheduling.models import MitraProfile, PickupSchedule

from .helpers import PLAIN_STATIC, make_approved_courier, make_user

WEATHER = {"temperature": 29, "text": "Berawan", "icon": "cloud", "rain": False}

# Empat titik contoh di Kota Depok
POINTS = [
    ("TJ-0001", "Kafe Senja Margonda", -6.3688, 106.8330, 36),
    ("TJ-0002", "Hotel Arya Depok", -6.3719, 106.8231, 60),
    ("TJ-0003", "Kukusan Roastery", -6.3640, 106.8230, 18),
    ("TJ-0004", "Warung Tekko Beji", -6.3775, 106.8180, 25),
]
USER_POS = {"lat": "-6.3700", "lng": "106.8250"}   # di dalam Depok


def offline(url):
    raise RoutingError("tidak ada koneksi")


def make_points(rows=POINTS, courier=None, prefix="mitra"):
    points = []
    for index, (code, name, lat, lng, kg) in enumerate(rows):
        mitra = make_user(f"{prefix}_{index}", role="mitra")
        MitraProfile.objects.create(
            user=mitra, business_name=name, business_type="Kafe / Coffee Shop",
            address_detail="Jl. Contoh, Depok",
            latitude=lat, longitude=lng,
        )
        pickup = PickupSchedule.objects.create(
            mitra=mitra, estimated_weight=kg,
            pickup_date=timezone.localdate(), pickup_time_slot="08:00-10:00",
            status="SCHEDULED",
        )
        if courier:
            CourierAssignment.objects.create(pickup_schedule=pickup, courier=courier)
        pickup.code, pickup.name = code, name
        pickup.latitude, pickup.longitude = lat, lng
        points.append(pickup)
    return points


@override_settings(STORAGES=PLAIN_STATIC)
class RouteTestBase(TestCase):
    """Semua layanan luar (OSRM, Open-Meteo) dimatikan atau diganti data tetap."""

    def setUp(self):
        cache.clear()
        for p in (
            patch("courier.maps._fetch_json", side_effect=offline),
            patch("courier.route_views.current_weather", return_value=WEATHER),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.user = make_approved_courier("sari")
        self.points = make_points(courier=self.user)
        self.client.force_login(self.user)

    def payload(self, **params):
        res = self.client.get(reverse("courier:show_route_today"), params)
        return res, res.context["route"]

    def data(self, **params):
        return self.client.get(reverse("courier:route_data"), params).json()["plan"]

    def start(self, pk, **extra):
        return self.client.post(reverse("courier:start_pickup", args=[pk]), extra)

    def finish(self, pk, weight, **extra):
        if not PickupSchedule.objects.filter(pk=pk).exists():
            return self.client.post(reverse("courier:finish_pickup", args=[pk]), {
                "weight_kg": weight, **extra,
            })
        if not PickupRecord.objects.filter(courier=self.user, pickup_schedule_id=pk,
                                           status=PickupRecord.Status.ONGOING).exists():
            self.start(pk)
        profile = MitraProfile.objects.get(user=PickupSchedule.objects.get(pk=pk).mitra)
        return self.client.post(reverse("courier:finish_pickup", args=[pk]), {
            "weight_kg": weight, "lat": profile.latitude, "lng": profile.longitude, **extra,
        })

    def ids(self):
        """Urutan id titik seperti yang tampil di halaman."""
        return [s["id"] for s in self.payload()[1]["stops"]]


class RoutePageTests(RouteTestBase):
    def test_page_renders_design_elements(self):
        res, route = self.payload()
        self.assertEqual(res.status_code, 200)
        for text in ("Rute Hari Ini", "Urutan Penjemputan", "Kafe Senja Margonda", "Hotel Arya Depok"):
            self.assertContains(res, text)
        self.assertContains(res, 'id="route-data"')
        self.assertEqual(route["total"], 4)

    def test_all_stops_start_pending_with_one_next(self):
        _, route = self.payload()
        labels = [s["statusLabel"] for s in route["stops"]]
        self.assertEqual(sorted(labels), ["Berikutnya", "Terjadwal", "Terjadwal", "Terjadwal"])
        self.assertNotIn("Selesai", labels)
        self.assertNotIn("Menuju", labels)

    def test_target_is_the_next_stop(self):
        _, route = self.payload()
        nxt = next(s for s in route["stops"] if s["statusLabel"] == "Berikutnya")
        self.assertEqual(route["targetId"], nxt["id"])

    def test_offline_falls_back_to_estimate_with_notice(self):
        _, route = self.payload()
        self.assertEqual(route["route"]["label"], "Rute perkiraan")
        self.assertTrue(route["route"]["dashed"])
        self.assertTrue(route["notice"])

    def test_weather_included_and_failure_tolerated(self):
        self.assertEqual(self.payload()[1]["weather"], WEATHER)
        with patch("courier.route_views.current_weather", return_value=None):
            res, route = self.payload()
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(route["weather"])

    def test_map_is_limited_to_depok(self):
        b = self.payload()[1]["bounds"]
        self.assertLess(b["south"], b["north"])
        self.assertLess(b["west"], b["east"])
        for p in self.points:
            self.assertTrue(b["south"] <= p.latitude <= b["north"])
            self.assertTrue(b["west"] <= p.longitude <= b["east"])

    def test_warehouse_not_in_payload(self):
        _, route = self.payload()
        self.assertIsNone(route["origin"])
        self.assertNotIn("Gudang", str(route))

    def test_stops_are_stable_during_the_day(self):
        self.assertEqual(self.ids(), self.ids())

    def test_requires_courier_role(self):
        self.client.logout()
        self.client.force_login(make_user("mitra1", role="partner"))
        res = self.client.get(reverse("courier:show_route_today"))
        self.assertNotEqual(res.status_code, 200)

    def test_anonymous_redirected(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("courier:show_route_today")).status_code, 302)

    def test_legacy_reset_parameter_does_not_clear_completed_pickup(self):
        first = self.payload()[1]["targetId"]
        self.finish(first, "60")
        res = self.client.get(reverse("courier:show_route_today") + "?reset=1")
        self.assertEqual(res.status_code, 200)
        _, route = self.payload()
        self.assertIn("Selesai", [s["statusLabel"] for s in route["stops"]])

    def test_page_without_data_still_renders(self):
        PickupSchedule.objects.all().delete()
        res, route = self.payload()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(route["total"], 0)
        self.assertIsNone(route["route"])
        self.assertIsNone(route["targetId"])


class LiveLocationTests(RouteTestBase):
    def test_route_starts_from_user_position(self):
        plan = self.data(**USER_POS)
        self.assertEqual(plan["origin"], {"lat": -6.37, "lng": 106.825})
        self.assertEqual(plan["route"]["geometry"][0], [-6.37, 106.825])
        self.assertIn("Dari posisimu", [c["text"] for c in plan["route"]["chips"]])

    def test_without_position_route_only_connects_stops(self):
        plan = self.data()
        first = next(s for s in plan["stops"] if s["id"] == plan["targetId"])
        self.assertEqual(plan["route"]["geometry"][0], [first["lat"], first["lng"]])
        self.assertNotIn("Dari posisimu", [c["text"] for c in plan["route"]["chips"]])

    def test_position_near_depok_but_outside_is_rejected(self):
        plan = self.data(lat="-6.2000", lng="106.8200")   # Jakarta Selatan
        self.assertIsNone(plan["origin"])
        self.assertIn("Kota Depok", plan["locationNote"])
        self.assertNotIn("Dari posisimu", [c["text"] for c in plan["route"]["chips"]])

    def test_position_far_away_is_ignored_with_note(self):
        plan = self.data(lat="-7.2500", lng="112.7500")   # Surabaya
        self.assertIsNone(plan["origin"])
        self.assertIn("Kota Depok", plan["locationNote"])

    def test_position_inside_depok_has_no_note(self):
        self.assertIsNone(self.data(**USER_POS)["locationNote"])

    def test_garbage_position_is_ignored(self):
        for lat, lng in (("abc", "106.8"), ("-6.37", ""), ("nan", "nan"), ("inf", "106.8")):
            with self.subTest(lat=lat, lng=lng):
                plan = self.data(lat=lat, lng=lng)
                self.assertIsNone(plan["origin"])
                self.assertIsNone(plan["locationNote"])

    def test_route_data_requires_courier_and_get(self):
        self.assertEqual(self.client.post(reverse("courier:route_data")).status_code, 405)
        self.client.logout()
        self.client.force_login(make_user("mitra1", role="partner"))
        self.assertNotEqual(self.client.get(reverse("courier:route_data")).status_code, 200)

    def test_start_and_finish_keep_user_position(self):
        first = self.payload()[1]["targetId"]
        plan = self.start(first, **USER_POS).json()["plan"]
        self.assertEqual(plan["origin"], {"lat": -6.37, "lng": 106.825})
        plan = self.finish(first, "10").json()["plan"]
        pickup = PickupSchedule.objects.get(pk=first)
        profile = MitraProfile.objects.get(user=pickup.mitra)
        self.assertEqual(plan["origin"], {"lat": profile.latitude, "lng": profile.longitude})

    def test_finished_stops_are_not_part_of_the_route(self):
        first = self.payload()[1]["targetId"]
        before = len(self.data(**USER_POS)["route"]["geometry"])
        self.finish(first, "10")
        after = len(self.data(**USER_POS)["route"]["geometry"])
        self.assertEqual(after, before - 1)   # satu titik selesai, garis rute berkurang satu titik


class StartPickupTests(RouteTestBase):
    def test_start_moves_active_to_chosen_stop(self):
        a, b = self.ids()[:2]
        self.start(a)
        data = self.start(b).json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["plan"]["targetId"], b)
        status = {s["id"]: s["statusLabel"] for s in data["plan"]["stops"]}
        self.assertEqual(status[b], "Menuju")
        self.assertNotEqual(status[a], "Menuju")  # hanya satu titik berstatus menuju

    def test_start_done_stop_rejected(self):
        pk = self.ids()[0]
        self.finish(pk, "10")
        res = self.start(pk)
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.json()["ok"])

    def test_unknown_stop_404(self):
        self.assertEqual(self.start(9999).status_code, 404)

    def test_get_not_allowed(self):
        res = self.client.get(reverse("courier:start_pickup", args=[self.ids()[0]]))
        self.assertEqual(res.status_code, 405)

    def test_non_courier_blocked(self):
        pk = self.ids()[0]
        self.client.logout()
        self.client.force_login(make_user("mitra1", role="partner"))
        self.assertNotEqual(self.start(pk).status_code, 200)


class FinishPickupTests(RouteTestBase):
    def test_finish_saves_weight_log(self):
        pk = self.ids()[0]
        name = PickupSchedule.objects.get(pk=pk).mitra.profile.business_name
        self.assertEqual(self.finish(pk, "58,6").status_code, 200)
        log = WeightLog.objects.get(courier=self.user)
        self.assertEqual(log.partner_name, name)
        self.assertEqual(log.weight_kg, Decimal("58.6"))
        self.assertEqual(log.points, 293)  # 58,6 x 5 
        self.assertEqual(log.collected_at, timezone.localdate())
        self.assertIn(f"PK-{pk:04d}", log.notes)

    def test_message_has_points(self):
        data = self.finish(self.ids()[0], "58.6").json()
        self.assertIn("58,6 kg", data["message"])
        self.assertIn("+293 Waste Points", data["message"])

    def test_next_stop_becomes_target(self):
        pk = self.ids()[0]
        data = self.finish(pk, "58,6").json()
        stops = {s["id"]: s for s in data["plan"]["stops"]}
        self.assertEqual(stops[pk]["statusLabel"], "Selesai")
        self.assertEqual(stops[pk]["actualKg"], "58,6")
        target = data["plan"]["targetId"]
        self.assertNotEqual(target, pk)
        self.assertEqual(stops[target]["statusLabel"], "Berikutnya")

    def test_finish_all_stops_has_no_target(self):
        for pk in self.ids():
            data = self.finish(pk, "10").json()
        self.assertIsNone(data["plan"]["targetId"])
        self.assertIsNone(data["plan"]["navigation"])
        self.assertEqual(data["plan"]["directions"], [])
        self.assertEqual(WeightLog.objects.count(), 4)

    def test_invalid_weights_rejected_without_saving(self):
        pk = self.ids()[0]
        for bad in ("", "abc", "-5", "0", "0,0", "12,34", "5001", "10000", "1e3", "58,"):
            with self.subTest(weight=bad):
                res = self.finish(pk, bad)
                self.assertEqual(res.status_code, 400)
                self.assertIn("weight_kg", res.json()["errors"])
        self.assertEqual(WeightLog.objects.count(), 0)

    def test_boundaries_accepted(self):
        a, b = self.ids()[:2]
        self.assertEqual(self.finish(a, "0,1").status_code, 200)
        self.assertEqual(self.finish(b, "5000").status_code, 200)

    def test_cannot_finish_twice(self):
        pk = self.ids()[0]
        self.finish(pk, "10")
        res = self.finish(pk, "10")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(WeightLog.objects.count(), 1)

    def test_unknown_stop_404(self):
        self.assertEqual(self.finish(9999, "10").status_code, 404)

    def test_finish_counts_in_profile_stats(self):
        # Pikap yang diselesaikan di sini ikut dihitung di statistik Profil
        a, b = self.ids()[:2]
        self.finish(a, "58,6")
        self.finish(b, "10")
        stats = get_courier_stats(self.user)
        self.assertEqual(stats["pickups_done"], 2)
        self.assertEqual(stats["total_kg"], Decimal("68.6"))
        self.assertEqual(stats["points"], 293 + 50)

    def test_state_is_per_courier_session(self):
        pk = self.ids()[0]
        self.finish(pk, "10")
        other = self.client_class()
        other.force_login(make_approved_courier("andi"))
        res = other.get(reverse("courier:show_route_today"))
        stops = {s["id"]: s for s in res.context["route"]["stops"]}
        self.assertNotIn(pk, stops)


class DutyToggleTests(RouteTestBase):
    def post(self, value):
        return self.client.post(reverse("courier:toggle_duty"), {"on_duty": value})

    def test_set_on_and_off(self):
        data = self.post("true").json()
        self.assertTrue(data["is_on_duty"])
        self.assertEqual(data["label"], "Sedang Bertugas")
        self.assertTrue(CourierProfile.objects.get(user=self.user).is_on_duty)

        data = self.post("false").json()
        self.assertFalse(data["is_on_duty"])
        self.assertEqual(data["label"], "Tidak Bertugas")

    def test_repeated_request_is_idempotent(self):
        self.post("true")
        self.assertTrue(self.post("true").json()["is_on_duty"])

    def test_garbage_value_means_off(self):
        self.post("true")
        self.assertFalse(self.post("yes").json()["is_on_duty"])

    def test_page_shows_current_state(self):
        self.post("true")
        res = self.client.get(reverse("courier:show_route_today"))
        self.assertContains(res, "Sedang Bertugas")
        self.assertContains(res, "checked")


class NearbyStopsTests(RouteTestBase):
    """Rute hanya menampilkan pickup hari ini yang ditugaskan ke kurir login."""

    def setUp(self):
        super().setUp()
        PickupSchedule.objects.all().delete()
        west = [(f"W-{i}", f"Barat {i}", -6.40 + i * 0.0003, 106.76, 20) for i in range(8)]
        east = [(f"E-{i}", f"Timur {i}", -6.40 + i * 0.0003, 106.86, 20) for i in range(8)]
        self.points = make_points(west + east, courier=self.user, prefix="nearby")

    def spread_km(self, stops):
        from courier.maps import haversine_m
        return max(haversine_m((a.latitude, a.longitude), (b.latitude, b.longitude)) for a in stops for b in stops) / 1000

    def test_all_assigned_pickups_are_returned_for_the_requested_day(self):
        stops = get_today_stops(self.user, timezone.localdate())
        self.assertEqual(len(stops), 16)
        self.assertEqual({s.pk for s in stops}, {p.pk for p in self.points})

    def test_unassigned_pickups_are_not_shown(self):
        today = timezone.localdate()
        unassigned = make_points([("U-1", "Tidak ditugaskan", -6.4, 106.8, 20)], prefix="unassigned")
        self.assertEqual(len(get_today_stops(self.user, today)), 16)
        self.assertNotIn(unassigned[0].pk, {s.pk for s in get_today_stops(self.user, today)})

    def test_same_stops_all_day(self):
        today = timezone.localdate()
        first = [s.pk for s in get_today_stops(self.user, today)]
        self.assertEqual(first, [s.pk for s in get_today_stops(self.user, today)])

    def test_fewer_points_than_a_day_uses_all(self):
        PickupSchedule.objects.exclude(pk__in=[p.pk for p in self.points[:3]]).delete()
        self.assertEqual(len(get_today_stops(self.user, timezone.localdate())), 3)


class EstimateByCourierVehicleTests(RouteTestBase):
    """Estimasi berat mengikuti armada kurir yang login (motor maksimal 5 kg, pickup maksimal 10 kg)."""

    def set_vehicle(self, user, vehicle):
        CourierProfile.objects.update_or_create(user=user, defaults={"vehicle_type": vehicle})

    def replace_points(self, rows):
        PickupSchedule.objects.all().delete()
        self.points = make_points(rows, courier=self.user, prefix="estimate")

    def est_by_name(self, client=None):
        res = (client or self.client).get(reverse("courier:show_route_today"))
        return {s["name"]: s["estKg"] for s in res.context["route"]["stops"]}

    def test_estimated_weight_comes_from_mitra_pickup(self):
        self.set_vehicle(self.user, CourierProfile.VehicleType.MOTOR_BOX)
        self.replace_points([("A-1", "Besar", -6.38, 106.82, 10), ("A-2", "Sedang", -6.381, 106.82, 6),
                             ("A-3", "Kecil", -6.382, 106.82, 2), ("A-4", "Lama", -6.383, 106.82, 88)])
        est = self.est_by_name()
        self.assertEqual(est, {"Besar": 10, "Sedang": 6, "Kecil": 2, "Lama": 88})

    def test_estimate_does_not_change_with_vehicle_type(self):
        self.set_vehicle(self.user, CourierProfile.VehicleType.PICKUP_BAK)
        self.replace_points([("A-1", "Besar", -6.38, 106.82, 10), ("A-2", "Sedang", -6.381, 106.82, 6),
                             ("A-3", "Kecil", -6.382, 106.82, 2), ("A-4", "Lama", -6.383, 106.82, 88)])
        est = self.est_by_name()
        self.assertEqual(est, {"Besar": 10, "Sedang": 6, "Kecil": 2, "Lama": 88})

    def test_each_courier_sees_own_vehicle_on_same_stops(self):
        self.replace_points([("A-1", "Titik", -6.38, 106.82, 10), ("A-2", "Lain", -6.381, 106.82, 8)])
        self.set_vehicle(self.user, CourierProfile.VehicleType.PICKUP_BAK)
        other_user = make_approved_courier("andi")
        self.set_vehicle(other_user, CourierProfile.VehicleType.MOTOR_BOX)
        make_points([("B-1", "Titik", -6.38, 106.82, 10)], courier=other_user, prefix="other")
        other = self.client_class()
        other.force_login(other_user)
        self.assertEqual(self.est_by_name()["Titik"], 10)
        self.assertEqual(self.est_by_name(other)["Titik"], 10)

    def test_all_stops_show_the_couriers_vehicle(self):
        self.set_vehicle(self.user, CourierProfile.VehicleType.MOTOR_BOX)
        _, route = self.payload()
        self.assertEqual({s["vehicle"] for s in route["stops"]}, {"Motor Box"})
        self.set_vehicle(self.user, CourierProfile.VehicleType.PICKUP_BAK)
        _, route = self.payload()
        self.assertEqual({s["vehicle"] for s in route["stops"]}, {"Pickup Bak"})

    def test_pickup_estimate_is_not_scaled_by_courier_vehicle(self):
        self.set_vehicle(self.user, CourierProfile.VehicleType.MOTOR_BOX)
        self.assertEqual({s["estKg"] for s in self.payload()[1]["stops"]}, {18, 25, 36, 60})

    def test_estimate_function(self):
        from courier.route_state import estimate_for
        self.assertEqual([estimate_for(n, "Motor Box") for n in range(0, 12)], [1, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 5])
        self.assertEqual([estimate_for(n, "Pickup Bak") for n in (0, 1, 5, 10, 99)], [1, 1, 5, 10, 10])
        self.assertEqual(estimate_for(7, "Kapal Layar"), 7)    # armada tak dikenal: batas terbesar
        self.assertEqual(estimate_for(7, None), 7)

    def test_weight_log_is_not_limited_by_the_estimate(self):
        # Estimasi hanya perkiraan; berat nyata tetap bisa dicatat sesuai timbangan
        self.set_vehicle(self.user, CourierProfile.VehicleType.MOTOR_BOX)
        self.assertEqual(self.finish(self.ids()[0], "58,6").status_code, 200)


class DayRolloverTests(RouteTestBase):
    def test_state_resets_on_new_day(self):
        pk = self.ids()[0]
        self.finish(pk, "10")
        tomorrow = timezone.localdate() + timedelta(days=1)
        stops = {s.pk: s for s in get_today_stops(self.user, tomorrow)}
        self.assertNotIn(pk, stops)


def fake_route(points):
    """Rute OSRM palsu: tiap titik tujuan punya satu leg dengan empat langkah."""
    legs = [
        {"distance": 900, "duration": 120, "steps": [
            {"distance": 350, "name": "Jl. Margonda Raya", "type": "depart", "modifier": "straight"},
            {"distance": 450, "name": "Jl. Arif Rahman Hakim", "type": "turn", "modifier": "left"},
            {"distance": 100, "name": "", "type": "turn", "modifier": "right"},
            {"distance": 0, "name": "", "type": "arrive", "modifier": ""},
        ]}
        for _ in points[1:]
    ]
    return {
        "source": "osrm",
        "geometry": [list(p) for p in points],
        "distance": 900.0 * len(legs),
        "duration": 120.0 * len(legs),
        "legs": legs,
    }


class DirectionsTests(RouteTestBase):
    def setUp(self):
        super().setUp()
        p = patch("courier.route_plan.get_route", side_effect=fake_route)
        p.start()
        self.addCleanup(p.stop)

    def test_directions_list_every_step_with_distance(self):
        plan = self.data(**USER_POS)
        self.assertEqual([s["text"] for s in plan["directions"]], [
            "Mulai perjalanan di Jl. Margonda Raya",
            "Belok kiri ke Jl. Arif Rahman Hakim",
            "Belok kanan",
            "Tiba di tujuan",
        ])
        self.assertEqual([s["distance"] for s in plan["directions"]], ["350 m", "450 m", "100 m", ""])

    def test_icons_match_maneuver(self):
        plan = self.data(**USER_POS)
        self.assertEqual([s["icon"] for s in plan["directions"]],
                         ["arrow-up", "arrow-left", "arrow-right", "map-pin"])

    def test_navigation_card_uses_first_turn(self):
        nav = self.data(**USER_POS)["navigation"]
        self.assertEqual(nav["distance_text"], "350 m")
        self.assertEqual(nav["instruction"], "Belok kiri ke Jl. Arif Rahman Hakim")

    def test_directions_follow_current_target(self):
        pk = self.ids()[0]
        data = self.finish(pk, "10").json()
        self.assertTrue(data["plan"]["directions"])
        target = next(s for s in data["plan"]["stops"] if s["id"] == data["plan"]["targetId"])
        self.assertEqual(data["plan"]["targetName"], target["name"])

    def test_first_stop_has_no_directions_without_position(self):
        # Tanpa lokasi, titik pertama adalah awal rute sehingga belum ada belokan menuju ke sana
        plan = self.data()
        self.assertEqual(plan["directions"], [])
        self.assertIsNone(plan["navigation"])

    def test_estimate_mode_has_no_steps(self):
        with patch("courier.route_plan.get_route", side_effect=estimate_route):
            plan = self.data(**USER_POS)
        self.assertEqual(plan["directions"], [])


class RouteStaticTests(TestCase):
    def test_static_files_and_styles_exist(self):
        base = Path(settings.BASE_DIR) / "static" / "courier"
        self.assertTrue((base / "js/route.js").exists())
        css = (base / "css/courier.css").read_text(encoding="utf-8")
        for cls in (".route-layout", ".route-map-card", ".route-item", ".duty-switch", ".route-toast", ".route-me"):
            self.assertIn(cls, css)
