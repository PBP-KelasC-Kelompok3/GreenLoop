"""Test perintah seed_points (data awal titik jemput dari OpenStreetMap)."""
import io
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from courier.management.commands import seed_points
from courier.management.commands.seed_points import CENTRAL_DEPOK
from courier.maps import DEPOK_BOUNDS
from courier.route_state import LARGEST_CAPACITY_KG
from courier.models import CollectionPoint


def element(i, amenity="cafe", lat=-6.40, lng=106.82, name=None, **tags):
    """Satu elemen jawaban Overpass."""
    return {"type": "node", "id": i, "lat": lat + i * 0.0001, "lon": lng,
            "tags": {"amenity": amenity, "name": name or f"Tempat {i}", **tags}}


def many(n):
    return [element(i) for i in range(1, n + 1)]


class ParsePlacesTests(SimpleTestCase):
    def test_valid_place_is_parsed(self):
        place = seed_points.parse_places([element(
            7, "restaurant", **{"addr:street": "Jl. Margonda Raya", "addr:housenumber": "8", "addr:suburb": "Pondok Cina"},
        )])[0]
        self.assertEqual(place["source_id"], "node/7")
        self.assertEqual(place["category"], "Restoran")
        self.assertEqual(place["address"], "Jl. Margonda Raya 8, Pondok Cina, Depok")
        self.assertEqual(place["photo_note"], "Disetujui admin · kulit buah & sayur kering")

    def test_only_kitchen_waste_partners_are_kept(self):
        kept = {label for label, _ in seed_points.CATEGORIES.values()}
        self.assertEqual(kept, {"Kafe", "Restoran", "Restoran cepat saji", "Pujasera", "Hotel", "Toko roti"})
        # pasar, toko sayur, dan supermarket diabaikan walau ada di data OpenStreetMap
        dropped = [
            {"type": "node", "id": 1, "lat": -6.40, "lon": 106.82, "tags": {"amenity": "marketplace", "name": "Pasar A"}},
            {"type": "node", "id": 2, "lat": -6.40, "lon": 106.82, "tags": {"shop": "greengrocer", "name": "Toko B"}},
            {"type": "node", "id": 3, "lat": -6.40, "lon": 106.82, "tags": {"shop": "supermarket", "name": "Swalayan C"}},
        ]
        self.assertEqual(seed_points.parse_places(dropped), [])
        query = seed_points.build_query()
        for tag in ("marketplace", "greengrocer", "supermarket"):
            self.assertNotIn(tag, query)

    def test_every_category_uses_the_only_accepted_waste_type(self):
        wastes = {waste for _, waste in seed_points.CATEGORIES.values()}
        self.assertEqual(wastes, {"kulit buah & sayur kering"})
        for tag, label in (("cafe", "Kafe"), ("restaurant", "Restoran"), ("food_court", "Pujasera")):
            note = seed_points.parse_places([element(1, tag)])[0]["photo_note"]
            self.assertIn("kulit buah & sayur", note, label)
            for other in ("ampas kopi", "sisa makanan", "adonan"):
                self.assertNotIn(other, note)

    def test_address_falls_back_to_city(self):
        self.assertEqual(seed_points.parse_places([element(1)])[0]["address"], "Kota Depok")

    def test_way_uses_center_coordinates(self):
        way = {"type": "way", "id": 5, "center": {"lat": -6.4, "lon": 106.8},
               "tags": {"tourism": "hotel", "name": "Hotel Contoh"}}
        place = seed_points.parse_places([way])[0]
        self.assertEqual((place["latitude"], place["longitude"]), (-6.4, 106.8))
        self.assertEqual(place["category"], "Hotel")

    def test_invalid_elements_are_skipped(self):
        b = DEPOK_BOUNDS
        bad = [
            {"type": "node", "id": 1, "lat": -6.4, "lon": 106.8, "tags": {"amenity": "cafe"}},                  # tanpa nama
            {"type": "node", "id": 2, "lat": -6.4, "lon": 106.8, "tags": {"amenity": "bank", "name": "Bank"}},  # jenis lain
            {"type": "node", "id": 3, "tags": {"amenity": "cafe", "name": "Tanpa koordinat"}},
            {"type": "node", "id": 4, "lat": b["north"] + 1, "lon": 106.8, "tags": {"amenity": "cafe", "name": "Luar Depok"}},
            {"type": "node", "id": 5, "lat": -6.4, "lon": 106.8},
        ]
        self.assertEqual(seed_points.parse_places(bad), [])

    def test_duplicates_are_merged(self):
        a = element(1, name="Kafe Kembar", lat=-6.40, lng=106.82)
        b = dict(element(2, name="kafe kembar", lat=-6.40, lng=106.82), lat=a["lat"])
        self.assertEqual(len(seed_points.parse_places([a, b])), 1)

    def test_estimate_is_within_largest_vehicle_capacity(self):
        # Disimpan untuk armada terbesar (1-10 kg); halaman rute menyesuaikannya ke armada kurir
        places = seed_points.parse_places(many(200))
        self.assertEqual(LARGEST_CAPACITY_KG, 10)
        for p in places:
            self.assertTrue(1 <= p["est_kg"] <= LARGEST_CAPACITY_KG, p)
        self.assertEqual(min(p["est_kg"] for p in places), 1)
        self.assertEqual(max(p["est_kg"] for p in places), 10)

    def test_places_do_not_pick_a_vehicle(self):
        # Armada ditentukan oleh profil kurir, bukan oleh titik jemput
        self.assertNotIn("vehicle", seed_points.parse_places(many(5))[0])

    def test_places_are_stable_between_runs(self):
        self.assertEqual(seed_points.parse_places(many(30)), seed_points.parse_places(many(30)))

    def test_query_uses_central_depok_by_default(self):
        q = seed_points.build_query()
        self.assertIn('"amenity"="cafe"', q)
        self.assertIn(str(CENTRAL_DEPOK["south"]), q)
        self.assertNotIn(str(DEPOK_BOUNDS["south"]), q)

    def test_central_box_is_inside_the_depok_box(self):
        self.assertGreaterEqual(CENTRAL_DEPOK["south"], DEPOK_BOUNDS["south"])
        self.assertLessEqual(CENTRAL_DEPOK["north"], DEPOK_BOUNDS["north"])
        self.assertGreaterEqual(CENTRAL_DEPOK["west"], DEPOK_BOUNDS["west"])
        self.assertLessEqual(CENTRAL_DEPOK["east"], DEPOK_BOUNDS["east"])

    def test_edge_places_near_jakarta_are_skipped_by_default(self):
        edge = element(1, lat=-6.335, lng=106.85, name="Dekat Perbatasan")   # utara, dekat Jakarta
        self.assertEqual(seed_points.parse_places([edge]), [])
        self.assertEqual(len(seed_points.parse_places([edge], DEPOK_BOUNDS)), 1)

    def test_central_place_is_kept(self):
        self.assertEqual(len(seed_points.parse_places([element(1, lat=-6.385, lng=106.82)])), 1)


