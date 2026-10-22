from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import RegisterForm


def redirect_after_login(user):
    """Mengarahkan user ke halaman utama sesuai rolenya."""
    profile = getattr(user, 'userprofile', None)

    if profile is not None and profile.role == 'courier':
        return redirect('courier:show_dashboard')

    return redirect('home')


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)

        if form.is_valid():
            user = form.save()

            user.userprofile.role = form.cleaned_data['role']
            user.userprofile.save()

            login(request, user)
            return redirect_after_login(user)
    else:
        form = RegisterForm()

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