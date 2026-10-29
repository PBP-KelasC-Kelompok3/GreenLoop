"""Satu aturan konversi berat terverifikasi menjadi Waste Points."""
from decimal import Decimal, ROUND_DOWN


POINTS_PER_KILOGRAM = 5
WEIGHT_PRECISION_KG = Decimal("0.1")
MEMBERSHIP_THRESHOLDS = {
    "Bronze": 0,
    "Silver": 1000,
    "Gold": 3000,
    "Platinum": 5000,
}


def points_for_weight(weight_kg):
    """Hitung poin utuh dengan membulatkan berat dan hasil poin ke bawah."""
    weight = Decimal(str(weight_kg)).quantize(WEIGHT_PRECISION_KG, rounding=ROUND_DOWN)
    return int((weight * POINTS_PER_KILOGRAM).to_integral_value(rounding=ROUND_DOWN))


def membership_tier(balance):
    """Satu aturan level mitra untuk dashboard, profil, dan halaman reward."""
    balance = int(balance or 0)
    if balance >= MEMBERSHIP_THRESHOLDS["Platinum"]:
        return "Platinum"
    if balance >= MEMBERSHIP_THRESHOLDS["Gold"]:
        return "Gold"
    if balance >= MEMBERSHIP_THRESHOLDS["Silver"]:
        return "Silver"
    return "Bronze"