class SeedCommandTests(TestCase):
    def run_seed(self, elements, **options):
        out = io.StringIO()
        with patch.object(seed_points, "fetch_elements", return_value=elements):
            call_command("seed_points", stdout=out, **options)
        return out.getvalue()

    def test_creates_requested_number_of_points(self):
        out = self.run_seed(many(80), count=60)
        self.assertEqual(CollectionPoint.objects.count(), 60)
        self.assertIn("total 60", out)

    def test_default_is_at_least_fifty(self):
        self.run_seed(many(80))
        self.assertGreaterEqual(CollectionPoint.objects.count(), 50)

    def test_codes_are_unique_and_sequential(self):
        self.run_seed(many(60), count=55)
        codes = sorted(CollectionPoint.objects.values_list("code", flat=True))
        self.assertEqual(codes[0], "TJ-0001")
        self.assertEqual(len(set(codes)), 55)

    def test_running_twice_does_not_duplicate(self):
        self.run_seed(many(70), count=60)
        self.run_seed(many(70), count=60)
        self.assertEqual(CollectionPoint.objects.count(), 60)

    def test_rerun_updates_changed_data(self):
        self.run_seed(many(60), count=60)
        changed = many(60)
        changed[0]["tags"]["name"] = "Nama Baru"
        self.run_seed(changed, count=60)
        self.assertTrue(CollectionPoint.objects.filter(name="Nama Baru").exists())
        self.assertEqual(CollectionPoint.objects.count(), 60)

    def test_too_few_places_is_an_error_and_saves_nothing(self):
        with self.assertRaisesMessage(CommandError, "Hanya 10 tempat"):
            self.run_seed(many(10), count=60)
        self.assertEqual(CollectionPoint.objects.count(), 0)

    def test_network_failure_is_a_clear_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")), \
                patch.object(seed_points.time, "sleep"):
            with self.assertRaisesMessage(CommandError, "Overpass API tidak bisa dihubungi"):
                call_command("seed_points", stdout=io.StringIO())

    def test_clear_removes_old_points_first(self):
        CollectionPoint.objects.create(code="TJ-9999", name="Lama", category="Kafe", address="x",
                                       latitude=-6.33, longitude=106.85, source_id="node/old")
        self.run_seed(many(60), count=60, clear=True)
        self.assertFalse(CollectionPoint.objects.filter(source_id="node/old").exists())
        self.assertEqual(CollectionPoint.objects.count(), 60)

    def test_failed_download_with_clear_keeps_existing_points(self):
        # --clear baru menghapus setelah data baru berhasil diambil, jadi data lama tidak hilang saat server sibuk
        CollectionPoint.objects.create(code="TJ-0001", name="Lama", category="Kafe", address="x",
                                       latitude=-6.39, longitude=106.82, source_id="node/old")
        with patch.object(seed_points, "fetch_elements", side_effect=CommandError("502")):
            with self.assertRaises(CommandError):
                call_command("seed_points", clear=True, stdout=io.StringIO())
        self.assertEqual(CollectionPoint.objects.count(), 1)

    def test_too_few_places_with_clear_keeps_existing_points(self):
        CollectionPoint.objects.create(code="TJ-0001", name="Lama", category="Kafe", address="x",
                                       latitude=-6.39, longitude=106.82, source_id="node/old")
        with self.assertRaises(CommandError):
            self.run_seed(many(5), count=60, clear=True)
        self.assertEqual(CollectionPoint.objects.count(), 1)

    def test_old_points_kept_without_clear(self):
        CollectionPoint.objects.create(code="TJ-9999", name="Lama", category="Kafe", address="x",
                                       latitude=-6.33, longitude=106.85, source_id="node/old")
        self.run_seed(many(60), count=60)
        self.assertTrue(CollectionPoint.objects.filter(source_id="node/old").exists())

    def test_wide_uses_whole_depok_box(self):
        with patch.object(seed_points, "fetch_elements", return_value=many(60)) as fetch:
            call_command("seed_points", wide=True, stdout=io.StringIO())
        self.assertEqual(fetch.call_args[0][0], DEPOK_BOUNDS)

    def test_default_uses_central_box(self):
        with patch.object(seed_points, "fetch_elements", return_value=many(60)) as fetch:
            call_command("seed_points", stdout=io.StringIO())
        self.assertEqual(fetch.call_args[0][0], CENTRAL_DEPOK)

    def test_all_points_are_inside_central_depok(self):
        self.run_seed(many(60), count=60)
        b = CENTRAL_DEPOK
        for p in CollectionPoint.objects.all():
            self.assertTrue(b["south"] <= p.latitude <= b["north"])
            self.assertTrue(b["west"] <= p.longitude <= b["east"])


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload if isinstance(self.payload, bytes) else __import__("json").dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code):
    import urllib.error
    return urllib.error.HTTPError("https://x", code, "Bad Gateway", {}, None)


