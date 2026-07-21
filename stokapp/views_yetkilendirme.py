"""
Ayarlar > Yetkilendirme — roller, kullanıcı–rol, yetki listesi.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.conf import settings

from .models_rbac import KullaniciRolu, Rol, RolYetkisi, SistemYetkisi
from .rbac_registry import RBAC_MODULE_ACTIONS
from .rbac_utils import clear_user_permission_cache, has_permission


def _yetki_gate(request):
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)
    if not has_permission(request.user, 'sistem.yetkilendirme'):
        return render(
            request,
            'stokapp/rbac/403_yetki.html',
            {'gerekli_yetki': 'sistem.yetkilendirme'},
            status=403,
        )
    return None


@login_required
def yetkilendirme_roller(request):
    g = _yetki_gate(request)
    if g:
        return g
    roller = Rol.objects.annotate(kullanici_sayisi=Count('kullanicilar')).order_by('ad')
    return render(request, 'stokapp/yetkilendirme/roller.html', {'roller': roller})


@login_required
def yetkilendirme_rol_ekle(request):
    g = _yetki_gate(request)
    if g:
        return g
    yetkiler = list(SistemYetkisi.objects.order_by('modul', 'kod'))
    gruplar = {}
    for y in yetkiler:
        gruplar.setdefault(y.modul, []).append(y)
    if request.method == 'POST':
        ad = (request.POST.get('ad') or '').strip()
        slug = (request.POST.get('slug') or '').strip().lower().replace(' ', '-')
        aciklama = (request.POST.get('aciklama') or '').strip()
        if not ad or not slug:
            messages.error(request, 'Ad ve kod zorunludur.')
        elif Rol.objects.filter(slug=slug).exists():
            messages.error(request, 'Bu kodda bir rol zaten var.')
        else:
            with transaction.atomic():
                rol = Rol.objects.create(ad=ad, slug=slug, aciklama=aciklama)
                secili = request.POST.getlist('yetki')
                for kid in secili:
                    try:
                        y = SistemYetkisi.objects.get(pk=int(kid))
                        RolYetkisi.objects.get_or_create(rol=rol, yetki=y)
                    except (ValueError, SistemYetkisi.DoesNotExist):
                        pass
            messages.success(request, 'Rol oluşturuldu.')
            return redirect('stokapp:yetkilendirme_roller')
    return render(
        request,
        'stokapp/yetkilendirme/rol_form.html',
        {'baslik': 'Yeni rol', 'rol': None, 'gruplar': gruplar, 'secili_ids': set()},
    )


@login_required
def yetkilendirme_rol_duzenle(request, pk):
    g = _yetki_gate(request)
    if g:
        return g
    rol = get_object_or_404(Rol, pk=pk)
    if rol.slug == 'admin':
        messages.warning(request, 'Admin rolünün yetkileri salt okunur (tüm yetkiler).')
    yetkiler = list(SistemYetkisi.objects.order_by('modul', 'kod'))
    gruplar = {}
    for y in yetkiler:
        gruplar.setdefault(y.modul, []).append(y)
    secili_ids = set(RolYetkisi.objects.filter(rol=rol).values_list('yetki_id', flat=True))
    if request.method == 'POST':
        if rol.slug == 'admin':
            messages.error(request, 'Admin rolü düzenlenemez.')
            return redirect('stokapp:yetkilendirme_roller')
        rol.ad = (request.POST.get('ad') or rol.ad).strip()
        rol.aciklama = (request.POST.get('aciklama') or '').strip()
        rol.save(update_fields=['ad', 'aciklama'])
        with transaction.atomic():
            RolYetkisi.objects.filter(rol=rol).delete()
            for kid in request.POST.getlist('yetki'):
                try:
                    y = SistemYetkisi.objects.get(pk=int(kid))
                    RolYetkisi.objects.create(rol=rol, yetki=y)
                except (ValueError, SistemYetkisi.DoesNotExist):
                    pass
        _clear_rol_cache(rol.pk)
        messages.success(request, 'Rol güncellendi.')
        return redirect('stokapp:yetkilendirme_roller')
    return render(
        request,
        'stokapp/yetkilendirme/rol_form.html',
        {'baslik': 'Rol düzenle', 'rol': rol, 'gruplar': gruplar, 'secili_ids': secili_ids},
    )


def _clear_rol_cache(rol_id):
    for uid in KullaniciRolu.objects.filter(rol_id=rol_id).values_list('user_id', flat=True):
        clear_user_permission_cache(uid)


@login_required
def yetkilendirme_rol_sil(request, pk):
    g = _yetki_gate(request)
    if g:
        return g
    rol = get_object_or_404(Rol, pk=pk)
    if request.method != 'POST':
        return redirect('stokapp:yetkilendirme_roller')
    if rol.slug == 'admin':
        messages.error(request, 'Admin rolü silinemez.')
        return redirect('stokapp:yetkilendirme_roller')
    uids = list(KullaniciRolu.objects.filter(rol=rol).values_list('user_id', flat=True))
    rol.delete()
    for uid in uids:
        clear_user_permission_cache(uid)
    messages.success(request, 'Rol silindi.')
    return redirect('stokapp:yetkilendirme_roller')


@login_required
def yetkilendirme_kullanicilar(request):
    g = _yetki_gate(request)
    if g:
        return g
    kullanicilar = (
        User.objects.filter(is_active=True)
        .order_by('username')
        .prefetch_related(
            Prefetch(
                'tekos_rolleri',
                queryset=KullaniciRolu.objects.select_related('rol'),
            )
        )
    )
    roller = Rol.objects.order_by('ad')
    return render(
        request,
        'stokapp/yetkilendirme/kullanicilar.html',
        {'kullanicilar': kullanicilar, 'roller': roller},
    )


@login_required
def yetkilendirme_kullanici_roller(request, pk):
    g = _yetki_gate(request)
    if g:
        return g
    user = get_object_or_404(User, pk=pk)
    roller = Rol.objects.order_by('ad')
    if request.method == 'POST':
        ids = [int(x) for x in request.POST.getlist('rol') if str(x).isdigit()]
        with transaction.atomic():
            KullaniciRolu.objects.filter(user=user).delete()
            for rid in ids:
                try:
                    r = Rol.objects.get(pk=rid)
                    KullaniciRolu.objects.create(user=user, rol=r)
                except Rol.DoesNotExist:
                    pass
        clear_user_permission_cache(user.pk)
        messages.success(request, 'Roller güncellendi.')
        return redirect('stokapp:yetkilendirme_kullanicilar')
    atanmis = set(KullaniciRolu.objects.filter(user=user).values_list('rol_id', flat=True))
    return render(
        request,
        'stokapp/yetkilendirme/kullanici_roller.html',
        {'hedef_user': user, 'roller': roller, 'atanmis': atanmis},
    )


@login_required
def yetkilendirme_yetkiler(request):
    g = _yetki_gate(request)
    if g:
        return g
    yetkiler = list(SistemYetkisi.objects.order_by('modul', 'kod'))
    gruplar = {}
    for y in yetkiler:
        lbl = RBAC_MODULE_ACTIONS.get(y.modul, {}).get('label', y.modul)
        gruplar.setdefault(y.modul, {'label': lbl, 'rows': []})['rows'].append(y)
    return render(request, 'stokapp/yetkilendirme/yetkiler.html', {'gruplar': gruplar})
