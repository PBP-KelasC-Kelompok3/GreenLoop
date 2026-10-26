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

            # Login terlebih dahulu
            login(request, user)

            # Admin dan petugas langsung ke Panel Admin
            is_petugas = user.groups.filter(
                name='Petugas GreenLoop'
            ).exists()

            if user.is_superuser or user.is_staff or role == 'admin' or is_petugas:
                return redirect('admin_dashboard')

            # Kurir langsung ke dashboard kurir
            elif role == 'courier':
                return redirect('courier_dashboard')

            # Mitra langsung ke dashboard mitra
            elif role == 'mitra':
                return redirect('mitra_dashboard')

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




