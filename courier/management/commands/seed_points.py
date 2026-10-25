"""Mengisi data awal titik jemput dari OpenStreetMap (Overpass API, tanpa API key).

Contoh:
    python manage.py seed_points                 # ambil 60 titik di pusat Kota Depok (sekitar Margonda)
    python manage.py seed_points --count 80
    python manage.py seed_points --clear         # hapus titik lama dulu (mis. setelah kotak wilayah berubah)
    python manage.py seed_points --wide          # seluruh kotak Depok, termasuk tepi yang berbatasan dengan Jakarta

Nama dan koordinat adalah data asli OpenStreetMap, sama dengan yang tergambar di peta.
Untuk deploy tanpa internet, simpan hasilnya sebagai fixture lalu muat di server:
    python manage.py dumpdata courier.CollectionPoint --indent 2 > courier/fixtures/collection_points.json
    python manage.py loaddata collection_points
"""
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request

from django.core.management.base import BaseCommand, CommandError

from courier.maps import DEPOK_BOUNDS
from courier.models import CollectionPoint
from courier.route_state import LARGEST_CAPACITY_KG

# Server Overpass publik. Bila satu sibuk (502/504/429), perintah mencoba ulang lalu pindah ke berikutnya.
DEFAULT_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
ATTEMPTS_PER_SERVER = 2
RETRY_WAIT_SECONDS = 3
REQUEST_TIMEOUT = 90
USER_AGENT = "GreenLoop-Courier/1.0 (tugas kuliah)"

# Wilayah yang dipakai: pusat Kota Depok (koridor Margonda, Beji, Pancoran Mas, Sukmajaya).
# Kotak seluruh Depok (maps.DEPOK_BOUNDS) ikut menjangkau Jakarta Timur/Selatan di sisi utara,
# jadi untuk data awal dipakai kotak yang lebih sempit ini.
CENTRAL_DEPOK = {"south": -6.43, "north": -6.36, "west": 106.78, "east": 106.86}

# GreenLoop hanya menerima kulit buah dan sayur yang kering dan belum tercampur limbah lain,
# jadi semua titik memakai jenis limbah yang sama.
WASTE = "kulit buah & sayur"

# Tag OpenStreetMap -> (jenis tampilan, jenis limbah). Hanya mitra penghasil limbah dapur.
CATEGORIES = {
    ("amenity", "cafe"): ("Kafe", WASTE),
    ("amenity", "restaurant"): ("Restoran", WASTE),
    ("amenity", "fast_food"): ("Restoran cepat saji", WASTE),
    ("amenity", "food_court"): ("Pujasera", WASTE),
    ("tourism", "hotel"): ("Hotel", WASTE),
    ("shop", "bakery"): ("Toko roti", WASTE),
}


def overpass_urls():
    """Daftar server yang dicoba berurutan; OVERPASS_URL (bila diisi) dipakai sendirian."""
    custom = os.environ.get("OVERPASS_URL")
    return [custom] if custom else list(DEFAULT_URLS)


def build_query(box=CENTRAL_DEPOK):
    b = box
    bbox = f"{b['south']},{b['west']},{b['north']},{b['east']}"
    filters = "".join(f'nwr["{k}"="{v}"]["name"]({bbox});' for k, v in CATEGORIES)
    return f"[out:json][timeout:60];({filters});out center 600;"


def fetch_elements(box=CENTRAL_DEPOK, log=lambda message: None):
    """Mengambil daftar tempat dari Overpass API, dengan percobaan ulang dan server cadangan."""
    data = urllib.parse.urlencode({"data": build_query(box)}).encode()
    errors = []
    for url in overpass_urls():
        host = urllib.parse.urlparse(url).netloc
        for attempt in range(1, ATTEMPTS_PER_SERVER + 1):
            request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                    return json.loads(response.read().decode("utf-8")).get("elements", [])
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                errors.append(f"{host}: {exc}")
                log(f"  {host} gagal (percobaan {attempt}/{ATTEMPTS_PER_SERVER}): {exc}")
                if attempt < ATTEMPTS_PER_SERVER:
                    time.sleep(RETRY_WAIT_SECONDS)
    raise CommandError(
        "Overpass API tidak bisa dihubungi. Server publiknya sering sibuk; coba lagi beberapa menit lagi. "
        f"Rincian: {errors[-1]}"
    )


