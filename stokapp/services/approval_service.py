from django.utils import timezone

from stokapp.models import ApprovalRequest
from stokapp.services.approval_action_executor import ApprovalActionExecutor


REQUIRES_EXPLICIT_APPROVAL = {
    "send_supplier_quote_request",
    "approve_supplier_offer",
    "create_purchase_order",
    "create_production_order",
    "plan_payment",
}


def can_execute_without_approval(action_type):
    return action_type not in REQUIRES_EXPLICIT_APPROVAL


def execute_direct_if_allowed(action_type, payload):
    if not can_execute_without_approval(action_type):
        raise PermissionError(f"{action_type} işlemi kullanıcı onayı olmadan çalıştırılamaz.")
    return ApprovalActionExecutor.execute(action_type, payload)


def serialize_approval_request(obj):
    return {
        "id": str(obj.id),
        "action_type": obj.action_type,
        "title": obj.title,
        "description": obj.description,
        "ai_summary": obj.ai_summary,
        "payload": obj.payload,
        "risk_level": obj.risk_level,
        "status": obj.status,
        "source": obj.source,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
        "approved_by": obj.approved_by,
        "approved_at": obj.approved_at.isoformat() if obj.approved_at else None,
        "rejected_by": obj.rejected_by,
        "rejected_at": obj.rejected_at.isoformat() if obj.rejected_at else None,
        "reject_reason": obj.reject_reason,
        "executed_at": obj.executed_at.isoformat() if obj.executed_at else None,
        "error_message": obj.error_message,
    }


def approve_request(approval_request, username):
    approval_request.status = ApprovalRequest.STATUS_APPROVED
    approval_request.approved_by = username
    approval_request.approved_at = timezone.now()
    approval_request.error_message = None
    approval_request.rejected_by = None
    approval_request.rejected_at = None
    approval_request.reject_reason = None
    approval_request.save(update_fields=[
        "status",
        "approved_by",
        "approved_at",
        "error_message",
        "rejected_by",
        "rejected_at",
        "reject_reason",
        "updated_at",
    ])

    try:
        execution_payload = {
            **(approval_request.payload or {}),
            "_approved_by": username,
            "_approval_request_id": str(approval_request.id),
        }
        result = ApprovalActionExecutor.execute(approval_request.action_type, execution_payload)

        payload_updates = (result or {}).get("payload_updates") or {}
        if payload_updates:
            merged_payload = {**(approval_request.payload or {}), **payload_updates}
            approval_request.payload = merged_payload

        approval_request.status = ApprovalRequest.STATUS_EXECUTED
        approval_request.executed_at = timezone.now()
        approval_request.error_message = None
        update_fields = ["status", "executed_at", "error_message", "updated_at"]
        if payload_updates:
            update_fields.append("payload")
        approval_request.save(update_fields=update_fields)
        return {"ok": True, "execution_result": result}
    except Exception as exc:
        approval_request.status = ApprovalRequest.STATUS_FAILED
        approval_request.error_message = str(exc)
        approval_request.save(update_fields=["status", "error_message", "updated_at"])
        return {"ok": False, "error": str(exc)}
