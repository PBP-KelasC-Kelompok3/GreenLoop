from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from courier.models import CourierProfile


class CourierApprovalMiddleware:
    """Batasi akun kurir yang belum disetujui ke halaman tunggu verifikasi."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.pending_path = reverse("courier:pending_verification")
        self.logout_path = reverse("logout")

    def __call__(self, request):
        user = request.user
        profile = getattr(user, "userprofile", None) if user.is_authenticated else None

        if (
            profile
            and profile.role == "courier"
            and not user.is_staff
            and not user.is_superuser
            and not self._is_allowed_path(request.path_info)
        ):
            courier_profile = CourierProfile.objects.filter(user_id=user.pk).only("is_approved").first()
            if not courier_profile or not courier_profile.is_approved:
                return redirect("courier:pending_verification")

        return self.get_response(request)

    def _is_allowed_path(self, path):
        return (
            path in (self.pending_path, self.logout_path)
            or path.startswith(settings.STATIC_URL)
            or bool(settings.MEDIA_URL and path.startswith(settings.MEDIA_URL))
        )
