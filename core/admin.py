from django.contrib import admin

from core.models import Company, CompanyMembership, Department


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
