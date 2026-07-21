from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from .models import StokItem, StokHareketi, Depo, Raf
from django import forms


class StokTransferForm(forms.Form):
    """Stok transfer formu"""
    stok_item = forms.ModelChoiceField(
        queryset=StokItem.objects.filter(arsivli=False),
        label="Stok",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    kaynak_depo = forms.ModelChoiceField(
        queryset=Depo.objects.all(),
        label="Kaynak Depo",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    kaynak_raf = forms.ModelChoiceField(
        queryset=Raf.objects.none(),
        label="Kaynak Raf",
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    hedef_depo = forms.ModelChoiceField(
        queryset=Depo.objects.all(),
        label="Hedef Depo",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    hedef_raf = forms.ModelChoiceField(
        queryset=Raf.objects.none(),
        label="Hedef Raf",
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    miktar = forms.DecimalField(
        max_digits=10,
        decimal_places=3,
        min_value=0.001,
        label="Transfer Miktarı",
        widget=forms.NumberInput(attrs={'step': '0.001', 'min': '0.001', 'class': 'form-control'})
    )
    birim = forms.CharField(
        max_length=20,
        initial='Adet',
        widget=forms.TextInput(attrs={'class': 'form-control', 'readonly': True})
    )
    referans_no = forms.CharField(
        max_length=100,
        required=False,
        label="Referans No (Opsiyonel)",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    aciklama = forms.CharField(
        required=False,
        label="Açıklama",
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Kaynak ve hedef depo seçildiğinde rafları dinamik yüklemek için
        # JavaScript ile yapılacak, burada sadece form alanlarını hazırlıyoruz
        if 'kaynak_depo' in self.data:
            try:
                depo_id = int(self.data.get('kaynak_depo'))
                self.fields['kaynak_raf'].queryset = Raf.objects.filter(depo_id=depo_id).order_by('ad')
            except (ValueError, TypeError):
                pass
        
        if 'hedef_depo' in self.data:
            try:
                depo_id = int(self.data.get('hedef_depo'))
                self.fields['hedef_raf'].queryset = Raf.objects.filter(depo_id=depo_id).order_by('ad')
            except (ValueError, TypeError):
                pass

    def clean(self):
        cleaned_data = super().clean()
        kaynak_depo = cleaned_data.get('kaynak_depo')
        hedef_depo = cleaned_data.get('hedef_depo')
        stok_item = cleaned_data.get('stok_item')
        miktar = cleaned_data.get('miktar')

        # Kaynak ve hedef depo aynı olamaz
        if kaynak_depo and hedef_depo and kaynak_depo == hedef_depo:
            raise forms.ValidationError("Kaynak ve hedef depo aynı olamaz!")

        # Stok kontrolü
        if stok_item and miktar:
            # Eğer stok item'ın depo bilgisi varsa kontrol et
            if stok_item.depo and stok_item.depo != kaynak_depo:
                raise forms.ValidationError(
                    f"Bu ürün {stok_item.depo.ad} deposunda. Kaynak depo olarak {kaynak_depo.ad} seçilemez."
                )
            
            # Mevcut stok kontrolü
            if stok_item.mevcut_miktar < miktar:
                raise forms.ValidationError(
                    f"Yetersiz stok! Mevcut: {stok_item.mevcut_miktar} {stok_item.birim}, "
                    f"Transfer edilmek istenen: {miktar} {stok_item.birim}"
                )

        return cleaned_data


@login_required
def stok_transfer(request):
    """Stok transfer işlemi"""
    if request.method == 'POST':
        form = StokTransferForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    stok_item = form.cleaned_data['stok_item']
                    kaynak_depo = form.cleaned_data['kaynak_depo']
                    kaynak_raf = form.cleaned_data.get('kaynak_raf')
                    hedef_depo = form.cleaned_data['hedef_depo']
                    hedef_raf = form.cleaned_data.get('hedef_raf')
                    miktar = form.cleaned_data['miktar']
                    birim = form.cleaned_data['birim'] or stok_item.birim
                    referans_no = form.cleaned_data.get('referans_no', '')
                    aciklama = form.cleaned_data.get('aciklama', '')

                    # Kaynak depodan çıkış
                    cikis_hareket = StokHareketi.objects.create(
                        stok_item=stok_item,
                        hareket_tipi='CIKIS',
                        miktar=miktar,
                        birim=birim,
                        referans_no=referans_no or f'TRANSFER-{kaynak_depo.ad}-{hedef_depo.ad}',
                        aciklama=f'Transfer: {kaynak_depo.ad} → {hedef_depo.ad}. {aciklama}',
                        user=request.user.username
                    )

                    # Hedef depoya giriş
                    giris_hareket = StokHareketi.objects.create(
                        stok_item=stok_item,
                        hareket_tipi='GIRIS',
                        miktar=miktar,
                        birim=birim,
                        referans_no=referans_no or f'TRANSFER-{kaynak_depo.ad}-{hedef_depo.ad}',
                        aciklama=f'Transfer: {kaynak_depo.ad} → {hedef_depo.ad}. {aciklama}',
                        user=request.user.username
                    )

                    # Stok item'ın depo/raf bilgisini güncelle (hedef depoya)
                    stok_item.depo = hedef_depo
                    stok_item.raf = hedef_raf
                    stok_item.save()

                    messages.success(
                        request,
                        f'{miktar} {birim} {stok_item.stok_kodu} başarıyla '
                        f'{kaynak_depo.ad} deposundan {hedef_depo.ad} deposuna transfer edildi.'
                    )
                    return redirect('stokapp:stok_transfer')
            except Exception as e:
                messages.error(request, f'Transfer hatası: {str(e)}')
    else:
        form = StokTransferForm()

    return render(request, 'stokapp/stok_transfer.html', {'form': form})


@login_required
def stok_transfer_listesi(request):
    """Transfer işlemleri listesi"""
    # Transfer işlemlerini bulmak için referans numarasında TRANSFER geçen hareketleri filtrele
    transferler = StokHareketi.objects.filter(
        referans_no__icontains='TRANSFER'
    ).order_by('-tarih')[:100]

    # Transfer çiftlerini grupla (çıkış ve giriş)
    transfer_gruplari = {}
    for hareket in transferler:
        ref_no = hareket.referans_no
        if ref_no not in transfer_gruplari:
            transfer_gruplari[ref_no] = {'cikis': None, 'giris': None}
        
        if hareket.hareket_tipi == 'CIKIS':
            transfer_gruplari[ref_no]['cikis'] = hareket
        elif hareket.hareket_tipi == 'GIRIS':
            transfer_gruplari[ref_no]['giris'] = hareket

    context = {
        'transfer_gruplari': transfer_gruplari,
    }
    return render(request, 'stokapp/stok_transfer_listesi.html', context)