def can_manage_greenloop(user):
    """Akses admin GreenLoop yang dipakai lintas aplikasi."""
    if not user.is_authenticated:
        return False
    profile = getattr(user, "userprofile", None)
    return bool(
        user.is_superuser
        or user.is_staff
        or user.groups.filter(name="Petugas GreenLoop").exists()
        or (profile and profile.role == "admin")
    )
