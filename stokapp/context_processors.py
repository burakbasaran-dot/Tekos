from django.db.models import F

from .constants import SYSTEM_AI_NAME
from .form_field_helps import build_help_config
from .models import GenelAyarlar, StokItem
from .nav_visibility import NAV_HIDDEN_ITEMS
from .rbac_utils import get_user_permissions


def kritik_stok_bildirimi(request):
    """Tüm sayfalarda kritik stok sayısını göster - sadece stok takibi yapılan ürünler"""
    if request.user.is_authenticated:
        kritik_sayisi = StokItem.objects.filter(
            stok_takip=True,
            mevcut_miktar__lte=F('minimum_stok')
        ).count()
        return {
            'kritik_stok_bildirim_sayisi': kritik_sayisi
        }
    return {'kritik_stok_bildirim_sayisi': 0}


def rbac_menus(request):
    """Şablonlarda menü / buton için yetki kodları ve modül bayrakları."""
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {
            'rbac_kodlar': frozenset(),
            'rbac_god': False,
            'rbac_stok_menu': False,
            'rbac_teklif_menu': False,
            'rbac_satinalma_menu': False,
            'rbac_yetkilendirme_menu': False,
            'rbac_arge_menu': False,
        }
    if request.user.is_superuser:
        from .models_rbac import SistemYetkisi

        kodlar = frozenset(SistemYetkisi.objects.values_list('kod', flat=True))
        return {
            'rbac_kodlar': kodlar,
            'rbac_god': True,
            'rbac_stok_menu': True,
            'rbac_teklif_menu': True,
            'rbac_satinalma_menu': True,
            'rbac_yetkilendirme_menu': True,
            'rbac_arge_menu': True,
        }
    kodlar = get_user_permissions(request.user)

    def _pfx(p):
        return any(x.startswith(p) for x in kodlar)

    return {
        'rbac_kodlar': kodlar,
        'rbac_god': False,
        'rbac_stok_menu': _pfx('stok.'),
        'rbac_teklif_menu': _pfx('teklif.'),
        'rbac_satinalma_menu': _pfx('satin_alma.'),
        'rbac_yetkilendirme_menu': 'sistem.yetkilendirme' in kodlar,
        'rbac_arge_menu': _pfx('arge.'),
    }


def nav_visibility(request):
    """Gizli menü öğeleri ve superuser önizleme bayrağı."""
    from .nav_visibility import can_see_hidden_nav

    user = getattr(request, 'user', None)
    show_hidden = can_see_hidden_nav(user) if user else False
    return {
        'nav_hidden_items': NAV_HIDDEN_ITEMS,
        # Gizli menü önizlemesi: yalnızca superuser (RBAC Admin rolü yeterli değil)
        'rbac_is_admin': show_hidden,
        'nav_show_hidden_items': show_hidden,
    }


def form_field_helps(request):
    """Tüm formlarda otomatik alan ipucu metinleri (manuel ipuculu sayfalar hariç)."""
    return {'form_field_help_config': build_help_config(request)}


def system_ai_context(request):
    tekora_aktif = True
    firma_logo_url = None
    firma_ismi = ''
    try:
        ayarlar = GenelAyarlar.get_ayarlar()
        tekora_aktif = bool(ayarlar.tekora_aktif)
        firma_ismi = ayarlar.firma_ismi or ''
        if ayarlar.firma_logo:
            firma_logo_url = ayarlar.firma_logo.url
    except Exception:
        tekora_aktif = True
    return {
        'system_ai_name': SYSTEM_AI_NAME,
        'tekora_aktif': tekora_aktif,
        'firma_logo_url': firma_logo_url,
        'firma_ismi': firma_ismi,
    }