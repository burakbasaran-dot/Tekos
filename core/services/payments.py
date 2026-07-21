"""Payment provider interface — no live Stripe/iyzico integration yet."""

from __future__ import annotations

from typing import Any, Protocol


class PaymentProvider(Protocol):
    def create_checkout_session(self, *, company_id: int, plan_code: str, renewal: str) -> dict[str, Any]:
        """Return provider session payload (e.g. checkout URL)."""
        ...

    def parse_webhook(self, payload: bytes, headers: dict[str, str]) -> dict[str, Any]:
        """Normalize webhook event for subscription updates."""
        ...


class NullPaymentProvider:
    """Placeholder until a real provider is wired."""

    def create_checkout_session(self, *, company_id: int, plan_code: str, renewal: str) -> dict[str, Any]:
        return {
            "status": "not_configured",
            "company_id": company_id,
            "plan_code": plan_code,
            "renewal": renewal,
        }

    def parse_webhook(self, payload: bytes, headers: dict[str, str]) -> dict[str, Any]:
        return {"status": "ignored", "reason": "payment provider not configured"}


def get_payment_provider() -> PaymentProvider:
    return NullPaymentProvider()
