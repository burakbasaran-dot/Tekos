"""Public signup forms."""

from __future__ import annotations

import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from core.constants import (
    COMPANY_SIZE_CHOICES,
    EXPERIENCE_LEVEL_CHOICES,
    INDUSTRY_CHOICES,
    TECHNOLOGY_CHOICES,
    TRIAL_MODULE_CHOICES,
    WORK_STYLE_CHOICES,
)
from core.models import LegalDocument, SignupApplication
from core.services.signup_security import validate_cv_upload, validate_honeypot

User = get_user_model()
PHONE_RE = re.compile(r"^\+?[\d\s\-()]{10,20}$")


class HoneypotMixin(forms.Form):
    website_url = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_website_url(self):
        validate_honeypot(self.cleaned_data.get("website_url", ""))
        return ""


class LegalConsentMixin(forms.Form):
    kvkk_accepted = forms.BooleanField(
        required=True,
        label="KVKK Aydınlatma Metni'ni okudum ve kabul ediyorum.",
    )
    terms_accepted = forms.BooleanField(
        required=True,
        label="Kullanım Koşulları'nı okudum ve kabul ediyorum.",
    )
    commercial_communication_accepted = forms.BooleanField(
        required=False,
        label="Ticari elektronik ileti almak istiyorum.",
    )

    def _active_legal_versions(self):
        versions = {}
        for doc in LegalDocument.objects.filter(is_active=True):
            versions[doc.doc_type] = doc.version
        return versions


class TrialSignupForm(HoneypotMixin, LegalConsentMixin, forms.Form):
    first_name = forms.CharField(max_length=80, label="Ad")
    last_name = forms.CharField(max_length=80, label="Soyad")
    email = forms.EmailField(label="E-posta")
    phone = forms.CharField(max_length=40, label="Telefon")
    company_name = forms.CharField(max_length=200, label="Firma adı")
    industry = forms.ChoiceField(choices=INDUSTRY_CHOICES, label="Sektör")
    city = forms.CharField(max_length=80, label="Şehir")
    company_size = forms.ChoiceField(choices=COMPANY_SIZE_CHOICES, label="Çalışan sayısı")
    username_preference = forms.CharField(
        max_length=150, required=False, label="Tercih edilen kullanıcı adı"
    )
    password1 = forms.CharField(widget=forms.PasswordInput, label="Şifre")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Şifre tekrarı")
    job_title = forms.CharField(max_length=120, required=False, label="Görev / unvan")
    website = forms.URLField(required=False, label="Web sitesi")
    trial_modules = forms.MultipleChoiceField(
        choices=TRIAL_MODULE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Denemek istediğiniz modüller",
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Beklentiniz",
    )
    source = forms.CharField(widget=forms.HiddenInput, required=False)

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "").strip()
        if not PHONE_RE.match(phone):
            raise ValidationError("Geçerli bir telefon numarası girin.")
        return phone

    def clean_email(self):
        return self.cleaned_data["email"].lower().strip()

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Şifreler eşleşmiyor.")
        if p1:
            validate_password(p1)
        return cleaned

    def save_application(self, request) -> SignupApplication:
        from core.services.applications import capture_request_meta, set_application_status

        data = self.cleaned_data
        app = SignupApplication.objects.create(
            application_type=SignupApplication.TYPE_TRIAL,
            status=SignupApplication.STATUS_EMAIL_VERIFICATION_PENDING,
            first_name=data["first_name"],
            last_name=data["last_name"],
            email=data["email"],
            phone=data["phone"],
            company_name=data["company_name"],
            industry=data["industry"],
            city=data["city"],
            company_size=data["company_size"],
            username_preference=data.get("username_preference", ""),
            job_title=data.get("job_title", ""),
            website=data.get("website", ""),
            trial_modules=data.get("trial_modules") or [],
            message=data.get("message", ""),
            source=data.get("source", ""),
            kvkk_accepted=data["kvkk_accepted"],
            terms_accepted=data["terms_accepted"],
            commercial_communication_accepted=data.get("commercial_communication_accepted", False),
            legal_document_versions=self._active_legal_versions(),
        )
        capture_request_meta(app, request)
        app.save()
        set_application_status(
            app,
            SignupApplication.STATUS_EMAIL_VERIFICATION_PENDING,
            note="Trial başvurusu gönderildi",
        )
        return app


