from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.contrib import messages
from django.views.decorators.http import require_POST

from .forms import RegisterForm


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)

        if form.is_valid():
            user = form.save()

            user_profile = user.userprofile
            user_profile.role = form.cleaned_data['role']
            user_profile.save()

            messages.success(
                request,
                'Registrasi berhasil! Silakan login menggunakan akun kamu.'
            )

            return redirect('login')

    else:
        form = RegisterForm()

    return render(
        request,
        'accounts/register.html',
        {'form': form}
    )


from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect


from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            profile = getattr(user, 'userprofile', None)
            role = profile.role if profile else None

            # Periksa apakah pengguna termasuk petugas
            is_petugas = user.groups.filter(
                name='Petugas GreenLoop'
            ).exists()

            # Login pengguna
            login(request, user)

            # Petugas dan admin langsung ke dashboard admin
            if (
                is_petugas
                or user.is_superuser
                or user.is_staff
                or role == 'admin'
            ):
                return redirect('admin_dashboard')

            # Kurir ke dashboard kurir
            if role == 'courier':
                return redirect('courier_dashboard')

            # Di fungsi register dan login_view:
            if role == 'mitra' or (profile and profile.role == 'mitra'):
                return redirect('/scheduling/dashboard/')  

            # Pengguna lainnya ke beranda
            return redirect('home')

        return render(
            request,
            'accounts/login.html',
            {'error': 'Username atau password salah.'}
        )

    return render(request, 'accounts/login.html')

@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def profile(request):
    profile = getattr(request.user, 'userprofile', None)

    return render(
        request,
        'accounts/profile.html',
        {'profile': profile}
    )

@login_required
def profile(request):
    profile = getattr(request.user, 'userprofile', None)

    return render(
        request,
        'accounts/profile.html',
        {'profile': profile}
    )




