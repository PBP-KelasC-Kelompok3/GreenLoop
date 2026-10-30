from django.shortcuts import render
from accounts.decorator import role_required
from accounts.models import UserProfile
from .impact import estimate_co2e_avoided
from waste_reward.points import POINTS_PER_KILOGRAM


def home(request):
    # Data dummy untuk Live Impact.
    # Nanti dapat diganti dengan data asli dari modul Waste & Reward.

    monthly = [
        {"label": "Mei", "kg": 900},
        {"label": "Jun", "kg": 1250},
        {"label": "Jul", "kg": 1650},
        {"label": "Agu", "kg": 2050},
        {"label": "Sep", "kg": 2450},
        {"label": "Okt", "kg": 3000},
    ]

    max_kg = max(m["kg"] for m in monthly)

    for m in monthly:
        m["percent"] = round(m["kg"] / max_kg * 100)

    total_waste_kg = 12480
    co2e_estimate = estimate_co2e_avoided(total_waste_kg)
    impact = {
        "total_waste_kg": f"{total_waste_kg:,}".replace(",", "."),
        "carbon_reduction_kg": f"{int(co2e_estimate):,}".replace(",", "."),
        "points_per_kg": POINTS_PER_KILOGRAM,
        "monthly": monthly,
        # Jumlah akun Mitra terdaftar (data nyata)
        "partner_count": UserProfile.objects.filter(role='mitra').count(),
    }

    return render(
        request,
        'index.html',
        {'impact': impact}
    )


MODULE_TITLES = {
    "pickup": "Pickup",
    "courier": "Courier",
    "store": "Store",
    "rewards": "Rewards",
    "katalog": "Katalog",
    "lacak-pesanan": "Lacak Pesanan",
    "mitra-dashboard": "Dashboard Mitra",
    "courier-dashboard": "Dashboard Courier",
    "routes": "Rute Courier",
}


def coming_soon(request, module):
    title = MODULE_TITLES.get(
        module,
        module.replace("-", " ").title()
    )

    return render(
        request,
        'coming_soon.html',
        {'module_title': title}
    )

@role_required(['admin'])
def admin_dashboard(request):
    return render(request, 'admin/dashboard.html')