class DeveloperSignupForm(HoneypotMixin, LegalConsentMixin, forms.Form):
    first_name = forms.CharField(max_length=80, label="Ad")
    last_name = forms.CharField(max_length=80, label="Soyad")
    email = forms.EmailField(label="E-posta")
    phone = forms.CharField(max_length=40, label="Telefon")
    city = forms.CharField(max_length=80, label="Şehir")
    country = forms.CharField(max_length=80, initial="Türkiye", label="Ülke")
    company_name = forms.CharField(max_length=200, label="Mevcut iş / şirket")
    job_title = forms.CharField(max_length=120, label="Uzmanlık alanı")
    experience_level = forms.ChoiceField(
        choices=EXPERIENCE_LEVEL_CHOICES, label="Deneyim seviyesi"
    )
    work_style = forms.ChoiceField(choices=WORK_STYLE_CHOICES, label="Çalışma biçimi")
    technologies = forms.MultipleChoiceField(
        choices=TECHNOLOGY_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Bildiğiniz teknolojiler",
    )
    github_url = forms.URLField(required=False, label="GitHub")
    linkedin_url = forms.URLField(required=False, label="LinkedIn")
    portfolio_url = forms.URLField(required=False, label="Portföy")
    website = forms.URLField(required=False, label="Kişisel web sitesi")
    weekly_hours = forms.CharField(max_length=40, required=False, label="Haftalık ayırabileceğiniz süre")
    motivation = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        required=False,
        label="Neden TEKOS geliştiricisi olmak istiyorsunuz?",
    )
    contribution_modules = forms.CharField(
        required=False,
        label="Katkı sağlamak istediğiniz modüller",
    )
    cv_file = forms.FileField(required=False, label="Özgeçmiş (PDF/Word)")
    source = forms.CharField(widget=forms.HiddenInput, required=False)

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "").strip()
        if not PHONE_RE.match(phone):
            raise ValidationError("Geçerli bir telefon numarası girin.")
        return phone

    def clean_email(self):
        return self.cleaned_data["email"].lower().strip()

    def clean_cv_file(self):
        f = self.cleaned_data.get("cv_file")
        if f:
            validate_cv_upload(f)
        return f

    def save_application(self, request) -> SignupApplication:
        from core.models import ApplicationUpload
        from core.services.applications import capture_request_meta, set_application_status

        data = self.cleaned_data
        profile = {
            "experience_level": data["experience_level"],
            "work_style": data["work_style"],
            "technologies": data.get("technologies") or [],
            "github_url": data.get("github_url", ""),
            "linkedin_url": data.get("linkedin_url", ""),
            "portfolio_url": data.get("portfolio_url", ""),
            "weekly_hours": data.get("weekly_hours", ""),
            "motivation": data.get("motivation", ""),
            "contribution_modules": data.get("contribution_modules", ""),
        }
        app = SignupApplication.objects.create(
            application_type=SignupApplication.TYPE_DEVELOPER,
            status=SignupApplication.STATUS_EMAIL_VERIFICATION_PENDING,
            first_name=data["first_name"],
            last_name=data["last_name"],
            email=data["email"],
            phone=data["phone"],
            city=data["city"],
            country=data.get("country", "Türkiye"),
            company_name=data["company_name"],
            job_title=data["job_title"],
            website=data.get("website", ""),
            developer_profile=profile,
            source=data.get("source", ""),
            kvkk_accepted=data["kvkk_accepted"],
            terms_accepted=data["terms_accepted"],
            legal_document_versions=self._active_legal_versions(),
        )
        capture_request_meta(app, request)
        app.save()
        set_application_status(
            app,
            SignupApplication.STATUS_EMAIL_VERIFICATION_PENDING,
            note="Geliştirici başvurusu gönderildi",
        )
        cv = data.get("cv_file")
        if cv:
            ApplicationUpload.objects.create(
                application=app,
                file=cv,
                original_name=cv.name,
                content_type=cv.content_type or "",
            )
        return app
