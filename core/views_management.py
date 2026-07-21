"""Platform management list pages (read-oriented)."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_http_methods

from core.decorators import platform_manage_required
from core.models import Company, PlatformAuditLog
from core.services.tenancy import get_user_companies


@platform_manage_required
@require_GET
def company_list(request):
    companies = get_user_companies(request.user, active_only=False)
    return render(
        request,
        "core/company_list.html",
        {
            "page_title": "Firma Yönetimi",
            "breadcrumb": [("Yönetim", None), ("Firma Yönetimi", None)],
            "companies": companies,
        },
    )


@platform_manage_required
@require_GET
def demo_company_list(request):
    qs = Company.objects.filter(is_demo=True).order_by("name")
    if not request.user.is_superuser:
        allowed = set(get_user_companies(request.user, active_only=False).values_list("pk", flat=True))
        qs = qs.filter(pk__in=allowed)
    return render(
        request,
        "core/demo_company_list.html",
        {
            "page_title": "Demo Firmalar",
            "breadcrumb": [("Yönetim", None), ("Demo Firmalar", None)],
            "companies": qs,
        },
    )


@platform_manage_required
@require_GET
def system_health(request):
    vendor = connection.vendor
    engine = connection.settings_dict.get("ENGINE", "")
    # Short engine label only — no DSN / credentials
    engine_label = engine.rsplit(".", 1)[-1] if engine else "unknown"
    db_ok = False
    db_error = ""
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        db_ok = True
    except Exception as exc:
        db_error = type(exc).__name__

    pending = 0
    applied = 0
    try:
        executor = MigrationExecutor(connection)
        pending = len(executor.migration_plan(executor.loader.graph.leaf_nodes()))
        applied = len(executor.loader.applied_migrations)
    except Exception:
        pending = -1

    return render(
        request,
        "core/system_health.html",
        {
            "page_title": "Sistem Sağlığı",
            "breadcrumb": [("Sistem", None), ("Sistem Sağlığı", None)],
            "db_ok": db_ok,
            "db_error": db_error,
            "vendor": vendor,
            "engine_label": engine_label,
            "migrations_applied": applied,
            "migrations_pending": pending,
            "overall_ok": db_ok and pending == 0,
        },
    )


@platform_manage_required
@require_http_methods(["GET"])
def audit_log_list(request):
    qs = PlatformAuditLog.objects.select_related("company", "user").order_by("-created_at")
    if request.user.is_superuser:
        pass
    else:
        company = getattr(request, "company", None)
        if company is None:
            qs = qs.none()
        else:
            qs = qs.filter(company=company)

    action_filter = (request.GET.get("action") or "").strip()
    if action_filter:
        qs = qs.filter(action=action_filter)

    logs = list(qs[:200])
    return render(
        request,
        "core/audit_log_list.html",
        {
            "page_title": "Audit Log",
            "breadcrumb": [("Sistem", None), ("Audit Log", None)],
            "logs": logs,
            "action_filter": action_filter,
            "action_choices": PlatformAuditLog.ACTION_CHOICES,
            "is_superuser": request.user.is_superuser,
        },
    )
