from django.shortcuts import render
from accounts.decorator import role_required


@role_required(['courier'])
def show_dashboard(request):
    return render(request, "courier/dashboard.html")