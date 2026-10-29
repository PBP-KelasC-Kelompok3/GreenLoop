"""Asumsi dampak lingkungan yang dipakai lintas halaman GreenLoop."""
from decimal import Decimal, ROUND_HALF_UP


# Estimasi sementara untuk demo: kg CO2e avoided per kg limbah organik.
CO2E_AVOIDED_KG_PER_KG = Decimal("0.5")


def estimate_co2e_avoided(weight_kg):
    weight = Decimal(str(weight_kg or 0))
    return (weight * CO2E_AVOIDED_KG_PER_KG).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )
