from stokapp.actions.approve_supplier_offer import handle as approve_supplier_offer_handle
from stokapp.actions.create_production_order import handle as create_production_order_handle
from stokapp.actions.create_purchase_order import handle as create_purchase_order_handle
from stokapp.actions.bulk_create_purchase_request import handle as bulk_create_purchase_request_handle
from stokapp.actions.create_purchase_request import handle as create_purchase_request_handle
from stokapp.actions.create_sales_order import handle as create_sales_order_handle
from stokapp.actions.plan_payment import handle as plan_payment_handle
from stokapp.actions.send_customer_email import handle as send_customer_email_handle
from stokapp.actions.send_supplier_quote_request import handle as send_supplier_quote_request_handle


class ApprovalActionExecutor:
    HANDLERS = {
        "create_sales_order": create_sales_order_handle,
        "create_purchase_request": create_purchase_request_handle,
        "bulk_create_purchase_request": bulk_create_purchase_request_handle,
        "send_supplier_quote_request": send_supplier_quote_request_handle,
        "approve_supplier_offer": approve_supplier_offer_handle,
        "create_purchase_order": create_purchase_order_handle,
        "create_production_order": create_production_order_handle,
        "plan_payment": plan_payment_handle,
        "send_customer_email": send_customer_email_handle,
    }

    @classmethod
    def execute(cls, action_type, payload):
        handler = cls.HANDLERS.get(action_type)
        if not handler:
            raise ValueError(f"Desteklenmeyen action_type: {action_type}")
        return handler(payload or {})
