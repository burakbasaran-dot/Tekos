from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from core.models import Company
from core.services.tenancy import get_user_companies, set_active_company


@login_required
@require_http_methods(["GET", "POST"])
def company_select(request):
    companies = list(get_user_companies(request.user))
    error = ""
    if request.method == "POST":
        company_id = request.POST.get("company_id")
        company = get_object_or_404(Company, pk=company_id)
        if set_active_company(request, company):
            next_url = request.GET.get("next") or "/stok/dashboard/"
            return redirect(next_url)
        error = "Bu firmaya erişim yetkiniz yok veya firma aktif değil."
    return render(
        request,
        "core/company_select.html",
        {
            "companies": companies,
            "active_company": getattr(request, "company", None),
            "error": error,
        },
    )
