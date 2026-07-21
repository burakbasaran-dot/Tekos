"""Redirect incomplete company setups to the wizard."""

from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

from core.models import CompanyMembership


class SetupWizardMiddleware(MiddlewareMixin):
    EXEMPT_PREFIXES = (
        "/platform/setup/",
        "/platform/company/",
        "/accounts/",
        "/admin/",
        "/api/",
        "/static/",
        "/media/",
    )

    def process_request(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or user.is_superuser:
            return None

        path = request.path or ""
        if any(path.startswith(p) for p in self.EXEMPT_PREFIXES):
            return None

        company = getattr(request, "company", None)
        if company is None:
            # User has membership but no resolved company — still check incomplete
            membership = (
                CompanyMembership.objects.filter(user=user, is_active=True)
                .select_related("company")
                .first()
            )
            company = membership.company if membership else None

        if company and not company.setup_completed:
            return redirect(f"/platform/setup/{1}/")
        return None
