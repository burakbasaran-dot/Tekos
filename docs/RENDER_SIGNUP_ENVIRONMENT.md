# Render Signup Environment

```
PUBLIC_SIGNUP_ENABLED=True
TRIAL_SIGNUP_ENABLED=True
DEVELOPER_SIGNUP_ENABLED=True
TRIAL_DAYS=30
ADMIN_NOTIFICATION_EMAIL=admin@example.com
SITE_URL=https://tekos-9155.onrender.com
DEFAULT_FROM_EMAIL=noreply@example.com
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
CAPTCHA_ENABLED=False
APPLICATION_UPLOAD_MAX_MB=5
MAX_TRIALS_PER_EMAIL=1
MAX_TRIALS_PER_IP=5
```

Cron: `python manage.py process_trial_expirations` — günlük.
