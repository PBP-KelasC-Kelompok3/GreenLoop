"""Clients for RajaOngkir shipping quotes and Midtrans Snap payments."""
import hashlib
import hmac

import requests
from django.conf import settings


class ServiceError(Exception):
    """Raised when an upstream API fails with a safe user-facing message."""


def _ro_headers():
    if not settings.RAJAONGKIR_API_KEY:
        raise ServiceError("Ongkir belum dikonfigurasi. Tambahkan RAJAONGKIR_API_KEY.")
    return {"key": settings.RAJAONGKIR_API_KEY}


def search_destinations(term, limit=10):
    term = (term or "").strip()
    if len(term) < 2:
        return []
    try:
        response = requests.get(
            f"{settings.RAJAONGKIR_BASE_URL.rstrip('/')}/destination/domestic-destination",
            params={"search": term, "limit": limit, "offset": 0},
            headers=_ro_headers(),
            timeout=15,
        )
        body = response.json()
    except (requests.RequestException, ValueError):
        raise ServiceError("Layanan pencarian alamat sedang tidak dapat dihubungi.")
    if response.status_code != 200:
        raise ServiceError(_ro_message(body, "Pencarian tujuan gagal."))
    results = []
    for item in body.get("data") or []:
        label = item.get("label") or ", ".join(
            str(part) for part in (
                item.get("subdistrict_name"), item.get("district_name"),
                item.get("city_name"), item.get("province_name"), item.get("zip_code"),
            ) if part
        )
        results.append({"id": str(item["id"]), "label": label})
    return results


def calculate_shipping(destination_id, weight_grams):
    if not settings.RAJAONGKIR_ORIGIN_ID:
        raise ServiceError("Lokasi asal pengiriman belum dikonfigurasi.")
    try:
        response = requests.post(
            f"{settings.RAJAONGKIR_BASE_URL.rstrip('/')}/calculate/domestic-cost",
            headers={**_ro_headers(), "Content-Type": "application/x-www-form-urlencoded"},
            data={
                "origin": settings.RAJAONGKIR_ORIGIN_ID,
                "destination": destination_id,
                "weight": max(1, int(weight_grams)),
                "courier": ":".join(settings.RAJAONGKIR_COURIERS),
                "price": "lowest",
            },
            timeout=20,
        )
        body = response.json()
    except (requests.RequestException, ValueError):
        raise ServiceError("Layanan ongkir sedang tidak dapat dihubungi.")
    if response.status_code != 200:
        raise ServiceError(_ro_message(body, "Tidak ada pilihan pengiriman untuk tujuan ini."))
    options = []
    for item in body.get("data") or []:
        try:
            cost = int(item["cost"])
        except (KeyError, TypeError, ValueError):
            continue
        options.append({
            "courier_code": item.get("code", ""),
            "courier_name": item.get("name", item.get("code", "Kurir")),
            "service": item.get("service", ""),
            "description": item.get("description", ""),
            "etd": item.get("etd", ""),
            "cost": cost,
        })
    return sorted(options, key=lambda option: option["cost"])


def _ro_message(body, fallback):
    if not isinstance(body, dict):
        return fallback
    return (body.get("meta") or {}).get("message") or body.get("message") or fallback


def _midtrans_hosts():
    if settings.MIDTRANS_IS_PRODUCTION:
        return "https://app.midtrans.com", "https://api.midtrans.com"
    return "https://app.sandbox.midtrans.com", "https://api.sandbox.midtrans.com"


def snap_js_url():
    return _midtrans_hosts()[0] + "/snap/snap.js"


def create_snap_token(order):
    if not settings.MIDTRANS_SERVER_KEY:
        raise ServiceError("Pembayaran belum dikonfigurasi. Tambahkan MIDTRANS_SERVER_KEY.")
    items = [
        {
            "id": str(item.product_id or item.pk)[:50],
            "price": item.unit_price,
            "quantity": item.quantity,
            "name": item.product_name[:50],
        }
        for item in order.items.all()
    ]
    discount_amount = order.goods_discount + order.shipping_discount
    if discount_amount:
        items.append({
            "id": "voucher",
            "price": -discount_amount,
            "quantity": 1,
            "name": "Voucher Waste Points",
        })
    if order.shipping_cost:
        items.append({
            "id": "shipping",
            "price": order.shipping_cost,
            "quantity": 1,
            "name": f"Ongkir {order.courier_code.upper()} {order.courier_service}"[:50],
        })
    payload = {
        "transaction_details": {"order_id": order.order_id, "gross_amount": order.total_amount},
        "item_details": items,
        "expiry": {"unit": "hours", "duration": 24},
        "customer_details": {
            "first_name": order.recipient_name[:50],
            "email": order.user.email,
            "phone": order.phone[:19],
            "shipping_address": {
                "first_name": order.recipient_name[:50],
                "phone": order.phone[:19],
                "address": order.shipping_address[:200],
                "city": order.destination_label[:50],
            },
        },
    }
    try:
        response = requests.post(
            _midtrans_hosts()[0] + "/snap/v1/transactions",
            json=payload,
            auth=(settings.MIDTRANS_SERVER_KEY, ""),
            headers={"Accept": "application/json"},
            timeout=20,
        )
        body = response.json()
    except (requests.RequestException, ValueError):
        raise ServiceError("Layanan pembayaran sedang tidak dapat dihubungi.")
    token = body.get("token")
    if response.status_code not in (200, 201) or not token:
        messages = body.get("error_messages") or []
        raise ServiceError("; ".join(messages) or "Pembayaran tidak dapat dimulai.")
    return token


def fetch_transaction_status(midtrans_order_id):
    if not settings.MIDTRANS_SERVER_KEY:
        raise ServiceError("Pembayaran belum dikonfigurasi. Tambahkan MIDTRANS_SERVER_KEY.")
    try:
        response = requests.get(
            f"{_midtrans_hosts()[1]}/v2/{midtrans_order_id}/status",
            auth=(settings.MIDTRANS_SERVER_KEY, ""),
            headers={"Accept": "application/json"},
            timeout=15,
        )
        body = response.json()
    except (requests.RequestException, ValueError):
        raise ServiceError("Status pembayaran sedang tidak dapat diperiksa.")
    if response.status_code != 200:
        raise ServiceError(_ro_message(body, "Status pembayaran tidak ditemukan."))
    return body


def valid_notification_signature(payload):
    if not settings.MIDTRANS_SERVER_KEY:
        return False
    raw = (
        str(payload.get("order_id", ""))
        + str(payload.get("status_code", ""))
        + str(payload.get("gross_amount", ""))
        + (settings.MIDTRANS_SERVER_KEY or "")
    )
    expected = hashlib.sha512(raw.encode()).hexdigest()
    return hmac.compare_digest(expected, str(payload.get("signature_key", "")))
