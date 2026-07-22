"""Application management dashboard for platform admins."""

from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from core.decorators import platform_manage_required
from core.models import ApplicationUpload, SignupApplication
from core.services.applications import set_application_status
from core.services.audit import log_action
from core.services.conversion import convert_demo_to_customer
from core.services.email_verification import create_verification_token, resend_verification
from core.services.provisioning import provision_trial_company
from core.services.signup_email import send_developer_verification_email, send_trial_verification_email
from core.services.signup_security import store_pending_password


def _applications_queryset(request):
    qs = SignupApplication.objects.select_related(
        "created_user", "created_company", "created_subscription", "assigned_admin"
    )
    app_type = request.GET.get("type", "").strip()
    if app_type in (SignupApplication.TYPE_TRIAL, SignupApplication.TYPE_DEVELOPER):
        qs = qs.filter(application_type=app_type)
    status = request.GET.get("status", "").strip()
    if status:
        qs = qs.filter(status=status)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
            | Q(company_name__icontains=q)
            | Q(phone__icontains=q)
        )
    return qs.order_by("-created_at")


def _dashboard_stats():
    today = timezone.localdate()
    week_later = today + timedelta(days=7)
    return {
        "today_trials": SignupApplication.objects.filter(
            application_type=SignupApplication.TYPE_TRIAL,
            created_at__date=today,
        ).count(),
        "active_trials": SignupApplication.objects.filter(
            application_type=SignupApplication.TYPE_TRIAL,
            status=SignupApplication.STATUS_ACTIVE,
        ).count(),
        "expiring_soon": SignupApplication.objects.filter(
            application_type=SignupApplication.TYPE_TRIAL,
            status=SignupApplication.STATUS_ACTIVE,
            created_subscription__trial_end_date__lte=week_later,
            created_subscription__trial_end_date__gte=today,
        ).count(),
        "pending_developers": SignupApplication.objects.filter(
            application_type=SignupApplication.TYPE_DEVELOPER,
            status=SignupApplication.STATUS_REVIEW_PENDING,
        ).count(),
        "failed": SignupApplication.objects.filter(status=SignupApplication.STATUS_FAILED).count(),
    }


@platform_manage_required
@require_GET
def application_list(request):
    applications = list(_applications_queryset(request)[:200])
    return render(
        request,
        "core/applications/list.html",
        {
            "page_title": "Başvurular",
            "applications": applications,
            "stats": _dashboard_stats(),
            "status_choices": SignupApplication.STATUS_CHOICES,
            "type_filter": request.GET.get("type", ""),
            "status_filter": request.GET.get("status", ""),
            "q": request.GET.get("q", ""),
        },
    )


@platform_manage_required
@require_http_methods(["GET", "POST"])
def application_detail(request, pk: int):
    application = get_object_or_404(
        SignupApplication.objects.select_related(
            "created_user", "created_company", "created_subscription", "assigned_admin"
        ).prefetch_related("status_history", "uploads"),
        pk=pk,
    )
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "assign_me":
            application.assigned_admin = request.user
            application.save(update_fields=["assigned_admin", "updated_at"])
            messages.success(request, "Başvuru size atandı.")
        elif action == "approve":
            set_application_status(
                application,
                SignupApplication.STATUS_APPROVED,
                changed_by=request.user,
                note=request.POST.get("note", ""),
            )
            messages.success(request, "Başvuru onaylandı.")
        elif action == "reject":
            set_application_status(
                application,
                SignupApplication.STATUS_REJECTED,
                changed_by=request.user,
                note=request.POST.get("note", ""),
            )
            application.rejection_reason = (request.POST.get("note", "") or "")[:500]
            application.save(update_fields=["rejection_reason", "updated_at"])
            messages.success(request, "Başvuru reddedildi.")
        elif action == "resend_verification":
            try:
                token = resend_verification(application)
                if application.application_type == SignupApplication.TYPE_TRIAL:
                    send_trial_verification_email(application, token)
                else:
                    send_developer_verification_email(application, token)
                messages.success(request, "Doğrulama e-postası yeniden gönderildi.")
            except Exception as exc:
                messages.error(request, str(exc))
        elif action == "retry_provisioning":
            if application.application_type != SignupApplication.TYPE_TRIAL:
                messages.error(request, "Yalnızca deneme başvuruları için geçerli.")
            else:
                pw = request.POST.get("temp_password", "").strip()
                if not pw:
                    messages.error(request, "Geçici şifre gerekli (güvenli kanaldan iletin).")
                else:
                    result = provision_trial_company(
                        application, pw, request=request, force=True
                    )
                    if result.success:
                        messages.success(request, "Provisioning tamamlandı.")
                    else:
                        messages.error(request, result.error or "Provisioning başarısız.")
        elif action == "extend_trial":
            days = int(request.POST.get("days", "7") or "7")
            sub = application.created_subscription
            if sub and sub.trial_end_date:
                sub.trial_end_date += timedelta(days=days)
                sub.end_date = sub.trial_end_date
                sub.save(update_fields=["trial_end_date", "end_date", "updated_at"])
                messages.success(request, f"Deneme {days} gün uzatıldı.")
        elif action == "convert_customer":
            company = application.created_company
            if not company:
                messages.error(request, "Firma bulunamadı.")
            else:
                from core.models import Plan

                plan = Plan.objects.filter(code="standard").first()
                convert_demo_to_customer(
                    company,
                    plan,
                    keep_sample_data=request.POST.get("keep_data") == "on",
                    changed_by=request.user,
                    request=request,
                )
                messages.success(request, "Firma müşteriye dönüştürüldü.")
        elif action == "add_note":
            note = (request.POST.get("note", "") or "").strip()
            if note:
                application.internal_notes = (
                    application.internal_notes + "\n" + note
                ).strip()
                application.save(update_fields=["internal_notes", "updated_at"])
                messages.success(request, "Not eklendi.")
        log_action(
            action="update",
            user=request.user,
            model_name="SignupApplication",
            object_id=application.pk,
            object_repr=f"admin:{action}",
            request=request,
        )
        return redirect("core:application_detail", pk=application.pk)

    return render(
        request,
        "core/applications/detail.html",
        {
            "page_title": f"Başvuru #{application.pk}",
            "application": application,
        },
    )


@platform_manage_required
@require_GET
def application_cv_download(request, pk: int, upload_id: int):
    application = get_object_or_404(SignupApplication, pk=pk)
    upload = get_object_or_404(ApplicationUpload, pk=upload_id, application=application)
    if not upload.file:
        raise Http404()
    return FileResponse(upload.file.open("rb"), as_attachment=True, filename=upload.original_name)
