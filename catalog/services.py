"""Thin clients for RajaOngkir (Komerce) and Midtrans."""
import hashlib
import hmac

import requests
from django.conf import settings
from django.core.cache import cache


class ServiceError(Exception):
    """Raised when an upstream API fails; message is safe to show to the user."""


# --------------------------------------------------------------------------- RajaOngkir
def _ro_headers():
    if not settings.RAJAONGKIR_API_KEY:
        raise ServiceError("Shipping is not configured (missing RAJAONGKIR_API_KEY).")
    return {"key": settings.RAJAONGKIR_API_KEY}


def search_destinations(term, limit=10):
    """Search subdistricts by name/zip. Cached because the data rarely changes."""
    term = term.strip().lower()
    cache_key = f"ro:dest:{term}:{limit}"
    hit = cache.get(cache_key)
    if hit is not None:
        return hit
    try:
        r = requests.get(
            f"{settings.RAJAONGKIR_BASE_URL}/destination/domestic-destination",
            params={"search": term, "limit": limit, "offset": 0},
            headers=_ro_headers(),
            timeout=15,
        )
        body = r.json()
    except (requests.RequestException, ValueError):
        raise ServiceError("Could not reach the shipping service. Try again.")
    if r.status_code == 404:
        return []
    if r.status_code != 200:
        raise ServiceError(_ro_message(body, "Destination lookup failed."))
    results = []
    for d in body.get("data") or []:
        label = d.get("label") or ", ".join(
            x for x in [d.get("subdistrict_name"), d.get("district_name"), d.get("city_name"),
                        d.get("province_name"), d.get("zip_code")] if x
        )
        results.append({"id": str(d["id"]), "label": label})
    cache.set(cache_key, results, 60 * 60)
    return results


def calculate_shipping(destination_id, weight_grams):
    """Return a flat, cheapest-first list of courier services for a destination."""
    if not settings.RAJAONGKIR_ORIGIN_ID or settings.RAJAONGKIR_ORIGIN_ID == "0":
        raise ServiceError("Shipping origin is not configured (RAJAONGKIR_ORIGIN_ID).")
    try:
        r = requests.post(
            f"{settings.RAJAONGKIR_BASE_URL}/calculate/domestic-cost",
            headers=_ro_headers(),
            data={
                "origin": settings.RAJAONGKIR_ORIGIN_ID,
                "destination": destination_id,
                "weight": max(1, int(weight_grams)),
                "courier": ":".join(settings.RAJAONGKIR_COURIERS),
                "price": "lowest",
            },
            timeout=20,
        )
        body = r.json()
    except (requests.RequestException, ValueError):
        raise ServiceError("Could not reach the shipping service. Try again.")
    if r.status_code != 200:
        raise ServiceError(_ro_message(body, "No shipping options available for this destination."))
    options = []
    for d in body.get("data") or []:
        try:
            cost = int(d["cost"])
        except (KeyError, TypeError, ValueError):
            continue
        options.append({
            "courier_code": d.get("code", ""),
            "courier_name": d.get("name", d.get("code", "")),
            "service": d.get("service", ""),
            "description": d.get("description", ""),
            "etd": d.get("etd", ""),
            "cost": cost,
        })
    options.sort(key=lambda o: o["cost"])
    return options


def _ro_message(body, fallback):
    try:
        return (body.get("meta") or {}).get("message") or body.get("message") or fallback
    except AttributeError:
        return fallback


# --------------------------------------------------------------------------- Midtrans
def _midtrans_hosts():
    if settings.MIDTRANS_IS_PRODUCTION:
        return "https://app.midtrans.com", "https://api.midtrans.com"
    return "https://app.sandbox.midtrans.com", "https://api.sandbox.midtrans.com"


def snap_js_url():
    return _midtrans_hosts()[0] + "/snap/snap.js"


def create_snap_token(order, customer_email=""):
    """Create a Snap transaction and return its token."""
    if not settings.MIDTRANS_SERVER_KEY:
        raise ServiceError("Payments are not configured (missing MIDTRANS_SERVER_KEY).")
    payload = {
        "transaction_details": {"order_id": order.midtrans_order_id, "gross_amount": order.gross_amount},
        "item_details": [
            {"id": str(order.product_id or "item"), "price": order.unit_price,
             "quantity": order.quantity, "name": order.product_name[:50]},
            {"id": "shipping", "price": order.shipping_cost, "quantity": 1,
             "name": f"Shipping {order.courier_code.upper()} {order.courier_service}"[:50]},
        ],
        "expiry": {"unit": "hours", "duration": 24},
        "customer_details": {
            "first_name": order.recipient_name[:50],
            "phone": order.phone[:19],
            "email": customer_email,
            "shipping_address": {
                "first_name": order.recipient_name[:50],
                "phone": order.phone[:19],
                "address": order.address[:200],
            },
        },
    }
    try:
        r = requests.post(
            _midtrans_hosts()[0] + "/snap/v1/transactions",
            json=payload,
            auth=(settings.MIDTRANS_SERVER_KEY, ""),
            headers={"Accept": "application/json"},
            timeout=20,
        )
        body = r.json()
    except (requests.RequestException, ValueError):
        raise ServiceError("Could not reach the payment service. Try again.")
    token = body.get("token")
    if r.status_code not in (200, 201) or not token:
        msgs = body.get("error_messages")
        raise ServiceError("; ".join(msgs) if msgs else "Payment could not be started.")
    return token


def fetch_transaction_status(midtrans_order_id):
    """Ask Midtrans for the current status (used when the webhook can't reach localhost)."""
    try:
        r = requests.get(
            f"{_midtrans_hosts()[1]}/v2/{midtrans_order_id}/status",
            auth=(settings.MIDTRANS_SERVER_KEY, ""),
            headers={"Accept": "application/json"},
            timeout=15,
        )
        return r.json()
    except (requests.RequestException, ValueError):
        raise ServiceError("Could not reach the payment service. Try again.")


def valid_notification_signature(payload):
    raw = (
        str(payload.get("order_id", ""))
        + str(payload.get("status_code", ""))
        + str(payload.get("gross_amount", ""))
        + settings.MIDTRANS_SERVER_KEY
    )
    expected = hashlib.sha512(raw.encode()).hexdigest()
    return hmac.compare_digest(expected, str(payload.get("signature_key", "")))


def cancel_transaction(midtrans_order_id):
    """Cancel a transaction that has a payment attempt but is not yet paid."""
    try:
        r = requests.post(
            f"{_midtrans_hosts()[1]}/v2/{midtrans_order_id}/cancel",
            auth=(settings.MIDTRANS_SERVER_KEY, ""),
            headers={"Accept": "application/json"},
            timeout=15,
        )
        return r.json()
    except (requests.RequestException, ValueError):
        raise ServiceError("Could not reach the payment service. Try again.")
