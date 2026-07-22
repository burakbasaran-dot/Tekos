from django.urls import path

from . import views
from . import views_applications
from . import views_management
from . import views_platform
from . import views_setup
from . import views_signup

urlpatterns = [
    path("health/", views.health, name="health"),
]

platform_urlpatterns = [
    path("company/select/", views_platform.company_select, name="company_select"),
    path("companies/", views_management.company_list, name="company_list"),
    path("demo-companies/", views_management.demo_company_list, name="demo_company_list"),
    path("system-health/", views_management.system_health, name="system_health"),
    path("audit-logs/", views_management.audit_log_list, name="audit_log_list"),
    path("subscription/", views_platform.subscription_status, name="subscription_status"),
    path("setup/", views_setup.setup_wizard, {"step": 1}, name="setup_wizard"),
    path("setup/<int:step>/", views_setup.setup_wizard, name="setup_wizard_step"),
    path("applications/", views_applications.application_list, name="application_list"),
    path("applications/<int:pk>/", views_applications.application_detail, name="application_detail"),
    path(
        "applications/<int:pk>/cv/<int:upload_id>/",
        views_applications.application_cv_download,
        name="application_cv_download",
    ),
    path("trial/welcome/", views_signup.trial_welcome, name="trial_welcome"),
]