@patch.object(seed_points.time, "sleep")
class FetchElementsTests(SimpleTestCase):
    """Server Overpass publik sering sibuk: coba ulang, lalu pindah ke server cadangan."""

    OK = {"elements": [{"type": "node", "id": 1}]}

    def run_fetch(self, outcomes, env=None, log=lambda message: None):
        """Menjalankan fetch_elements dengan jawaban palsu berurutan. Hasil: (hasil atau CommandError, daftar URL)."""
        import os
        urls = []

        def fake_urlopen(request, timeout=None):
            urls.append(request.full_url)
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), patch.dict("os.environ", env or {}):
            if not env:
                os.environ.pop("OVERPASS_URL", None)      # dipulihkan otomatis oleh patch.dict
            try:
                result = seed_points.fetch_elements(log=log)
            except CommandError as exc:
                result = exc
        return result, urls

    def test_success_on_first_try(self, sleep):
        result, urls = self.run_fetch([FakeResponse(self.OK)])
        self.assertEqual(result, self.OK["elements"])
        self.assertEqual(urls, [seed_points.DEFAULT_URLS[0]])
        sleep.assert_not_called()

    def test_retries_same_server_after_502(self, sleep):
        result, urls = self.run_fetch([http_error(502), FakeResponse(self.OK)])
        self.assertEqual(result, self.OK["elements"])
        self.assertEqual(urls, [seed_points.DEFAULT_URLS[0]] * 2)    # percobaan kedua di server yang sama
        sleep.assert_called_once()

    def test_falls_back_to_next_server(self, sleep):
        result, urls = self.run_fetch([http_error(502), http_error(504), FakeResponse(self.OK)])
        self.assertEqual(result, self.OK["elements"])
        self.assertEqual(urls[2], seed_points.DEFAULT_URLS[1])

    def test_html_error_page_with_200_counts_as_failure(self, sleep):
        result, urls = self.run_fetch([FakeResponse(b"<html>Server busy</html>"), FakeResponse(self.OK)])
        self.assertEqual(result, self.OK["elements"])
        self.assertEqual(len(urls), 2)

    def test_all_servers_failing_gives_a_clear_error(self, sleep):
        total = len(seed_points.DEFAULT_URLS) * seed_points.ATTEMPTS_PER_SERVER
        result, urls = self.run_fetch([http_error(502) for _ in range(total)])
        self.assertIsInstance(result, CommandError)
        self.assertIn("502", str(result))
        self.assertIn("coba lagi", str(result))
        self.assertEqual(len(urls), total)
        self.assertEqual(set(urls), set(seed_points.DEFAULT_URLS))      # semua server sempat dicoba

    def test_custom_url_is_used_alone_without_fallbacks(self, sleep):
        custom = "http://localhost:9/api"
        result, urls = self.run_fetch([http_error(502) for _ in range(seed_points.ATTEMPTS_PER_SERVER)],
                                      env={"OVERPASS_URL": custom})
        self.assertIsInstance(result, CommandError)
        self.assertEqual(set(urls), {custom})

    def test_urls_default_and_override(self, sleep):
        with patch.dict("os.environ", {"OVERPASS_URL": "http://localhost:9"}):
            self.assertEqual(seed_points.overpass_urls(), ["http://localhost:9"])
        with patch.dict("os.environ"):
            __import__("os").environ.pop("OVERPASS_URL", None)
            self.assertEqual(seed_points.overpass_urls(), seed_points.DEFAULT_URLS)

    def test_progress_is_reported_to_the_user(self, sleep):
        messages = []
        total = len(seed_points.DEFAULT_URLS) * seed_points.ATTEMPTS_PER_SERVER
        self.run_fetch([http_error(502) for _ in range(total)], log=messages.append)
        self.assertEqual(len(messages), total)
        self.assertTrue(any("overpass-api.de gagal" in m and "502" in m for m in messages))