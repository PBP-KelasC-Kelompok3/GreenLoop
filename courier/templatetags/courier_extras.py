from decimal import Decimal, InvalidOperation

from django import template

from courier.utils import format_date_id, get_initials

# Mendaftarkan filter agar bisa dipakai di template setelah {% load courier_extras %}
register = template.Library()


@register.filter
def initials(user):
    # {{ user|initials }} -> "BS"
    return get_initials(user)


@register.filter
def kg(value, mode=""):
    """35.2 -> '35,2'; 1234.5 -> '1.234,5'. Dengan 'short': '36,0' -> '36'."""
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return "-"

    # Format Indonesia: titik untuk ribuan, koma untuk desimal (kebalikan format Inggris)
    text = f"{number:,.1f}".translate(str.maketrans(",.", ".,"))
    if mode == "short" and text.endswith(",0"):
        text = text[:-2]
    return text


@register.filter
def num_id(value):
    """1234 -> '1.234'."""
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "-"


@register.filter
def date_id(value):
    """date(2026, 10, 21) -> '21 Okt 2026'."""
    return format_date_id(value) if value else "-"