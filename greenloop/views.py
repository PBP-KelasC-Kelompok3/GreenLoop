from django.shortcuts import render


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

    impact = {
        "total_waste_kg": "12.480",
        "carbon_reduction_kg": "8.740",
        "monthly": monthly,
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