def category_of(tags):
    for (key, value), info in CATEGORIES.items():
        if tags.get(key) == value:
            return info
    return None


def address_of(tags):
    street = " ".join(x for x in (tags.get("addr:street"), tags.get("addr:housenumber")) if x)
    area = tags.get("addr:suburb") or tags.get("addr:subdistrict") or tags.get("addr:village") or ""
    parts = [p for p in (tags.get("addr:full") or street, area) if p]
    return (", ".join(parts) + ", Depok") if parts else "Kota Depok"


def parse_places(elements, box=CENTRAL_DEPOK):
    """Mengubah elemen Overpass menjadi daftar tempat unik (nama + koordinat di dalam kotak wilayah)."""
    places, seen = [], set()
    b = box
    for element in elements:
        tags = element.get("tags") or {}
        info = category_of(tags)
        lat = element.get("lat") or (element.get("center") or {}).get("lat")
        lng = element.get("lon") or (element.get("center") or {}).get("lon")
        name = (tags.get("name") or "").strip()
        if not (info and name and lat is not None and lng is not None):
            continue
        if not (b["south"] <= lat <= b["north"] and b["west"] <= lng <= b["east"]):
            continue
        key = (name.lower(), round(lat, 3), round(lng, 3))
        if key in seen:
            continue
        seen.add(key)
        label, waste = info
        source_id = f"{element['type']}/{element['id']}"
        rng = random.Random(source_id)      # berat contoh tetap sama tiap kali seed dijalankan
        est = rng.randint(1, LARGEST_CAPACITY_KG)   # estimasi untuk armada terbesar; halaman rute menyesuaikannya ke armada kurir
        places.append({
            "source_id": source_id,
            "name": name[:120],
            "category": label,
            "address": address_of(tags)[:200],
            "latitude": float(lat),
            "longitude": float(lng),
            "est_kg": est,
            "photo_note": f"Disetujui admin · {waste}",
        })
    return places


class Command(BaseCommand):
    help = "Mengisi titik jemput (mitra) di Kota Depok dari OpenStreetMap."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=60, help="Jumlah titik yang disimpan (default 60).")
        parser.add_argument("--wide", action="store_true", help="Pakai seluruh kotak Depok, bukan hanya pusat kota.")
        parser.add_argument("--clear", action="store_true", help="Hapus semua titik jemput lama sebelum mengisi.")

    def handle(self, *args, **options):
        want = options["count"]
        box = DEPOK_BOUNDS if options["wide"] else CENTRAL_DEPOK
        places = parse_places(fetch_elements(box, log=self.stdout.write), box)
        if len(places) < want:
            raise CommandError(
                f"Hanya {len(places)} tempat ditemukan, kurang dari {want}. "
                "Coba lagi nanti, kurangi --count, atau tambahkan --wide untuk wilayah lebih luas."
            )

        if options["clear"]:
            CollectionPoint.objects.all().delete()

        # Pilihan acak tetapi tetap (benih tetap), supaya hasilnya sama di semua komputer
        places.sort(key=lambda p: p["source_id"])
        random.Random(2026).shuffle(places)
        places = places[:want]

        created = 0
        for place in places:
            existing = CollectionPoint.objects.filter(source_id=place["source_id"]).first()
            if existing:
                for field, value in place.items():
                    setattr(existing, field, value)
                existing.save()
                continue
            number = CollectionPoint.objects.count() + 1
            while CollectionPoint.objects.filter(code=f"TJ-{number:04d}").exists():
                number += 1
            CollectionPoint.objects.create(code=f"TJ-{number:04d}", **place)
            created += 1

        total = CollectionPoint.objects.count()
        self.stdout.write(self.style.SUCCESS(f"Selesai: {created} titik baru, total {total} titik jemput."))