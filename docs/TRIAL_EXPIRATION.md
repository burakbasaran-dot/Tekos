# Trial Expiration

Komut: `python manage.py process_trial_expirations`

- 7/3/1 gün kala hatırlatma e-postaları
- Süre dolunca `Subscription.STATUS_EXPIRED`
- Render Cron: günlük `0 6 * * *`
