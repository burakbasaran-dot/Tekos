from django.contrib import admin

from core.models import (
    Company,
    CompanyMembership,
    Department,
    Plan,
    PlanModuleEntitlement,
    Subscription,
)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "setup_completed", "is_demo", "created_at")
    list_filter = ("is_active", "setup_completed", "is_demo")
    search_fields = ("name", "slug", "email")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(CompanyMembership)
class CompanyMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "role", "is_active", "is_default")
    list_filter = ("role", "is_active", "is_default", "company")
    search_fields = ("user__username", "company__name")
    autocomplete_fields = ("user", "company")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "is_active")
    list_filter = ("company", "is_active")
    search_fields = ("name", "company__name")


class PlanModuleEntitlementInline(admin.TabularInline):
    model = PlanModuleEntitlement
    extra = 1


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "monthly_price", "user_limit", "is_active", "trial_days")
    list_filter = ("is_active", "currency")
    search_fields = ("name", "code")
    prepopulated_fields = {"code": ("name",)}
    inlines = [PlanModuleEntitlementInline]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("company", "plan", "status", "start_date", "end_date", "trial_end_date")
    list_filter = ("status", "renewal_type", "plan")
    search_fields = ("company__name", "plan__code")
    autocomplete_fields = ("company", "plan")


@admin.register(PlanModuleEntitlement)
class PlanModuleEntitlementAdmin(admin.ModelAdmin):
    list_display = ("plan", "module_code", "is_enabled")
    list_filter = ("is_enabled", "plan")
