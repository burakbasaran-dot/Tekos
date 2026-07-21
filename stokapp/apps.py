from django.apps import AppConfig


class StokappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'stokapp'

    def ready(self):
        import stokapp.signals  # noqa: F401
        import stokapp.rbac_signals  # noqa: F401
        try:
            from django.db import OperationalError, connection
            from stokapp.mail_config import apply_mail_settings, ensure_mail_defaults_from_env
            from stokapp.models import GenelAyarlar

            tables = connection.introspection.table_names()
            if 'stokapp_genelayarlar' in tables:
                ayarlar = GenelAyarlar.get_ayarlar()
                ensure_mail_defaults_from_env(ayarlar)
                apply_mail_settings(ayarlar)
        except OperationalError:
            pass
        except Exception:
            pass