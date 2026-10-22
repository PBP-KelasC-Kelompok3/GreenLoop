from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def role_required(allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            profile = getattr(request.user, 'userprofile', None)

            if profile is None:
                return redirect('home')

            if profile.role not in allowed_roles:
                return redirect('home')

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator