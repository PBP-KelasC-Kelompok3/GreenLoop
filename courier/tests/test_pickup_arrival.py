"""Tes aturan mulai perjalanan dan verifikasi kedatangan sebelum pikap selesai."""
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from courier.models import PickupRecord, WeightLog
from courier.tests.helpers import PLAIN_STATIC, make_approved_courier, make_user
from scheduling.models import MitraProfile, PickupSchedule

WEATHER = {"temperature": 29, "text": "Berawan", "icon": "cloud", "rain": False}
MITRA_LOCATION = {"lat": "-6.3700", "lng": "106.8250"}


def offline(url):
    from courier.maps import RoutingError
    raise RoutingError("test offline")


@override_settings(STORAGES=PLAIN_STATIC)
class PickupArrivalTests(TestCase):
    def setUp(self):
        cache.clear()
        self.osrm = patch("courier.maps._fetch_json", side_effect=offline)
        self.weather = patch("courier.route_views.current_weather", return_value=WEATHER)
        self.osrm.start()
        self.weather.start()
        self.addCleanup(self.osrm.stop)
        self.addCleanup(self.weather.stop)

        self.courier = make_approved_courier("arrival_courier")
        self.mitra = make_user("arrival_mitra", role="mitra")
        self.mitra_profile = MitraProfile.objects.create(
            user=self.mitra,
            business_name="Kafe Kukusan",
            address_detail="Jl. Contoh, Depok",
            kota="Depok",
            latitude=float(MITRA_LOCATION["lat"]),
            longitude=float(MITRA_LOCATION["lng"]),
            location_locked=True,
        )
        self.pickup = PickupSchedule.objects.create(
            mitra=self.mitra,
            courier=self.courier,
            estimated_weight=12.5,
            pickup_date=timezone.localdate(),
            pickup_time_slot="08:00 - 10:00 WIB",
            status="SCHEDULED",
        )
        self.client.force_login(self.courier)

    def finish(self, **location):
        return self.client.post(
            reverse("courier:finish_pickup", args=[self.pickup.pk]),
            {"weight_kg": "12.5", **location},
        )

    def start(self):
        return self.client.post(
            reverse("courier:start_pickup", args=[self.pickup.pk]),
        )

    def test_cannot_finish_before_start_even_at_mitra_location(self):
        response = self.finish(**MITRA_LOCATION)

        self.assertEqual(response.status_code, 400)
        self.assertIn("Mulai perjalanan terlebih dahulu", response.json()["errors"]["__all__"][0])
        self.pickup.refresh_from_db()
        self.assertEqual(self.pickup.status, "SCHEDULED")
        self.assertFalse(WeightLog.objects.exists())
        self.assertFalse(PickupRecord.objects.exists())

    def test_cannot_finish_until_gps_is_within_arrival_radius(self):
        self.assertEqual(self.start().status_code, 200)

        response = self.finish(lat="-6.3800", lng=MITRA_LOCATION["lng"])

        self.assertEqual(response.status_code, 400)
        self.assertIn("masih sekitar", response.json()["errors"]["__all__"][0])
        self.pickup.refresh_from_db()
        self.assertEqual(self.pickup.status, "IN_PROGRESS")
        self.assertFalse(WeightLog.objects.exists())

    def test_finish_succeeds_after_start_and_arrival(self):
        self.assertEqual(self.start().status_code, 200)

        response = self.finish(**MITRA_LOCATION)

        self.assertEqual(response.status_code, 200)
        self.pickup.refresh_from_db()
        self.assertEqual(self.pickup.status, "COMPLETED")
        self.assertEqual(self.pickup.actual_weight, Decimal("12.5"))
        self.assertEqual(WeightLog.objects.get(pickup_schedule=self.pickup).weight_kg, Decimal("12.5"))
        record = PickupRecord.objects.get(pickup_schedule=self.pickup)
        self.assertEqual(record.status, PickupRecord.Status.DONE)
        self.assertEqual(record.actual_kg, Decimal("12.5"))

    def test_approved_but_not_started_pickup_is_not_shown_as_active(self):
        self.pickup.status = "IN_PROGRESS"
        self.pickup.save(update_fields=["status"])

        response = self.client.get(reverse("courier:route_data"))

        self.assertEqual(response.status_code, 200)
        stop = response.json()["plan"]["stops"][0]
        self.assertEqual(stop["status"], "next")
        self.assertEqual(stop["statusLabel"], "Berikutnya")