# TEKOS Platform Roadmap (Next)

## Tamamlanan temel

1. PostgreSQL production guard + docs
2. Multi-tenant Company / Membership / context
3. Company setup wizard
4. Subscription / Plan / entitlements (ödeme yok)
5. PlatformAuditLog (stokapp.AuditLog’dan ayrı)

## Henüz uygulanmayan tenant dönüşümleri

Mevcut stokapp modelleri (~145) **company FK almadı**.

Sıra önerisi:

1. Unique alanları `(company, …)` yapmak: `Depo.ad`, `StokItem.stok_kodu`, cari kodları, belge numaraları
2. `GenelAyarlar` singleton → company-scoped
3. RBAC rollerini company-scope
4. Null → backfill → NOT NULL
5. Tüm list/detail view’larda `for_company`

## Ödeme sistemi sonraki adımlar

1. Stripe veya iyzico `PaymentProvider` implementasyonu
2. Checkout + webhook imza doğrulama
3. Subscription status senkronu
4. `ayarlar/abonelik/` stub’ını platform UI’ye bağlama

## Audit sonraki adımlar

- Kullanıcı yönetimi UI olayları
- Export/import
- Retention job

## Media / storage

Render ephemeral disk → S3 uyumlu object storage

## Operasyon

- Branch protection + CI `workflow` scope ile Actions push
- Düzenli `pg_dump` + harici saklama
