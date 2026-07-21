from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.files.storage import default_storage
from django.conf import settings
from django.db.models import Max
import os
from decimal import Decimal
from .models import Recete, ReceteTalimat, ReceteTalimatOlcu, ReceteTalimatDosya, ReceteTalimatEkipman, ReceteTalimatProgram, ReceteTalimatFikstur, ReceteTalimatOlcuAleti, ReceteTalimatAciklama, ReceteTalimatKurulumDosyasi, Ekipman, Fikstur, OlcuAleti, KurulumDosyasi


@login_required
@require_http_methods(["GET"])
def recete_talimat_listesi(request, pk):
    """AJAX: Reçete talimatları listesi"""
    recete = get_object_or_404(Recete, pk=pk)
    talimatlar = recete.talimatlar.prefetch_related('olculer', 'dosyalar', 'ekipmanlar', 'programlar', 'olcu_aletleri', 'ek_aciklamalar', 'kurulum_dosyalari__kurulum_dosyasi__urun', 'kurulum_dosyalari__kurulum_dosyasi__istasyon').all()
    
    results = []
    for talimat in talimatlar:
        olculer = []
        for olcu in talimat.olculer.all():
            olculer.append({
                'id': olcu.pk,
                'aciklama': olcu.aciklama,
                'nominal_deger': str(olcu.nominal_deger) if olcu.nominal_deger else '',
                'birim': olcu.birim,
                'min_deger': str(olcu.min_deger) if olcu.min_deger else '',
                'max_deger': str(olcu.max_deger) if olcu.max_deger else '',
                'sira': olcu.sira,
            })
        
        dosyalar = []
        for dosya in talimat.dosyalar.all():
            dosyalar.append({
                'id': dosya.pk,
                'aciklama': dosya.aciklama,
                'dosya_url': dosya.dosya.url if dosya.dosya else '',
                'dosya_adi': dosya.dosya_adi or os.path.basename(dosya.dosya.name) if dosya.dosya else '',
                'dosya_tipi': dosya.dosya_tipi,
            })
        
        ekipmanlar = []
        for talimat_ekipman in talimat.ekipmanlar.all():
            ekipmanlar.append({
                'id': talimat_ekipman.pk,
                'ekipman_id': talimat_ekipman.ekipman.pk,
                'ekipman_numarasi': talimat_ekipman.ekipman.ekipman_numarasi,
                'ad': talimat_ekipman.ekipman.ad,
                'aciklama': talimat_ekipman.ekipman.aciklama,
                'sira': talimat_ekipman.sira,
            })
        
        fiksturler = []
        for talimat_fikstur in talimat.fiksturler.all():
            fiksturler.append({
                'id': talimat_fikstur.pk,
                'fikstur_id': talimat_fikstur.fikstur.pk,
                'fikstur_numarasi': talimat_fikstur.fikstur.fikstur_numarasi,
                'ad': talimat_fikstur.fikstur.ad,
                'aciklama': talimat_fikstur.fikstur.aciklama,
                'sira': talimat_fikstur.sira,
            })
        
        programlar = []
        for program in talimat.programlar.all():
            programlar.append({
                'id': program.pk,
                'program_adi': program.program_adi,
                'aciklama': program.aciklama,
                'sira': program.sira,
            })
        
        olcu_aletleri = []
        for talimat_olcu_aleti in talimat.olcu_aletleri.all():
            olcu_aletleri.append({
                'id': talimat_olcu_aleti.pk,
                'olcu_aleti_id': talimat_olcu_aleti.olcu_aleti.pk if talimat_olcu_aleti.olcu_aleti else None,
                'seri_no': talimat_olcu_aleti.olcu_aleti.seri_no if talimat_olcu_aleti.olcu_aleti else '',
                'marka': talimat_olcu_aleti.olcu_aleti.marka if talimat_olcu_aleti.olcu_aleti else '',
                'model': talimat_olcu_aleti.olcu_aleti.model if talimat_olcu_aleti.olcu_aleti else '',
                'sira': talimat_olcu_aleti.sira,
            })
        
        ek_aciklamalar = []
        for ek_aciklama in talimat.ek_aciklamalar.all():
            ek_aciklamalar.append({
                'id': ek_aciklama.pk,
                'aciklama': ek_aciklama.aciklama,
                'sira': ek_aciklama.sira,
            })
        
        kurulum_dosyalari = []
        for talimat_kurulum in talimat.kurulum_dosyalari.all():
            pdf_url = ''
            if talimat_kurulum.kurulum_dosyasi.pdf_dosya:
                try:
                    pdf_url = talimat_kurulum.kurulum_dosyasi.pdf_dosya.url
                except:
                    pdf_url = ''
            
            kurulum_dosyalari.append({
                'id': talimat_kurulum.pk,
                'kurulum_dosyasi_id': talimat_kurulum.kurulum_dosyasi.pk,
                'urun_kodu': talimat_kurulum.kurulum_dosyasi.urun.stok_kodu,
                'urun_parcasi': talimat_kurulum.kurulum_dosyasi.urun_parcasi,
                'istasyon_adi': talimat_kurulum.kurulum_dosyasi.istasyon.ad if talimat_kurulum.kurulum_dosyasi.istasyon else '',
                'versiyon': talimat_kurulum.kurulum_dosyasi.versiyon,
                'aciklama': talimat_kurulum.kurulum_dosyasi.aciklama,
                'pdf_url': pdf_url,
                'sira': talimat_kurulum.sira,
            })
        
        results.append({
            'id': talimat.pk,
            'sira': talimat.sira,
            'aciklama': talimat.aciklama,
            'olculer': olculer,
            'dosyalar': dosyalar,
            'ekipmanlar': ekipmanlar,
            'fiksturler': fiksturler,
            'olcu_aletleri': olcu_aletleri,
            'programlar': programlar,
            'ek_aciklamalar': ek_aciklamalar,
            'kurulum_dosyalari': kurulum_dosyalari,
        })
    
    return JsonResponse({'success': True, 'talimatlar': results})


