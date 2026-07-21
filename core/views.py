from django.db import connection
from django.http import JsonResponse


def health(request):
    """Lightweight health check for Render / load balancers. No secrets."""
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "error"}, status=503)

    return JsonResponse({"status": "ok"})
