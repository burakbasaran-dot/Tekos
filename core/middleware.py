from django.utils.deprecation import MiddlewareMixin

from core.services.tenancy import resolve_company_from_request


class TenantMiddleware(MiddlewareMixin):
    """Attach request.company / request.tenant from session + membership."""

    def process_request(self, request):
        company = resolve_company_from_request(request)
        request.company = company
        request.tenant = company
