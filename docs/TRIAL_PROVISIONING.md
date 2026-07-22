# Trial Provisioning

`core/services/provisioning.py` — `provision_trial_company()` transaction içinde User, Company, Membership, Subscription ve demo seed oluşturur.

Idempotent: `created_company` varsa tekrar oluşturmaz.

## Demo seed
`core/services/demo_seed.py` — `DEMO-{slug}-` prefix ile örnek stok/cari.

## Bilinen sınırlama
stokapp modelleri henüz company FK taşımıyor; örnek veriler prefix ile ayırt edilir.
