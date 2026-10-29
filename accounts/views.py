from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from waste_reward.points import POINTS_PER_KILOGRAM

from .forms import RegisterForm


def redirect_after_login(user):
    """Send each account to the dashboard for its role."""
    profile = getattr(user, 'userprofile', None)
    role = profile.role if profile else None
    is_petugas = user.groups.filter(name='Petugas GreenLoop').exists()

    if user.is_superuser or user.is_staff or is_petugas or role == 'admin':
        return redirect('/scheduling/admin-panel/')
    if role == 'courier':
        return redirect('courier:show_dashboard')
    if role == 'mitra':
        return redirect('mitra_dashboard')
    return redirect('home')


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                user.userprofile.role = form.cleaned_data['role']
                user.userprofile.save(update_fields=['role'])
                form.save_role_profile(user)

            login(request, user)
            messages.success(request, 'Registrasi berhasil. Selamat datang di GreenLoop!')
            return redirect_after_login(user)
    else:
        initial_role = request.GET.get('role')
        initial = {'role': initial_role} if initial_role in ('consumer', 'mitra', 'courier') else {}
        form = RegisterForm(initial=initial)

    return render(request, 'accounts/register.html', {
        'form': form,
        'points_per_kg': POINTS_PER_KILOGRAM,
    })


def login_view(request):
    if request.method == 'POST':
        user = authenticate(
            request,
            username=request.POST.get('username'),
            password=request.POST.get('password'),
        )
        if user is not None:
            login(request, user)
            return redirect_after_login(user)

        return render(
            request,
            'accounts/login.html',
            {'error': 'Username atau password salah.'},
        )

    return render(request, 'accounts/login.html')


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def profile(request):
    user_profile = getattr(request.user, 'userprofile', None)
    return render(request, 'accounts/profile.html', {'profile': user_profile})
