from django import forms
from django.core.exceptions import ValidationError

from .models import ArGeDosya, ArGeProje, ArGeRevizyon, StokItem


class ArGeProjeForm(forms.ModelForm):
    class Meta:
        model = ArGeProje
        fields = [
            'proje_kodu',
            'proje_adi',
            'stok_item',
            'sorumlu',
            'durum',
            'baslangic_tarihi',
            'hedef_tarih',
            'oncelik',
            'hedef_maliyet',
            'hedef_satis_fiyati',
            'aciklama',
            'teknik_resim_hazir',
            'cad_hazir',
            'malzeme_tanimli',
            'operasyon_tanimli',
            'maliyet_hesaplandi',
            'kontrol_plani_hazir',
            'paketleme_hazir',
            'stok_kodu_var',
            'satis_fiyati_belirlendi',
        ]
        widgets = {
            'aciklama': forms.Textarea(attrs={'rows': 4}),
            'baslangic_tarihi': forms.DateInput(attrs={'type': 'date'}),
            'hedef_tarih': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['stok_item'].queryset = StokItem.objects.select_related('kategori').order_by(
            'stok_kodu'
        )
        self.fields['proje_kodu'].required = False
        if self.instance.pk:
            self.fields['proje_kodu'].disabled = True

    def clean_proje_kodu(self):
        kod = (self.cleaned_data.get('proje_kodu') or '').strip()
        if not self.instance.pk and not kod:
            return ArGeProje.uret_sonraki_proje_kodu()
        return kod or self.instance.proje_kodu

    def clean(self):
        data = super().clean()
        if data.get('durum') == 'SERI_URETIME_HAZIR':
            for name in [
                'teknik_resim_hazir',
                'cad_hazir',
                'malzeme_tanimli',
                'operasyon_tanimli',
                'maliyet_hesaplandi',
                'kontrol_plani_hazir',
                'paketleme_hazir',
                'stok_kodu_var',
                'satis_fiyati_belirlendi',
            ]:
                if not data.get(name):
                    raise ValidationError(
                        'Seri üretime hazır durumu için tüm kontrol maddeleri işaretlenmelidir.'
                    )
        return data


class ArGeRevizyonForm(forms.ModelForm):
    class Meta:
        model = ArGeRevizyon
        fields = [
            'revizyon_no',
            'tarih',
            'revizyon_nedeni',
            'degisiklik_tipi',
            'onceki_durum',
            'yeni_durum',
            'karar',
            'aciklama',
            'dosya',
            'gorsel',
        ]
        widgets = {
            'tarih': forms.DateInput(attrs={'type': 'date'}),
            'aciklama': forms.Textarea(attrs={'rows': 3}),
        }


class ArGeDosyaForm(forms.ModelForm):
    class Meta:
        model = ArGeDosya
        fields = ['dosya', 'dosya_tipi', 'aciklama']
