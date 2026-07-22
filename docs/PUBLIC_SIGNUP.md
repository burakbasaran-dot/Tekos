# Public Signup

## Amaç
Giriş sayfasından trial ve geliştirici başvurusu almak; trial için otomatik demo firma oluşturmak.

## Kullanıcı akışı
1. `/accounts/login/` → CTA butonları
2. Form doldur → e-posta doğrulama
3. Trial: otomatik provisioning → hoş geldiniz
4. Developer: `review_pending` → admin inceleme

## Veri modeli
`SignupApplication`, `ApplicationStatusHistory`, `EmailVerificationToken`, `LegalDocument`, `ApplicationUpload`

## Güvenlik
Rate limit, honeypot, CAPTCHA soyut katmanı, şifre session'da (DB'de değil).

## Environment
`PUBLIC_SIGNUP_ENABLED`, `TRIAL_DAYS`, `ADMIN_NOTIFICATION_EMAIL` — bkz. `RENDER_SIGNUP_ENVIRONMENT.md`
