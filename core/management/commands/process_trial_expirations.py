"""Expire trials and send reminder emails."""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import SignupApplication, Subscription
from core.services.audit import log_action
from core.services.signup_email import send_trial_expired_email, send_trial_reminder_email


class Command(BaseCommand):
    help = "Process trial expirations and send reminder emails (idempotent)."

    def handle(self, *args, **options):
        today = timezone.localdate()
        self._send_reminders(today)
        self._expire_trials(today)
        self.stdout.write(self.style.SUCCESS("Trial expiration processing complete."))

    def _send_reminders(self, today):
        active_apps = SignupApplication.objects.filter(
            application_type=SignupApplication.TYPE_TRIAL,
            status=SignupApplication.STATUS_ACTIVE,
            created_subscription__isnull=False,
        ).select_related("created_subscription")
        for app in active_apps:
            sub = app.created_subscription
            if not sub or not sub.trial_end_date:
                continue
            days_left = (sub.trial_end_date - today).days
            if days_left not in (7, 3, 1):
                continue
            flags = app.trial_notification_flags or {}
            key = f"reminder_{days_left}"
            if flags.get(key):
                continue
            if send_trial_reminder_email(app, days_left):
                flags[key] = True
                app.trial_notification_flags = flags
                app.save(update_fields=["trial_notification_flags", "updated_at"])

    def _expire_trials(self, today):
        subs = Subscription.objects.filter(
            status=Subscription.STATUS_TRIAL,
            trial_end_date__lt=today,
        ).select_related("company")
        for sub in subs:
            sub.status = Subscription.STATUS_EXPIRED
            sub.save(update_fields=["status", "updated_at"])
            app = SignupApplication.objects.filter(
                created_subscription=sub
            ).first()
            if app:
                flags = app.trial_notification_flags or {}
                if not flags.get("expired"):
                    send_trial_expired_email(app)
                    flags["expired"] = True
                    app.trial_notification_flags = flags
                    app.status = SignupApplication.STATUS_EXPIRED
                    app.save(update_fields=["trial_notification_flags", "status", "updated_at"])
            log_action(
                action="update",
                company=sub.company,
                model_name="Subscription",
                object_id=sub.pk,
                object_repr="trial_expired",
            )
