def handle(payload):
    return {
        "success": True,
        "message": "Mock müşteri e-postası gönderildi.",
        "result": {
            "to": payload.get("email_sender"),
            "subject": payload.get("email_subject"),
        },
    }
