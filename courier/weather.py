"""Cuaca Kota Depok saat ini dari Open-Meteo (API publik, tanpa API key)."""
import json
import os
import urllib.error
import urllib.request

from django.core.cache import cache

DEFAULT_URL = "https://api.open-meteo.com/v1/forecast"
DEPOK_CENTER = (-6.40, 106.82)  # perkiraan pusat Kota Depok
REQUEST_TIMEOUT = 6  # detik
CACHE_SECONDS = 600  # cuaca disimpan 10 menit
USER_AGENT = "GreenLoop-Courier/1.0 (tugas kuliah)"

# Kode cuaca WMO dari Open-Meteo -> (keterangan Indonesia, nama ikon Lucide)
WEATHER_CODES = {
    0: ("Cerah", "sun"),
    1: ("Cerah berawan", "cloud-sun"),
    2: ("Berawan sebagian", "cloud-sun"),
    3: ("Berawan", "cloud"),
    45: ("Berkabut", "cloud-fog"),
    48: ("Berkabut", "cloud-fog"),
    51: ("Gerimis ringan", "cloud-drizzle"),
    53: ("Gerimis", "cloud-drizzle"),
    55: ("Gerimis lebat", "cloud-drizzle"),
    61: ("Hujan ringan", "cloud-rain"),
    63: ("Hujan", "cloud-rain"),
    65: ("Hujan lebat", "cloud-rain"),
    80: ("Hujan lokal", "cloud-rain"),
    81: ("Hujan lokal", "cloud-rain"),
    82: ("Hujan deras", "cloud-rain"),
    95: ("Badai petir", "cloud-lightning"),
    96: ("Badai petir", "cloud-lightning"),
    99: ("Badai petir", "cloud-lightning"),
}
RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}


def describe_code(code):
    # Kode yang tidak dikenal dianggap berawan
    return WEATHER_CODES.get(code, ("Cuaca tidak diketahui", "cloud"))


def current_weather():
    """Cuaca Depok saat ini, atau None bila API tidak bisa dihubungi."""
    base = os.environ.get("OPEN_METEO_URL", DEFAULT_URL)
    lat, lng = DEPOK_CENTER
    url = (
        f"{base}?latitude={lat}&longitude={lng}"
        "&current=temperature_2m,precipitation,weather_code&timezone=Asia%2FJakarta"
    )

    data = cache.get(url)
    if data is None:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return None
        cache.set(url, data, CACHE_SECONDS)

    try:
        current = data["current"]
        code = int(current["weather_code"])
        text, icon = describe_code(code)
        return {
            "temperature": round(current["temperature_2m"]),
            "text": text,
            "icon": icon,
            "rain": code in RAIN_CODES or float(current.get("precipitation") or 0) > 0,
        }
    except (KeyError, TypeError, ValueError):
        return None