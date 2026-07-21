# Firma Kurulum Sihirbazı

## Amaç

Yeni firmanın temel bilgilerini adım adım tamamlamak; mevcut ERP ekranlarını bozmamak.

## Mimari

- URL: `/platform/setup/` ve `/platform/setup/<step>/`
- Draft: `CompanySetupDraft` (JSON + current_step)
- Guard: `SetupWizardMiddleware` — `setup_completed=False` ise ana uygulamaya gitmeden wizard
- Superuser muaf (`?skip=1` veya middleware bypass)

## Kullanılan modeller

Company, CompanySetupDraft, Department, CompanyMembership; seed için `stokapp.Depo.get_or_create`

## Kullanıcı akışı

1–7: Firma bilgileri → Logo → Departmanlar → Depolar → Kullanıcılar → Tercihler → Özet → tamamla

Yarım kalan kurulum draft üzerinden devam eder.

## Güvenlik

- Login zorunlu
- Yalnızca erişilebilir company
- GenelAyarlar’a yalnızca boş alan soft-sync

## Testler

`core.tests.test_setup_wizard`

## Manuel işlemler

Yok.

## Gelecek

- E-posta ile kullanıcı daveti
- Depo’ya company FK
- Tema/renklerin UI’ye bağlanması
