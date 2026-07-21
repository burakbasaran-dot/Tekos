"""
Veritabanındaki SistemYetkisi kayıtlarını rbac_registry ile senkronize eder.
Yeni modül eklendiğinde bu komutu çalıştırın.
"""

from django.core.management.base import BaseCommand

from stokapp.models_rbac import SistemYetkisi
from stokapp.rbac_registry import RBAC_MODULE_ACTIONS, human_label, iter_permission_codes


class Command(BaseCommand):
    help = 'RBAC yetki kayıtlarını registry ile oluşturur / günceller.'

    def handle(self, *args, **options):
        created = 0
        for kod in iter_permission_codes():
            mod = kod.split('.', 1)[0]
            act = kod.split('.', 1)[1]
            ad = human_label(mod, act)
            obj, was_created = SistemYetkisi.objects.get_or_create(
                kod=kod,
                defaults={'ad': ad, 'modul': mod},
            )
            if was_created:
                created += 1
            else:
                if obj.ad != ad or obj.modul != mod:
                    obj.ad = ad
                    obj.modul = mod
                    obj.save(update_fields=['ad', 'modul'])
        self.stdout.write(self.style.SUCCESS(f'RBAC yetkileri güncellendi. Yeni: {created}'))
