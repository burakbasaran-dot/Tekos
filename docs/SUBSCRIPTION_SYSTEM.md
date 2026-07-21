# Subscription & Licensing

## Amaç

Ödeme sisteminden bağımsız plan / abonelik / modül yetkisi altyapısı.

## Mimari

- `Plan`, `Subscription`, `PlanModuleEntitlement`
- Servisler: `core.services.licensing`
- Ödeme arayüzü: `PaymentProvider` + `NullPaymentProvider` (`core.services.payments`)
- Pilot yazma kısıtı: `@require_writable_subscription` (yalnızca platform uçları)

Süresi dolmuş / trial bitmiş → **salt okunur** (kullanıcı dostu). Superuser muaf.

## Kullanılan modeller

Plan, Subscription, PlanModuleEntitlement; Company ilişkisi

## Kullanıcı akışı

1. Seed: `free_trial` + `standard` planları
2. Mevcut company’lere trial subscription
3. Admin’den plan/abonelik yönetimi

Mevcut `ayarlar/abonelik/` stub’ına dokunulmadı.

## Güvenlik

- Limit: `can_add_user`
- Modül: `plan_has_module`
- Secret ödeme anahtarı yok (henüz)

## Testler

`core.tests.test_licensing`

## Manuel işlemler

Admin → Plan / Subscription düzenleme; production’da fiyatları güncelleyin.

## Gelecek — ödeme entegrasyonu

1. `PaymentProvider` implementasyonu (Stripe veya iyzico)
2. Checkout session + success/cancel URL
3. Webhook endpoint (`/platform/billing/webhook/`) — imza doğrulama
4. Subscription status senkronu (`active`, `past_due`, `cancelled`)
5. Fatura / makbuz saklama

Webhook dokümanı (tasarım):

```
POST /platform/billing/webhook/
Headers: provider signature
Body: provider event JSON
→ parse_webhook → update Subscription.status / end_date
```
