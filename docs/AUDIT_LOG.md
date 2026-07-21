# Platform Audit Log

## Amaç

Kritik platform işlemlerini kim / ne zaman / ne değişti sorularına cevap vermek.

## Mimari

- Model: `PlatformAuditLog` (`core_platform_audit_log`)
- **Not:** `stokapp.AuditLog` ayrıdır (kalite alan logları); karıştırılmamalı
- Servis: `core.services.audit.log_action` + hassas alan redaction
- Middleware: `AuditRequestMiddleware` → `request.audit_ip`
- Signals: login/logout; Company / CompanyMembership / Subscription; RBAC `KullaniciRolu` / `RolYetkisi`

## Kullanılan modeller

PlatformAuditLog

## Kullanıcı akışı

Admin → Platform audit logs (filtre: user, company, action, model, tarih). Readonly; silme yalnız superuser.

## Güvenlik

Redact: password, token, secret, api_key, session, cookie, …

## Testler

`core.tests.test_audit`

## Retention / arşivleme

Öneri:

- Hot storage: 90 gün
- Cold archive (S3/dump): 1–2 yıl
- Aylık `PlatformAuditLog` export + partition / archive table ileride

Export şimdilik admin üzerinden manuel (CSV ileride).

## Manuel işlemler

Yok.

## Gelecek

- Stok/sipariş kritik modellerine explicit service çağrıları
- Asenkron yazma (queue) yüksek hacimde