@login_required
@require_http_methods(["POST"])
def recete_talimat_ekle(request, pk):
    """AJAX: Yeni talimat ekle"""
    recete = get_object_or_404(Recete, pk=pk)
    
    try:
        aciklama = request.POST.get('aciklama', '')
        if not aciklama:
            return JsonResponse({'success': False, 'error': 'Açıklama boş olamaz.'}, status=400)
        
        # Sıra numarasını belirle
        max_sira = recete.talimatlar.aggregate(max_sira=Max('sira'))['max_sira'] or 0
        sira = max_sira + 1
        
        talimat = ReceteTalimat.objects.create(
            recete=recete,
            sira=sira,
            aciklama=aciklama
        )
        
        return JsonResponse({
            'success': True,
            'talimat': {
                'id': talimat.pk,
                'sira': talimat.sira,
                'aciklama': talimat.aciklama,
                'olculer': [],
                'dosyalar': [],
                'ekipmanlar': [],
                'programlar': [],
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_talimat_duzenle(request, pk, talimat_id):
    """AJAX: Talimat düzenle"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    
    try:
        aciklama = request.POST.get('aciklama', '')
        sira = request.POST.get('sira', talimat.sira)
        
        if not aciklama:
            return JsonResponse({'success': False, 'error': 'Açıklama boş olamaz.'}, status=400)
        
        talimat.aciklama = aciklama
        talimat.sira = int(sira)
        talimat.save()
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_talimat_sil(request, pk, talimat_id):
    """AJAX: Talimat sil"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    
    try:
        talimat.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_talimat_olcu_ekle(request, pk, talimat_id):
    """AJAX: Talimat ölçü ekle"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    
    try:
        aciklama = request.POST.get('aciklama', '')
        nominal_deger = request.POST.get('nominal_deger', '')
        birim = request.POST.get('birim', '')
        min_deger = request.POST.get('min_deger', '')
        max_deger = request.POST.get('max_deger', '')
        
        # Sıra numarasını belirle
        max_sira = talimat.olculer.aggregate(max_sira=Max('sira'))['max_sira'] or 0
        sira = max_sira + 1
        
        olcu = ReceteTalimatOlcu.objects.create(
            talimat=talimat,
            aciklama=aciklama,
            nominal_deger=Decimal(nominal_deger) if nominal_deger else None,
            birim=birim,
            min_deger=Decimal(min_deger) if min_deger else None,
            max_deger=Decimal(max_deger) if max_deger else None,
            sira=sira
        )
        
        return JsonResponse({
            'success': True,
            'olcu': {
                'id': olcu.pk,
                'aciklama': olcu.aciklama,
                'nominal_deger': str(olcu.nominal_deger) if olcu.nominal_deger else '',
                'birim': olcu.birim,
                'min_deger': str(olcu.min_deger) if olcu.min_deger else '',
                'max_deger': str(olcu.max_deger) if olcu.max_deger else '',
                'sira': olcu.sira,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_talimat_olcu_duzenle(request, pk, talimat_id, olcu_id):
    """AJAX: Talimat ölçü düzenle"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    olcu = get_object_or_404(ReceteTalimatOlcu, pk=olcu_id, talimat=talimat)
    
    try:
        aciklama = request.POST.get('aciklama', '')
        nominal_deger = request.POST.get('nominal_deger', '')
        birim = request.POST.get('birim', '')
        min_deger = request.POST.get('min_deger', '')
        max_deger = request.POST.get('max_deger', '')
        
        olcu.aciklama = aciklama
        olcu.nominal_deger = Decimal(nominal_deger) if nominal_deger else None
        olcu.birim = birim
        olcu.min_deger = Decimal(min_deger) if min_deger else None
        olcu.max_deger = Decimal(max_deger) if max_deger else None
        olcu.save()
        
        return JsonResponse({
            'success': True,
            'olcu': {
                'id': olcu.pk,
                'aciklama': olcu.aciklama,
                'nominal_deger': str(olcu.nominal_deger) if olcu.nominal_deger else '',
                'birim': olcu.birim,
                'min_deger': str(olcu.min_deger) if olcu.min_deger else '',
                'max_deger': str(olcu.max_deger) if olcu.max_deger else '',
                'sira': olcu.sira,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_talimat_olcu_sil(request, pk, talimat_id, olcu_id):
    """AJAX: Talimat ölçü sil"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    olcu = get_object_or_404(ReceteTalimatOlcu, pk=olcu_id, talimat=talimat)
    
    try:
        olcu.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_talimat_dosya_ekle(request, pk, talimat_id):
    """AJAX: Talimat dosya ekle"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    
    try:
        if 'dosya' not in request.FILES:
            return JsonResponse({'success': False, 'error': 'Dosya seçilmedi.'}, status=400)
        
        dosya = request.FILES['dosya']
        aciklama = request.POST.get('aciklama', '')
        dosya_adi = request.POST.get('dosya_adi', '')
        dosya_tipi = request.POST.get('dosya_tipi', '')
        
        # Dosya tipini belirle
        if not dosya_tipi:
            dosya_adi_lower = dosya.name.lower()
            if dosya_adi_lower.endswith('.pdf'):
                dosya_tipi = 'pdf'
            elif dosya_adi_lower.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp')):
                dosya_tipi = 'foto'
            else:
                dosya_tipi = 'dosya'
        
        dosya_obj = ReceteTalimatDosya.objects.create(
            talimat=talimat,
            aciklama=aciklama,
            dosya=dosya,
            dosya_adi=dosya_adi or dosya.name,
            dosya_tipi=dosya_tipi
        )
        
        return JsonResponse({
            'success': True,
            'dosya': {
                'id': dosya_obj.pk,
                'aciklama': dosya_obj.aciklama,
                'dosya_url': dosya_obj.dosya.url,
                'dosya_adi': dosya_obj.dosya_adi,
                'dosya_tipi': dosya_obj.dosya_tipi,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_talimat_dosya_sil(request, pk, talimat_id, dosya_id):
    """AJAX: Talimat dosya sil"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    dosya = get_object_or_404(ReceteTalimatDosya, pk=dosya_id, talimat=talimat)
    
    try:
        # Dosyayı sil
        if dosya.dosya:
            dosya.dosya.delete(save=False)
        dosya.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_talimat_ekipman_ekle(request, pk, talimat_id):
    """AJAX: Talimat ekipman ekle"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    
    try:
        ekipman_id = request.POST.get('ekipman_id', '')
        
        if not ekipman_id:
            return JsonResponse({'success': False, 'error': 'Ekipman seçilmedi.'}, status=400)
        
        ekipman = get_object_or_404(Ekipman, pk=ekipman_id, aktif=True)
        
        # Sıra numarasını belirle
        max_sira = talimat.ekipmanlar.aggregate(max_sira=Max('sira'))['max_sira'] or 0
        sira = max_sira + 1
        
        talimat_ekipman = ReceteTalimatEkipman.objects.create(
            talimat=talimat,
            ekipman=ekipman,
            sira=sira
        )
        
        return JsonResponse({
            'success': True,
            'ekipman': {
                'id': talimat_ekipman.pk,
                'ekipman_id': talimat_ekipman.ekipman.pk,
                'ekipman_numarasi': talimat_ekipman.ekipman.ekipman_numarasi,
                'ad': talimat_ekipman.ekipman.ad,
                'aciklama': talimat_ekipman.ekipman.aciklama,
                'sira': talimat_ekipman.sira,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_talimat_ekipman_sil(request, pk, talimat_id, ekipman_id):
    """AJAX: Talimat ekipman sil"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    ekipman = get_object_or_404(ReceteTalimatEkipman, pk=ekipman_id, talimat=talimat)
    
    try:
        ekipman.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_talimat_program_ekle(request, pk, talimat_id):
    """AJAX: Talimat program ekle"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    
    try:
        program_adi = request.POST.get('program_adi', '')
        aciklama = request.POST.get('aciklama', '')
        
        if not program_adi:
            return JsonResponse({'success': False, 'error': 'Program adı boş olamaz.'}, status=400)
        
        # Sıra numarasını belirle
        max_sira = talimat.programlar.aggregate(max_sira=Max('sira'))['max_sira'] or 0
        sira = max_sira + 1
        
        program = ReceteTalimatProgram.objects.create(
            talimat=talimat,
            program_adi=program_adi,
            aciklama=aciklama,
            sira=sira
        )
        
        return JsonResponse({
            'success': True,
            'program': {
                'id': program.pk,
                'program_adi': program.program_adi,
                'aciklama': program.aciklama,
                'sira': program.sira,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_talimat_program_sil(request, pk, talimat_id, program_id):
    """AJAX: Talimat program sil"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    program = get_object_or_404(ReceteTalimatProgram, pk=program_id, talimat=talimat)
    
    try:
        program.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_talimat_fikstur_ekle(request, pk, talimat_id):
    """AJAX: Talimat fikstür ekle"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    
    try:
        fikstur_id = request.POST.get('fikstur_id', '')
        
        if not fikstur_id:
            return JsonResponse({'success': False, 'error': 'Fikstür seçilmedi.'}, status=400)
        
        fikstur = get_object_or_404(Fikstur, pk=fikstur_id, aktif=True)
        
        # Sıra numarasını belirle
        max_sira = talimat.fiksturler.aggregate(max_sira=Max('sira'))['max_sira'] or 0
        sira = max_sira + 1
        
        talimat_fikstur = ReceteTalimatFikstur.objects.create(
            talimat=talimat,
            fikstur=fikstur,
            sira=sira
        )
        
        return JsonResponse({
            'success': True,
            'fikstur': {
                'id': talimat_fikstur.pk,
                'fikstur_id': talimat_fikstur.fikstur.pk,
                'fikstur_numarasi': talimat_fikstur.fikstur.fikstur_numarasi,
                'ad': talimat_fikstur.fikstur.ad,
                'aciklama': talimat_fikstur.fikstur.aciklama,
                'sira': talimat_fikstur.sira,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_talimat_fikstur_sil(request, pk, talimat_id, fikstur_id):
    """AJAX: Talimat fikstür sil"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    talimat_fikstur = get_object_or_404(ReceteTalimatFikstur, pk=fikstur_id, talimat=talimat)
    
    try:
        talimat_fikstur.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_talimat_olcu_aleti_ekle(request, pk, talimat_id):
    """AJAX: Talimat ölçü aleti ekle"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    
    try:
        olcu_aleti_id = request.POST.get('olcu_aleti_id', '')
        
        if not olcu_aleti_id:
            return JsonResponse({'success': False, 'error': 'Ölçü aleti seçilmedi.'}, status=400)
        
        olcu_aleti = get_object_or_404(OlcuAleti, pk=olcu_aleti_id, aktif=True)
        
        # Sıra numarasını belirle
        max_sira = talimat.olcu_aletleri.aggregate(max_sira=Max('sira'))['max_sira'] or 0
        sira = max_sira + 1
        
        talimat_olcu_aleti = ReceteTalimatOlcuAleti.objects.create(
            talimat=talimat,
            olcu_aleti=olcu_aleti,
            sira=sira
        )
        
        return JsonResponse({
            'success': True,
            'olcu_aleti': {
                'id': talimat_olcu_aleti.pk,
                'olcu_aleti_id': talimat_olcu_aleti.olcu_aleti.pk,
                'seri_no': talimat_olcu_aleti.olcu_aleti.seri_no,
                'marka': talimat_olcu_aleti.olcu_aleti.marka,
                'model': talimat_olcu_aleti.olcu_aleti.model,
                'sira': talimat_olcu_aleti.sira,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_talimat_olcu_aleti_sil(request, pk, talimat_id, olcu_aleti_id):
    """AJAX: Talimat ölçü aleti sil"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    talimat_olcu_aleti = get_object_or_404(ReceteTalimatOlcuAleti, pk=olcu_aleti_id, talimat=talimat)
    
    try:
        talimat_olcu_aleti.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def recete_talimat_aciklama_ekle(request, pk, talimat_id):
    """AJAX: Talimat ek açıklama ekle"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    
    try:
        aciklama = request.POST.get('aciklama', '').strip()
        
        if not aciklama:
            return JsonResponse({'success': False, 'error': 'Açıklama boş olamaz.'}, status=400)
        
        # Sıra numarasını belirle
        max_sira = talimat.ek_aciklamalar.aggregate(max_sira=Max('sira'))['max_sira'] or 0
        sira = max_sira + 1
        
        ek_aciklama = ReceteTalimatAciklama.objects.create(
            talimat=talimat,
            aciklama=aciklama,
            sira=sira
        )
        
        return JsonResponse({
            'success': True,
            'aciklama': {
                'id': ek_aciklama.pk,
                'aciklama': ek_aciklama.aciklama,
                'sira': ek_aciklama.sira,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def recete_talimat_aciklama_duzenle(request, pk, talimat_id, aciklama_id):
    """AJAX: Talimat ek açıklama düzenle"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    ek_aciklama = get_object_or_404(ReceteTalimatAciklama, pk=aciklama_id, talimat=talimat)
    
    try:
        aciklama = request.POST.get('aciklama', '').strip()
        
        if not aciklama:
            return JsonResponse({'success': False, 'error': 'Açıklama boş olamaz.'}, status=400)
        
        ek_aciklama.aciklama = aciklama
        ek_aciklama.save()
        
        return JsonResponse({
            'success': True,
            'aciklama': {
                'id': ek_aciklama.pk,
                'aciklama': ek_aciklama.aciklama,
                'sira': ek_aciklama.sira,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def recete_talimat_aciklama_sil(request, pk, talimat_id, aciklama_id):
    """AJAX: Talimat ek açıklama sil"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    ek_aciklama = get_object_or_404(ReceteTalimatAciklama, pk=aciklama_id, talimat=talimat)
    
    try:
        ek_aciklama.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def recete_talimat_kurulum_dosyalari_listesi(request, pk):
    """AJAX: Reçete ürününe ait kurulum dosyalarını getir"""
    recete = get_object_or_404(Recete, pk=pk)
    
    try:
        kurulum_dosyalari = KurulumDosyasi.objects.filter(urun=recete.urun, aktif=True).select_related('istasyon').order_by('urun_parcasi', '-versiyon')
        
        results = []
        for kurulum in kurulum_dosyalari:
            results.append({
                'id': kurulum.pk,
                'urun_kodu': kurulum.urun.stok_kodu,
                'urun_parcasi': kurulum.urun_parcasi,
                'istasyon_adi': kurulum.istasyon.ad if kurulum.istasyon else '',
                'versiyon': kurulum.versiyon,
                'aciklama': kurulum.aciklama,
            })
        
        return JsonResponse({'success': True, 'kurulum_dosyalari': results})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def recete_talimat_kurulum_dosyasi_ekle(request, pk, talimat_id):
    """AJAX: Talimat kurulum dosyası ekle"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    
    try:
        kurulum_dosyasi_id = request.POST.get('kurulum_dosyasi_id', '')
        
        if not kurulum_dosyasi_id:
            return JsonResponse({'success': False, 'error': 'Kurulum dosyası seçilmedi.'}, status=400)
        
        # Kurulum dosyasının reçetenin ürününe ait olduğunu kontrol et
        kurulum_dosyasi = get_object_or_404(KurulumDosyasi, pk=kurulum_dosyasi_id, aktif=True)
        if kurulum_dosyasi.urun != recete.urun:
            return JsonResponse({'success': False, 'error': 'Bu kurulum dosyası bu reçetenin ürününe ait değil.'}, status=400)
        
        # Zaten eklenmiş mi kontrol et
        if ReceteTalimatKurulumDosyasi.objects.filter(talimat=talimat, kurulum_dosyasi=kurulum_dosyasi).exists():
            return JsonResponse({'success': False, 'error': 'Bu kurulum dosyası zaten eklenmiş.'}, status=400)
        
        # Sıra numarasını belirle
        max_sira = talimat.kurulum_dosyalari.aggregate(max_sira=Max('sira'))['max_sira'] or 0
        sira = max_sira + 1
        
        talimat_kurulum = ReceteTalimatKurulumDosyasi.objects.create(
            talimat=talimat,
            kurulum_dosyasi=kurulum_dosyasi,
            sira=sira
        )
        
        pdf_url = ''
        if talimat_kurulum.kurulum_dosyasi.pdf_dosya:
            try:
                pdf_url = talimat_kurulum.kurulum_dosyasi.pdf_dosya.url
            except:
                pdf_url = ''
        
        return JsonResponse({
            'success': True,
            'kurulum_dosyasi': {
                'id': talimat_kurulum.pk,
                'kurulum_dosyasi_id': talimat_kurulum.kurulum_dosyasi.pk,
                'urun_kodu': talimat_kurulum.kurulum_dosyasi.urun.stok_kodu,
                'urun_parcasi': talimat_kurulum.kurulum_dosyasi.urun_parcasi,
                'istasyon_adi': talimat_kurulum.kurulum_dosyasi.istasyon.ad if talimat_kurulum.kurulum_dosyasi.istasyon else '',
                'versiyon': talimat_kurulum.kurulum_dosyasi.versiyon,
                'aciklama': talimat_kurulum.kurulum_dosyasi.aciklama,
                'pdf_url': pdf_url,
                'sira': talimat_kurulum.sira,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def recete_talimat_kurulum_dosyasi_sil(request, pk, talimat_id, kurulum_dosyasi_id):
    """AJAX: Talimat kurulum dosyası sil"""
    recete = get_object_or_404(Recete, pk=pk)
    talimat = get_object_or_404(ReceteTalimat, pk=talimat_id, recete=recete)
    talimat_kurulum = get_object_or_404(ReceteTalimatKurulumDosyasi, pk=kurulum_dosyasi_id, talimat=talimat)
    
    try:
        talimat_kurulum.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

