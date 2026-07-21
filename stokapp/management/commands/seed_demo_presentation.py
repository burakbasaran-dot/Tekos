"""
Tüm modüllere demo sunum verisi doldurur (modül başına 3–4 kayıt).

Kullanım:
    python manage.py seed_demo_presentation
    python manage.py seed_demo_presentation --count 4
"""

from django.core.management.base import BaseCommand

from stokapp.demo_seed import run_demo_seed


class Command(BaseCommand):
    help = 'Sunum için tüm modüllere mantıklı demo verileri doldurur (DEMO- önekli, tekrar çalıştırılabilir).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=4,
            help='Her modül için oluşturulacak kayıt sayısı (varsayılan: 4)',
        )

    def handle(self, *args, **options):
        count = options['count']
        self.stdout.write(self.style.MIGRATE_HEADING(f'Demo sunum verisi dolduruluyor ({count} kayıt/modül)...'))
        ctx = run_demo_seed(count=count, stdout=self.stdout, style=self.style)
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Demo veri doldurma tamamlandı.'))
        self.stdout.write(f'  Stok: {len(ctx.get("stoklar", []))} | Müşteri: {len(ctx.get("musteriler", []))} | Tedarikçi: {len(ctx.get("tedarikciler", []))}')
        self.stdout.write(f'  Sipariş: {len(ctx.get("siparisler", []))} | Teklif: {len(ctx.get("teklifler", []))} | Personel: {len(ctx.get("personeller", []))}')
