"""Company setup wizard views and completion logic."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from core.models import Company, CompanyMembership, CompanySetupDraft, Department
from core.services.tenancy import user_can_access_company

STEP_LABELS = {
    1: "Firma Bilgileri",
    2: "Firma Görseli",
    3: "Departmanlar",
    4: "Depolar",
    5: "Kullanıcılar",
    6: "Sistem Tercihleri",
    7: "Özet",
}

DEFAULT_DEPARTMENTS = ["Yönetim", "Üretim", "Satınalma", "Satış", "Depo"]
DEFAULT_WAREHOUSES = ["Ana Depo", "Üretim Deposu", "Sevkiyat Deposu"]


def _get_wizard_company(request):
    company = getattr(request, "company", None)
    if company and user_can_access_company(request.user, company):
        return company
    membership = (
        CompanyMembership.objects.filter(user=request.user, is_active=True)
        .select_related("company")
        .first()
    )
    return membership.company if membership else None


def _get_or_create_draft(company: Company) -> CompanySetupDraft:
    draft, _ = CompanySetupDraft.objects.get_or_create(company=company)
    return draft


def complete_setup(company: Company, draft: CompanySetupDraft, user) -> None:
    data = draft.data or {}
    company.name = (data.get("name") or company.name or "Yeni Firma").strip()
    company.short_name = (data.get("short_name") or "").strip()
    company.tax_office = (data.get("tax_office") or "").strip()
    company.tax_number = (data.get("tax_number") or "").strip()
    company.phone = (data.get("phone") or "").strip()
    company.email = (data.get("email") or "").strip()
    company.website = (data.get("website") or "").strip()
    company.address = (data.get("address") or "").strip()
    company.currency = (data.get("currency") or "TRY").strip()
    company.timezone = (data.get("timezone") or "Europe/Istanbul").strip()
    company.language = (data.get("language") or "tr").strip()
    company.date_format = (data.get("date_format") or "%d.%m.%Y").strip()
    try:
        company.default_vat = Decimal(str(data.get("default_vat", "20")))
    except (InvalidOperation, TypeError):
        company.default_vat = Decimal("20")
    company.setup_completed = True
    company.save()

    # Departments
    dept_names = data.get("departments") or DEFAULT_DEPARTMENTS
    for name in dept_names:
        name = (name or "").strip()
        if name:
            Department.objects.get_or_create(company=company, name=name)

    # Warehouses via existing Depo model (global unique name)
    warehouse_names = data.get("warehouses") or DEFAULT_WAREHOUSES
    try:
        from stokapp.models import Depo

        for name in warehouse_names:
            name = (name or "").strip()
            if name:
                Depo.objects.get_or_create(ad=name)
    except Exception:
        pass

    # Ensure current user is owner
    CompanyMembership.objects.update_or_create(
        user=user,
        company=company,
        defaults={
            "role": CompanyMembership.ROLE_OWNER,
            "is_active": True,
            "is_default": True,
        },
    )

    # Soft sync to GenelAyarlar only when empty (default company pattern)
    try:
        from stokapp.models import GenelAyarlar

        ayar = GenelAyarlar.get_ayarlar()
        if not (ayar.firma_ismi or "").strip():
            ayar.firma_ismi = company.name
        if not (ayar.telefon or "").strip() and company.phone:
            ayar.telefon = company.phone
        if not (ayar.email or "").strip() and company.email:
            ayar.email = company.email
        if not (ayar.vergi_dairesi or "").strip() and company.tax_office:
            ayar.vergi_dairesi = company.tax_office
        if not (ayar.vergi_no or "").strip() and company.tax_number:
            ayar.vergi_no = company.tax_number
        ayar.save()
    except Exception:
        pass

    draft.delete()


@login_required
@require_http_methods(["GET", "POST"])
def setup_wizard(request, step: int = 1):
    if request.user.is_superuser and request.GET.get("skip") == "1":
        return redirect("/stok/dashboard/")

    company = _get_wizard_company(request)
    if company is None:
        # Create a new company shell for first-time setup
        company = Company.objects.create(
            name="Yeni Firma",
            setup_completed=False,
            is_active=True,
        )
        CompanyMembership.objects.create(
            user=request.user,
            company=company,
            role=CompanyMembership.ROLE_OWNER,
            is_active=True,
            is_default=True,
        )
        request.session["active_company_id"] = company.pk
        request.company = company
        request.tenant = company

    if company.setup_completed and not request.user.is_superuser:
        return redirect("/stok/dashboard/")

    step = max(1, min(int(step), 7))
    draft = _get_or_create_draft(company)
    data = dict(draft.data or {})
    errors = []

    if request.method == "POST":
        action = request.POST.get("action", "next")
        if step == 1:
            name = (request.POST.get("name") or "").strip()
            if not name:
                errors.append("Firma adı zorunludur.")
            else:
                data.update(
                    {
                        "name": name,
                        "short_name": (request.POST.get("short_name") or "").strip(),
                        "tax_office": (request.POST.get("tax_office") or "").strip(),
                        "tax_number": (request.POST.get("tax_number") or "").strip(),
                        "phone": (request.POST.get("phone") or "").strip(),
                        "email": (request.POST.get("email") or "").strip(),
                        "website": (request.POST.get("website") or "").strip(),
                        "address": (request.POST.get("address") or "").strip(),
                    }
                )
        elif step == 2:
            if request.FILES.get("logo"):
                company.logo = request.FILES["logo"]
                company.save(update_fields=["logo", "updated_at"])
            data["theme"] = (request.POST.get("theme") or "default").strip()
        elif step == 3:
            raw = request.POST.get("departments") or "\n".join(DEFAULT_DEPARTMENTS)
            depts = [line.strip() for line in raw.splitlines() if line.strip()]
            if not depts:
                errors.append("En az bir departman gerekli.")
            else:
                data["departments"] = depts
        elif step == 4:
            raw = request.POST.get("warehouses") or "\n".join(DEFAULT_WAREHOUSES)
            whs = [line.strip() for line in raw.splitlines() if line.strip()]
            if not whs:
                errors.append("En az bir depo gerekli.")
            else:
                data["warehouses"] = whs
        elif step == 5:
            data["invite_note"] = (request.POST.get("invite_note") or "").strip()
        elif step == 6:
            data.update(
                {
                    "currency": (request.POST.get("currency") or "TRY").strip(),
                    "timezone": (request.POST.get("timezone") or "Europe/Istanbul").strip(),
                    "language": (request.POST.get("language") or "tr").strip(),
                    "date_format": (request.POST.get("date_format") or "%d.%m.%Y").strip(),
                    "default_vat": (request.POST.get("default_vat") or "20").strip(),
                }
            )
        elif step == 7:
            if action == "complete":
                if not (data.get("name") or company.name):
                    errors.append("Firma adı eksik; 1. adıma dönün.")
                else:
                    draft.data = data
                    draft.current_step = 7
                    draft.save()
                    complete_setup(company, draft, request.user)
                    return redirect("/stok/dashboard/")

        if not errors:
            draft.data = data
            if action == "back":
                draft.current_step = max(1, step - 1)
            else:
                draft.current_step = min(7, step + 1)
            draft.save()
            return redirect(f"/platform/setup/{draft.current_step}/")

    draft.current_step = step
    draft.data = data
    draft.save(update_fields=["current_step", "data", "updated_at"])

    return render(
        request,
        "core/setup_wizard.html",
        {
            "company": company,
            "step": step,
            "step_label": STEP_LABELS[step],
            "step_labels": STEP_LABELS,
            "data": data,
            "errors": errors,
            "default_departments": "\n".join(data.get("departments") or DEFAULT_DEPARTMENTS),
            "default_warehouses": "\n".join(data.get("warehouses") or DEFAULT_WAREHOUSES),
        },
    )
