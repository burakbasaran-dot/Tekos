from django.utils.deprecation import MiddlewareMixin

from core.services.audit import client_ip_from_request


class AuditRequestMiddleware(MiddlewareMixin):
    """Attach request.audit_ip for audit logging (safe X-Forwarded-For first hop)."""

    def process_request(self, request):
        request.audit_ip = client_ip_from_request(request)
