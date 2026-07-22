"""Public signup and email verification views."""

from __future__ import annotations

from django.contrib.auth import login
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from core.forms.signup import DeveloperSignupForm, TrialSignupForm
from core.models import LegalDocument, SignupApplication
from core.services.applications import set_application_status
from core.services.audit import log_action
from core.services.email_verification import (
    VerificationError,
    create_verification_token,
    verify_email_token,
)
from core.services.provisioning import provision_trial_company
from core.services.signup_email import (
    send_developer_admin_notification,
    send_developer_received_email,
    send_developer_verification_email,
    send_trial_verification_email,
)
from core.services.signup_security import (
    enforce_signup_rate_limits,
    pop_pending_password,
    store_pending_password,
    validate_captcha,
)
from core.services.signup_settings import developer_signup_enabled, trial_signup_enabled
from core.services.tenancy import set_active_company


def _signup_context(extra=None):
    ctx = {
        "kvkk_doc": LegalDocument.objects.filter(
            doc_type=LegalDocument.DOC_KVKK, is_active=True
        ).first(),
        "terms_doc": LegalDocument.objects.filter(
            doc_type=LegalDocument.DOC_TERMS, is_active=True
        ).first(),
    }
    if extra:
        ctx.update(extra)
    return ctx


@require_http_methods(["GET", "POST"])
def trial_register(request):
    if not trial_signup_enabled():
        raise Http404()
    if request.method == "POST":
        if request.session.get("trial_submit_lock"):
            return redirect("signup:signup_trial_pending")
        form = TrialSignupForm(request.POST)
        try:
            validate_captcha(request)
            if form.is_valid():
                enforce_signup_rate_limits(request, form.cleaned_data["email"])
                application = form.save_application(request)
                store_pending_password(request, application.pk, form.cleaned_data["password1"])
                token = create_verification_token(application)
                send_trial_verification_email(application, token)
                request.session["trial_submit_lock"] = True
                request.session["pending_app_id"] = application.pk
                log_action(
                    action="signup",
                    model_name="SignupApplication",
                    object_id=application.pk,
                    object_repr=str(application),
                    request=request,
                )
                return redirect("signup:signup_trial_pending")
        except Exception as exc:
            from django.core.exceptions import ValidationError

            if isinstance(exc, ValidationError):
                form.add_error(None, exc.message if hasattr(exc, "message") else str(exc))
    else:
        initial = {"source": request.GET.get("source", "login")}
        form = TrialSignupForm(initial=initial)
    return render(
        request,
        "core/signup/trial_register.html",
        _signup_context({"form": form, "page_title": "Ücretsiz Deneme — 30 Gün"}),
    )


@require_http_methods(["GET", "POST"])
def developer_register(request):
    if not developer_signup_enabled():
        raise Http404()
    if request.method == "POST":
        if request.session.get("dev_submit_lock"):
            return redirect("signup:signup_developer_pending")
        form = DeveloperSignupForm(request.POST, request.FILES)
        try:
            validate_captcha(request)
            if form.is_valid():
                enforce_signup_rate_limits(request, form.cleaned_data["email"])
                application = form.save_application(request)
                token = create_verification_token(application)
                send_developer_verification_email(application, token)
                request.session["dev_submit_lock"] = True
                request.session["pending_app_id"] = application.pk
                log_action(
                    action="signup",
                    model_name="SignupApplication",
                    object_id=application.pk,
                    object_repr=str(application),
                    request=request,
                )
                return redirect("signup:signup_developer_pending")
        except Exception as exc:
            from django.core.exceptions import ValidationError

            if isinstance(exc, ValidationError):
                form.add_error(None, exc.message if hasattr(exc, "message") else str(exc))
    else:
        initial = {"source": request.GET.get("source", "login")}
        form = DeveloperSignupForm(initial=initial)
    return render(
        request,
        "core/signup/developer_register.html",
        _signup_context({"form": form, "page_title": "Geliştirici Başvurusu"}),
    )


@require_GET
def trial_pending(request):
    return render(request, "core/signup/pending.html", {"type": "trial"})


@require_GET
def developer_pending(request):
    return render(request, "core/signup/pending.html", {"type": "developer"})


@require_GET
def verify_email(request, token: str):
    try:
        application = verify_email_token(token)
    except VerificationError as exc:
        return render(
            request,
            "core/signup/verify_result.html",
            {"success": False, "message": str(exc)},
        )

    if application.application_type == SignupApplication.TYPE_TRIAL:
        password = pop_pending_password(request, application.pk)
        if not password:
            return render(
                request,
                "core/signup/verify_result.html",
                {
                    "success": False,
                    "message": "Oturum süresi doldu. Lütfen başvuruyu yeniden gönderin.",
                },
            )
        result = provision_trial_company(application, password, request=request)
        if not result.success:
            return render(
                request,
                "core/signup/verify_result.html",
                {"success": False, "message": result.error or "Hesap oluşturulamadı."},
            )
        login(request, result.user, backend="django.contrib.auth.backends.ModelBackend")
        set_active_company(request, result.company)
        request.session.pop("trial_submit_lock", None)
        return redirect("core:trial_welcome")

    set_application_status(
        application,
        SignupApplication.STATUS_REVIEW_PENDING,
        note="E-posta doğrulandı, inceleme bekliyor",
    )
    send_developer_received_email(application)
    send_developer_admin_notification(application)
    request.session.pop("dev_submit_lock", None)
    return render(
        request,
        "core/signup/verify_result.html",
        {
            "success": True,
            "message": "E-posta doğrulandı. Başvurunuz incelenmek üzere alındı.",
        },
    )


@require_GET
def legal_kvkk(request):
    doc = get_object_or_404(LegalDocument, doc_type=LegalDocument.DOC_KVKK, is_active=True)
    return render(request, "core/signup/legal.html", {"doc": doc})


@require_GET
def legal_terms(request):
    doc = get_object_or_404(LegalDocument, doc_type=LegalDocument.DOC_TERMS, is_active=True)
    return render(request, "core/signup/legal.html", {"doc": doc})


@require_GET
def trial_welcome(request):
    if not request.user.is_authenticated:
        return redirect("login")
    company = getattr(request, "company", None)
    sub = None
    if company:
        from core.services.licensing import get_active_subscription

        sub = get_active_subscription(company)
    app = (
        SignupApplication.objects.filter(
            created_user=request.user,
            application_type=SignupApplication.TYPE_TRIAL,
        )
        .order_by("-created_at")
        .first()
    )
    return render(
        request,
        "core/signup/trial_welcome.html",
        {"company": company, "subscription": sub, "application": app},
    )
