from core.services.tenancy import user_can_manage_platform


def platform_menus(request):
    """Sidebar: Yönetim / Sistem groups."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"platform_manage_menu": False}
    return {"platform_manage_menu": user_can_manage_platform(request.user)}
