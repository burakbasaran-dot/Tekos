# Multi-Tenant Foundation

## Amaç

Firma (Company) bazlı mantıksal ayrım için temel modeller ve request context.

## Mimari

- `Company` + `CompanyMembership` (`core`)
- `TenantMiddleware` → `request.company` / `request.tenant`
- Session key: `active_company_id`
- Superuser tüm aktif firmaları görebilir
- Subdomain / custom_domain alanı reserved; routing henüz aktif değil

## Kullanılan modeller

- Company
- CompanyMembership (owner/admin/member)
- Department (wizard için, company-scoped)
- CompanySetupDraft (aşama 3)

## Kullanıcı akışı

1. Login
2. Üyeliklerden default / session firma
3. İsteğe bağlı `/platform/company/select/`

Mevcut kurulumda data migration bir Default Company oluşturur ve tüm kullanıcıları owner yapar (`setup_completed=True`).

## Güvenlik

- Kullanıcı yalnızca aktif üyelikli firmalara erişir
- Inactive company reddedilir (superuser hariç)

## Testler

`core.tests.test_tenancy`

## Manuel işlemler

Yok (migration bootstrap).

## Gelecek geliştirmeler — tenant dönüşüm roadmap

Mevcut ~145 stokapp modeli **henüz** company FK almadı.

Önerilen sıra:

1. Company + membership (bu aşama) ✓
2. Yüksek riskli unique alanlar: `(company, stok_kodu)`, `(company, Depo.ad)`, cari kodları
3. `GenelAyarlar` singleton → company-scoped settings
4. RBAC rollerinin company-scope’a alınması
5. Null company → backfill → NOT NULL
6. Tüm queryset’lerde `for_company`

Subdomain: `slug.tekos.app` ileride Host header ile çözülecek.
