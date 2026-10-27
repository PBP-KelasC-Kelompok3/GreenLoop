from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render


from .forms import RegisterForm


def redirect_after_login(user):
    """Mengarahkan user ke halaman utama sesuai rolenya."""
    profile = getattr(user, 'userprofile', None)

    if profile is not None and profile.role == 'courier':
        return redirect('courier:show_dashboard')

    if profile is not None and profile.role == 'admin':
        return redirect('admin_dashboard')

    return redirect('home')


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                user = form.save()

                user.userprofile.role = form.cleaned_data['role']
                user.userprofile.save()

                # Data usaha (Mitra) / kendaraan (Kurir) ke profil masing-masing
                form.save_role_profile(user)

            login(request, user)
            return redirect_after_login(user)
    else:
        # ?role=mitra memilih kartu peran sejak awal (dipakai tombol "Daftar Mitra")
        initial_role = request.GET.get('role')
        initial = {'role': initial_role} if initial_role in ('consumer', 'mitra', 'courier') else {}
        form = RegisterForm(initial=initial)

    return render(request, 'accounts/register.html', {'form': form})


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
            login(request, user)
            return redirect_after_login(user)

        return render(
            request,
            'accounts/login.html',
            {'error': 'Username atau password salah.'}
        )

    return render(request, 'accounts/login.html')

def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
def profile(request):
    profile = getattr(request.user, 'userprofile', None)

    return render(
        request,
        'accounts/profile.html',
        {'profile': profile}
    )