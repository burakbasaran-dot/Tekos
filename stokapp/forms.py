import re
from datetime import date, timedelta
from decimal import Decimal
from django import forms
from django.utils.dateparse import parse_date
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q, Sum
from .models import (
    OlcuAletiTuru, OlcuAleti, KalibrasyonKaydi,
    SiparisMaliyeti,
    StokHareketi,
    StokItem,
    Kategori, Tedarikci, Birim, Depo, Raf, Cari, GenelAyarlar, ParaBirimi, Operasyon, Istasyon, Sigorta,
    Personel, GunlukCalisma, AvansOdeme, PersonelIzin, PersonelBelgesi, Siparis, SiparisKalemi, SiparisMaliyeti, Musteri, Satinalma, SatinalmaKalemi, Talep, TalepKalemi, TalepDosya, TalepGecmisi, TalepSatinalmaBilgisi,
    UretimStandarti, UretimStandartiArsiv, Arac, AracBelgesi, AracBelgeTuru, Gayrimenkul, GayrimenkulIslemi, GayrimenkulDosya, BankaHesabi, KrediKarti, AylikOdeme,
    Ekipman, Fikstur, DisOperasyonTipi,
    Complaint, ComplaintAttachment, CapaAction, EcoChange, AlertRule, ControlPlan, ControlItem,
    WorkOrderInspection, QualityGate, NonconformanceAutoRule, ReceteOperasyon,
    KurulumDosyasi, KurulumDosyasiArsiv,
    CncProgram, CncProgramRevision, CncEkipman,
    DocumentType, Document, DocumentFile, DocumentRenewal, DocumentLink, DocumentReminder,
    GelistirmeTalebi, UretimDegisiklikKaydi
)

class StokHareketForm(forms.ModelForm):
    """Tek form ile GİRİŞ/ÇIKIŞ. view '__init__(hareket_tipi=...)' ile bilgi verir."""
    class Meta:
        model = StokHareketi
        fields = ["stok_item", "miktar", "birim", "referans_no", "depo", "raf"]
        widgets = {
            "miktar": forms.NumberInput(attrs={"step": "0.001", "min": "0"}),
            "depo": forms.Select(attrs={'class': 'form-select'}),
            "raf": forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.hareket_tipi = kwargs.pop("hareket_tipi", None)  # 'GIRIS' veya 'CIKIS'
        self.is_edit = kwargs.pop("is_edit", False)  # Düzenleme modu mu?
        super().__init__(*args, **kwargs)
        
        # Düzenleme modunda hareket_tipi alanını ekle ve stok_item'ı readonly yap
        if self.is_edit and self.instance and self.instance.pk:
            self.fields['hareket_tipi'] = forms.ChoiceField(
                choices=StokHareketi.HAREKET_TIPLERI,
                label="Hareket Tipi",
                required=True,
                widget=forms.Select(attrs={'class': 'form-select'}),
                initial=self.instance.hareket_tipi
            )
            # Stok item değiştirilemez
            if 'stok_item' in self.fields:
                self.fields['stok_item'].widget.attrs['readonly'] = True
                self.fields['stok_item'].widget.attrs['disabled'] = True
        
        # Depo ve raf queryset'lerini ayarla
        if 'depo' in self.fields:
            self.fields['depo'].queryset = Depo.objects.all()
            self.fields['depo'].widget.attrs.update({'class': 'form-select'})
        
        if 'raf' in self.fields:
            self.fields['raf'].queryset = Raf.objects.none()  # Başlangıçta boş
            self.fields['raf'].widget.attrs.update({'class': 'form-select'})
            # Depo seçilince rafları yüklemek için JavaScript kullanılacak

    def clean_miktar(self):
        val = self.cleaned_data.get("miktar")
        if val is None or Decimal(val) <= 0:
            raise ValidationError("Miktar 0'dan büyük olmalı.")
        return val


def _existing_field_names(model):
    return {f.name for f in model._meta.get_fields()}

class StokItemForm(forms.ModelForm):
    """Stok ekleme/düzenleme formu: Görsel, depo/raf, fiyatlar vs."""
    # Stok tipi seçimi ekle
    stok_tipi = forms.ChoiceField(
        choices=StokItem.STOK_TIPLERI,
        label="Stok Tipi",
        required=False,  # Artık zorunlu değil, kategori'den alınabilir
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_stok_tipi'})
    )
    
    _CANDIDATE_FIELDS = [
        # Kimlik
        'stok_kodu', 'ad', 'barkod', 'aciklama',
        # İlişkiler
        'kategori', 'tedarikci', 'birim', 'urun_agirligi', 'urun_agirlik_birimi', 'depo', 'raf',
        # Görseller
        'fotograf',
        'teknik_resim',
        # Fiyatlar
        'alis_fiyati',
        'satis_fiyati',
        'uretim_maliyeti',
        'satis_para_birimi',  # Eklendi
        # Para birimi alanları
        'alis_para_birimi',
        # Miktar & takip
        'acilis_miktari', 'stok_takip',
        # Stok seviyeleri
        'minimum_stok', 'maximum_stok',
        # Ürün tipi
        'urun_tipi', 'urun_rolu',
        # Arşiv
        'arsivli',
    ]

    class Meta:
        model = StokItem
        fields = '__all__'  # Tüm alanları yükle, sonra __init__'te filtrele
        widgets = {
            'satin_alma_fiyati': forms.NumberInput(attrs={'step': '0.01'}),
            'satis_fiyati': forms.NumberInput(attrs={'step': '0.01'}),
            'acilis_miktari': forms.NumberInput(attrs={'step': '0.001'}),
            'alis_fiyati': forms.NumberInput(attrs={'step': '0.01'}),
            'fotograf': forms.FileInput(attrs={'accept': 'image/*'}),
            'teknik_resim': forms.FileInput(attrs={'accept': '.dxf,.dwg'}),
            'stok_takip': forms.Select(attrs={'class': 'form-select'}, choices=[(True, 'Yapılsın'), (False, 'Yapılmasın')]),
            # Select alanları için widget'ları açıkça belirt
            'kategori': forms.Select(attrs={'class': 'form-select'}),
            'tedarikci': forms.Select(attrs={'class': 'form-select'}),
            'birim': forms.Select(attrs={'class': 'form-select'}),
            'depo': forms.Select(attrs={'class': 'form-select'}),
            'raf': forms.Select(attrs={'class': 'form-select'}),
            'urun_agirligi': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.0001', 'min': '0', 'placeholder': '0'}),
            'urun_agirlik_birimi': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Modelde mevcut alanları süz
        existing = _existing_field_names(StokItem)
        allowed_fields = set(f for f in self._CANDIDATE_FIELDS if f in existing)
        
        # İstenmeyen alanları kaldır
        fields_to_remove = [f for f in self.fields.keys() if f not in allowed_fields and f != 'stok_tipi']
        for field_name in fields_to_remove:
            del self.fields[field_name]
        
        # Mevcut kayıt için stok tipini al (önce kendi stok tipini, yoksa kategori'den)
        if self.instance and self.instance.pk:
            if self.instance.stok_tipi:
                self.fields['stok_tipi'].initial = self.instance.stok_tipi
            elif self.instance.kategori:
                self.fields['stok_tipi'].initial = self.instance.kategori.stok_tipi
        
        # Kategori queryset'ini ayarla (eğer kategori alanı varsa)
        if 'kategori' in self.fields:
            self.fields['kategori'].queryset = Kategori.objects.all()
            self.fields['kategori'].widget.attrs.update({'id': 'id_kategori', 'class': 'form-select'})
            self.fields['kategori'].required = True  # Kategori zorunlu
        
        # Diğer select alanlarına da class ekle ve queryset ayarla
        if 'tedarikci' in self.fields:
            self.fields['tedarikci'].queryset = Tedarikci.objects.all()
            self.fields['tedarikci'].widget.attrs.update({'class': 'form-select'})
            self.fields['tedarikci'].required = False  # Opsiyonel
        if 'urun_rolu' in self.fields:
            self.fields['urun_rolu'].widget.attrs.update({'class': 'form-select'})
        if 'birim' in self.fields:
            self.fields['birim'].queryset = Birim.objects.all()
            self.fields['birim'].widget.attrs.update({'class': 'form-select'})
            self.fields['birim'].required = False  # Opsiyonel
        if 'urun_agirlik_birimi' in self.fields:
            self.fields['urun_agirlik_birimi'].widget.attrs.update({'class': 'form-select'})
            self.fields['urun_agirlik_birimi'].required = False
        if 'urun_agirligi' in self.fields:
            self.fields['urun_agirligi'].widget.attrs.update({'class': 'form-input', 'step': '0.0001', 'min': '0', 'placeholder': '0'})
            self.fields['urun_agirligi'].required = False
        if self.instance and self.instance.pk and 'urun_tipi' in self.fields:
            self.fields['urun_tipi'].required = False
        if 'depo' in self.fields:
            # Tüm depoları göster (Depo Yönetimi'ndeki depolar)
            # Queryset'i list'e çevirerek evaluate et
            depo_queryset = Depo.objects.all().order_by('ad')
            self.fields['depo'].queryset = depo_queryset
            self.fields['depo'].widget.attrs.update({'class': 'form-select'})
            self.fields['depo'].required = False  # Opsiyonel
        if 'raf' in self.fields:
            depo_id = None
            if self.data and self.data.get('depo'):
                try:
                    depo_id = int(self.data.get('depo'))
                except (ValueError, TypeError):
                    pass
            if depo_id is None and self.instance and self.instance.pk and self.instance.depo_id:
                depo_id = self.instance.depo_id

            if depo_id:
                raf_qs = Raf.objects.filter(depo_id=depo_id)
                posted_raf = self.data.get('raf') if self.data else None
                if posted_raf:
                    try:
                        raf_qs = Raf.objects.filter(
                            Q(depo_id=depo_id) | Q(pk=int(posted_raf))
                        )
                    except (ValueError, TypeError):
                        pass
                self.fields['raf'].queryset = raf_qs.order_by('ad')
            else:
                self.fields['raf'].queryset = Raf.objects.none()

            self.fields['raf'].widget.attrs.update({'class': 'form-select'})
            self.fields['raf'].required = False  # Opsiyonel
        
        # Opsiyonel alanları işaretle
        optional_fields = ['satis_fiyati', 'acilis_miktari', 'alis_fiyati', 'uretim_maliyeti', 'barkod', 'aciklama', 'fotograf', 'teknik_resim', 'minimum_stok', 'maximum_stok', 'urun_agirligi', 'urun_agirlik_birimi']
        for field_name in optional_fields:
            if field_name in self.fields:
                self.fields[field_name].required = False

    def clean_stok_kodu(self):
        val = (self.cleaned_data.get('stok_kodu') or '').strip()
        if not val:
            raise ValidationError('Stok kodu boş olamaz.')
        qs = StokItem.objects.filter(stok_kodu__iexact=val)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('Bu stok kodu zaten kayıtlı.')
        return val

    def clean_uretim_maliyeti(self):
        val = self.cleaned_data.get('uretim_maliyeti')
        if val is None:
            if self.instance and self.instance.pk and self.instance.uretim_maliyeti is not None:
                return self.instance.uretim_maliyeti
            return Decimal('0')
        return val

    def clean(self):
        cleaned_data = super().clean()
        stok_tipi = cleaned_data.get('stok_tipi')
        kategori = cleaned_data.get('kategori')
        raf = cleaned_data.get('raf')
        depo = cleaned_data.get('depo')
        urun_rolu = cleaned_data.get('urun_rolu') or 'AL_SAT'
        alis_fiyati = cleaned_data.get('alis_fiyati') or Decimal('0')
        satis_fiyati = cleaned_data.get('satis_fiyati') or Decimal('0')
        uretim_maliyeti = cleaned_data.get('uretim_maliyeti') or Decimal('0')
        
        # Raf ve depo uyumluluğunu kontrol et
        if 'raf' in self.fields and raf:
            # Eğer raf seçildiyse, depo da seçilmeli ve raf o depo'ya ait olmalı
            if not depo:
                raise ValidationError({'raf': 'Raf seçmek için önce depo seçmelisiniz.'})
            if raf.depo != depo:
                raise ValidationError({'raf': 'Seçilen raf, seçilen depo\'ya ait değil.'})
        
        # Kategori alanı form'da varsa kontrol et
        if 'kategori' in self.fields:
            # Kategori zorunlu kontrolü - boş string veya None kontrolü
            if not kategori or (isinstance(kategori, str) and kategori.strip() == ''):
                raise ValidationError({'kategori': 'Kategori seçimi zorunludur.'})
            
            # Stok tipi artık kategori'den bağımsız
            # Eğer kullanıcı stok tipi seçmemişse, kategori'den varsayılan alınabilir ama zorunlu değil
            
            # Stok tipi artık kategori'den bağımsız, kategori stok tipini güncelleme
        else:
            # Kategori alanı form'da yoksa, sadece stok tipi kontrolü yap
            if stok_tipi and not kategori:
                # Bu durumda kullanıcı kategori seçmeli ama alan yok
                pass

        ham_post = getattr(self, '_ham_post_anahtarlari', None)

        def _kullanici_fiyat_gonderdi(alan):
            """Fiyat alanı kullanıcı tarafından mı gönderildi (merge değil)."""
            if ham_post is None:
                return True
            return alan in ham_post

        yeni_kayit = not (self.instance and self.instance.pk)

        # Ürün rolüne göre fiyat ve kaynak davranışları
        if urun_rolu == 'AL_SAT':
            cleaned_data['urun_tipi'] = 'SATINAL'
            if alis_fiyati <= 0 and (yeni_kayit or _kullanici_fiyat_gonderdi('alis_fiyati')):
                self.add_error('alis_fiyati', 'Al - sat ürün için alış fiyatı 0\'dan büyük olmalıdır.')
            if satis_fiyati <= 0 and (yeni_kayit or _kullanici_fiyat_gonderdi('satis_fiyati')):
                self.add_error('satis_fiyati', 'Al - sat ürün için satış fiyatı 0\'dan büyük olmalıdır.')
        elif urun_rolu == 'BILESEN':
            urun_tipi_bilesen = cleaned_data.get('urun_tipi') or 'SATINAL'
            if urun_tipi_bilesen not in ('SATINAL', 'URETIM'):
                urun_tipi_bilesen = 'SATINAL'
            cleaned_data['urun_tipi'] = urun_tipi_bilesen
            cleaned_data['satis_fiyati'] = Decimal('0')
            if urun_tipi_bilesen == 'SATINAL':
                if alis_fiyati <= 0 and (yeni_kayit or _kullanici_fiyat_gonderdi('alis_fiyati')):
                    self.add_error('alis_fiyati', 'Satın alınan üretim bileşeni için alış fiyatı 0\'dan büyük olmalıdır.')
            else:
                cleaned_data['tedarikci'] = None
                cleaned_data['alis_fiyati'] = Decimal('0')
                if uretim_maliyeti < 0:
                    self.add_error('uretim_maliyeti', 'Üretim maliyeti negatif olamaz.')
        elif urun_rolu == 'NIHAI_URUN':
            cleaned_data['urun_tipi'] = 'URETIM'
            if ham_post is not None and 'tedarikci' not in ham_post:
                if self.instance and self.instance.pk and self.instance.tedarikci_id:
                    cleaned_data['tedarikci'] = self.instance.tedarikci
            else:
                cleaned_data['tedarikci'] = None
            if ham_post is not None and 'alis_fiyati' not in ham_post:
                if self.instance and self.instance.pk:
                    cleaned_data['alis_fiyati'] = self.instance.alis_fiyati or Decimal('0')
                else:
                    cleaned_data['alis_fiyati'] = Decimal('0')
            else:
                cleaned_data['alis_fiyati'] = Decimal('0')
            if uretim_maliyeti < 0:
                self.add_error('uretim_maliyeti', 'Üretim maliyeti negatif olamaz.')
            elif uretim_maliyeti == 0 and not yeni_kayit and not _kullanici_fiyat_gonderdi('uretim_maliyeti'):
                pass

        stok_takip = cleaned_data.get('stok_takip')
        if stok_takip is False:
            cleaned_data['minimum_stok'] = Decimal('0')
            cleaned_data['maximum_stok'] = Decimal('0')
        
        return cleaned_data

    def save(self, commit=True):
        # Birim değerini cleaned_data'dan al (super().save() çağrılmadan önce)
        birim_value = None
        if 'birim' in self.fields:
            birim_value = self.cleaned_data.get('birim')
            print(f"Save - birim_value: {birim_value}, type: {type(birim_value)}")  # Debug
        
        instance = super().save(commit=False)
        
        # Satış para birimi değerini cleaned_data'dan al ve kaydet
        if 'satis_para_birimi' in self.cleaned_data:
            satis_para_birimi_value = self.cleaned_data.get('satis_para_birimi')
            if satis_para_birimi_value:
                instance.satis_para_birimi = satis_para_birimi_value
        # NOT: Satış para birimi view'da direkt ORM ile güncelleniyor, burada default değer atamaya gerek yok
        
        # Kategori kontrolü - sadece form'da varsa
        if 'kategori' in self.fields:
            # Kategori None veya boş ise hata ver (kategori_id kontrolü yap)
            if not instance.kategori_id:
                print("Save - Kategori yok, hata fırlatılıyor")  # Debug
                raise ValidationError('Kategori seçimi zorunludur. Lütfen bir kategori seçin.')
            
            # Stok tipini instance'a kaydet (kategori'den bağımsız)
            if self.cleaned_data.get('stok_tipi'):
                instance.stok_tipi = self.cleaned_data['stok_tipi']
        else:
            # Kategori alanı form'da yoksa ama model'de zorunluysa hata ver
            if not instance.kategori_id:
                raise ValidationError('Kategori alanı zorunludur ancak form\'da bulunamadı.')
        
        # Zorunlu alanlar için default değerleri set et (None ise)
        if instance.minimum_stok is None:
            instance.minimum_stok = 0
        if instance.guvenlik_stoku is None:
            instance.guvenlik_stoku = 0
        if instance.mevcut_miktar is None:
            instance.mevcut_miktar = 0
        if instance.acilis_miktari is None:
            instance.acilis_miktari = 0
        if instance.uretim_maliyeti is None:
            instance.uretim_maliyeti = Decimal('0')
        if instance.alis_fiyati is None:
            instance.alis_fiyati = Decimal('0')
        if instance.satis_fiyati is None:
            instance.satis_fiyati = Decimal('0')
        
        # Birim alanını düzelt: Eğer birim bir Birim objesi ise, ad değerini al
        if birim_value:
            # Eğer birim bir Birim objesi ise (ModelChoiceField'dan geliyor)
            if hasattr(birim_value, 'ad'):
                instance.birim = birim_value.ad
                print(f"Save - Birim objesi bulundu, ad değeri: {birim_value.ad}")  # Debug
            # Eğer birim zaten bir string ise, olduğu gibi bırak
            elif isinstance(birim_value, str):
                # Eğer string bir sayı ise (ID), Birim objesini al
                if birim_value.isdigit():
                    try:
                        from .models import Birim
                        birim_obj = Birim.objects.get(pk=int(birim_value))
                        instance.birim = birim_obj.ad
                        print(f"Save - Birim ID'den alındı (string): {birim_obj.ad}")  # Debug
                    except Birim.DoesNotExist:
                        print(f"Save - Birim ID bulunamadı: {birim_value}")  # Debug
                        # Birim bulunamazsa, mevcut değeri koru veya varsayılan değer kullan
                        if not instance.birim:
                            instance.birim = 'Adet'
                else:
                    # String ama sayı değil, direkt kullan
                    instance.birim = birim_value
                    print(f"Save - Birim string olarak kaydedildi: {birim_value}")  # Debug
            # Eğer birim bir sayı ise (ID), Birim objesini al
            elif isinstance(birim_value, (int, str)) and str(birim_value).isdigit():
                try:
                    from .models import Birim
                    birim_obj = Birim.objects.get(pk=int(birim_value))
                    instance.birim = birim_obj.ad
                    print(f"Save - Birim ID'den alındı: {birim_obj.ad}")  # Debug
                except Birim.DoesNotExist:
                    print(f"Save - Birim ID bulunamadı: {birim_value}")  # Debug
                    # Birim bulunamazsa, mevcut değeri koru veya varsayılan değer kullan
                    if not instance.birim:
                        instance.birim = 'Adet'
        elif hasattr(instance, 'birim') and instance.birim:
            # Eğer birim değeri instance'da varsa ama cleaned_data'da yoksa, olduğu gibi bırak
            print(f"Save - Birim değeri instance'da mevcut: {instance.birim}")  # Debug
        else:
            # Birim seçilmemişse varsayılan değer
            if not instance.birim:
                instance.birim = 'Adet'
        
        # None değerleri için varsayılan değerler ata
        from decimal import Decimal
        if hasattr(instance, 'acilis_miktari') and instance.acilis_miktari is None:
            instance.acilis_miktari = Decimal('0')
        if hasattr(instance, 'satis_fiyati') and instance.satis_fiyati is None:
            instance.satis_fiyati = Decimal('0')
        if hasattr(instance, 'alis_fiyati') and instance.alis_fiyati is None:
            instance.alis_fiyati = Decimal('0')
        
        # Yeni kayıt oluşturuluyorsa, açılış miktarını mevcut miktara kopyala
        if not instance.pk and hasattr(instance, 'acilis_miktari') and instance.acilis_miktari:
            instance.mevcut_miktar = instance.acilis_miktari
            print(f"Save - Açılış miktarı mevcut miktara kopyalandı: {instance.acilis_miktari}")  # Debug
        
        if commit:
            print(f"Save - commit=True, kaydediliyor...")  # Debug
            print(f"Save - Final birim değeri: {getattr(instance, 'birim', None)}")  # Debug
            instance.save()
            print(f"Save - Kayıt başarılı, pk: {instance.pk}")  # Debug
        return instance


class CariForm(forms.ModelForm):
    class Meta:
        model = Cari
        fields = [f for f in ['unvan','vergi_no','yetkili','telefon','email','adres']
                  if f in _existing_field_names(Cari)]
        widgets = {
            'adres': forms.Textarea(attrs={'rows': 3}),
        }

class GenelAyarlarForm(forms.ModelForm):
    smtp_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control secret-field', 'autocomplete': 'new-password'}),
        label="SMTP şifre",
    )
    pop_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control secret-field', 'autocomplete': 'new-password'}),
        label="POP şifre",
    )
    imap_hesaplari_json = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 8, 'spellcheck': 'false'}),
        label="IMAP hesapları (JSON)",
        help_text='[{"email": "...", "password": "..."}] formatında.',
    )

    class Meta:
        model = GenelAyarlar
        fields = [
            'firma_ismi', 'firma_logo', 'telefon', 'email',
            'teslimat_adresi', 'fatura_adresi', 'vergi_dairesi', 'vergi_no',
            'tekora_aktif',
            'musteri_mail_cc_adresi', 'satinalma_mail_cc_adresi',
            'email_backend', 'smtp_host', 'smtp_port', 'smtp_use_tls', 'smtp_use_ssl',
            'smtp_username', 'smtp_timeout', 'default_from_email', 'server_email',
            'email_subject_prefix',
            'imap_server', 'imap_port', 'imap_use_ssl', 'imap_mailbox', 'imap_body_max_chars',
            'pop_server', 'pop_port', 'pop_use_ssl', 'pop_username',
            'para_birimi',
            'on_tanimli_satis_lokasyonu', 'on_tanimli_satin_alma_lokasyonu', 'on_tanimli_uretim_lokasyonu',
            'varsayilan_satis_teslimat_suresi', 'varsayilan_satin_alma_teslimat_suresi', 'varsayilan_uretim_suresi',
            'satis_irsaliyesi_oneki', 'satin_alma_irsaliyesi_oneki', 'is_emri_oneki',
        ]
        widgets = {
            'firma_ismi': forms.TextInput(attrs={'class': 'form-control'}),
            'firma_logo': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'telefon': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'teslimat_adresi': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'fatura_adresi': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'vergi_dairesi': forms.TextInput(attrs={'class': 'form-control'}),
            'vergi_no': forms.TextInput(attrs={'class': 'form-control'}),
            'tekora_aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'musteri_mail_cc_adresi': forms.EmailInput(attrs={'class': 'form-control'}),
            'satinalma_mail_cc_adresi': forms.EmailInput(attrs={'class': 'form-control'}),
            'email_backend': forms.Select(attrs={'class': 'form-select'}),
            'smtp_host': forms.TextInput(attrs={'class': 'form-control'}),
            'smtp_port': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 65535}),
            'smtp_use_tls': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'smtp_use_ssl': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'smtp_username': forms.TextInput(attrs={'class': 'form-control'}),
            'smtp_timeout': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'default_from_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'server_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'email_subject_prefix': forms.TextInput(attrs={'class': 'form-control'}),
            'imap_server': forms.TextInput(attrs={'class': 'form-control'}),
            'imap_port': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 65535}),
            'imap_use_ssl': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'imap_mailbox': forms.TextInput(attrs={'class': 'form-control'}),
            'imap_body_max_chars': forms.NumberInput(attrs={'class': 'form-control', 'min': 1024}),
            'pop_server': forms.TextInput(attrs={'class': 'form-control'}),
            'pop_port': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 65535}),
            'pop_use_ssl': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'pop_username': forms.TextInput(attrs={'class': 'form-control'}),
            'para_birimi': forms.Select(attrs={'class': 'form-select'}),
            'on_tanimli_satis_lokasyonu': forms.Select(attrs={'class': 'form-select'}),
            'on_tanimli_satin_alma_lokasyonu': forms.Select(attrs={'class': 'form-select'}),
            'on_tanimli_uretim_lokasyonu': forms.Select(attrs={'class': 'form-select'}),
            'varsayilan_satis_teslimat_suresi': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'varsayilan_satin_alma_teslimat_suresi': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'varsayilan_uretim_suresi': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'satis_irsaliyesi_oneki': forms.TextInput(attrs={'class': 'form-control'}),
            'satin_alma_irsaliyesi_oneki': forms.TextInput(attrs={'class': 'form-control'}),
            'is_emri_oneki': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        from .mail_config import format_imap_accounts_for_display, mask_secret

        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if (self.instance.smtp_password or '').strip():
                self.initial.setdefault('smtp_password', mask_secret(self.instance.smtp_password))
            if (self.instance.pop_password or '').strip():
                self.initial.setdefault('pop_password', mask_secret(self.instance.pop_password))
            self.initial.setdefault(
                'imap_hesaplari_json',
                format_imap_accounts_for_display(self.instance.imap_hesaplari),
            )

        # Para birimi queryset
        if 'para_birimi' in self.fields:
            self.fields['para_birimi'].queryset = ParaBirimi.objects.filter(aktif=True).order_by('kod')
            self.fields['para_birimi'].required = False
        
        # Depo queryset'leri
        for field_name in ['on_tanimli_satis_lokasyonu', 'on_tanimli_satin_alma_lokasyonu', 'on_tanimli_uretim_lokasyonu']:
            if field_name in self.fields:
                self.fields[field_name].queryset = Depo.objects.all().order_by('ad')
                self.fields[field_name].required = False

    def clean_smtp_password(self):
        from .mail_config import _is_masked

        value = (self.cleaned_data.get('smtp_password') or '').strip()
        if _is_masked(value) and self.instance and self.instance.pk:
            return self.instance.smtp_password
        return value

    def clean_pop_password(self):
        from .mail_config import _is_masked

        value = (self.cleaned_data.get('pop_password') or '').strip()
        if _is_masked(value) and self.instance and self.instance.pk:
            return self.instance.pop_password
        return value

    def clean_imap_hesaplari_json(self):
        from .mail_config import merge_imap_accounts_json

        raw = self.cleaned_data.get('imap_hesaplari_json') or '[]'
        old = list(self.instance.imap_hesaplari or []) if self.instance and self.instance.pk else []
        try:
            return merge_imap_accounts_json(raw, old)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.smtp_password = self.cleaned_data.get('smtp_password') or ''
        obj.pop_password = self.cleaned_data.get('pop_password') or ''
        obj.imap_hesaplari = self.cleaned_data.get('imap_hesaplari_json') or []
        if commit:
            obj.save()
        return obj
class KullaniciForm(forms.ModelForm):
    """Yeni kullanıcı ekleme formu"""
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label="Şifre",
        required=True
    )
    telefon = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label="Telefon Numarası"
    )
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'is_staff', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'is_staff': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'username': 'Kullanıcı Adı',
            'first_name': 'Ad',
            'last_name': 'Soyad',
            'email': 'E-Posta',
            'is_staff': 'Yönetici',
            'is_active': 'Aktif',
        }


class KullaniciDuzenleForm(forms.ModelForm):
    """Kullanıcı düzenleme formu"""
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label="Yeni Şifre (Değiştirmek istemiyorsanız boş bırakın)",
        required=False
    )
    telefon = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label="Telefon Numarası"
    )
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'is_staff', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'is_staff': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'username': 'Kullanıcı Adı',
            'first_name': 'Ad',
            'last_name': 'Soyad',
            'email': 'E-Posta',
            'is_staff': 'Yönetici',
            'is_active': 'Aktif',
        }

class OperasyonForm(forms.ModelForm):
    class Meta:
        model = Operasyon
        fields = ['ad', 'aciklama', 'aktif', 'sira', 'akis_dis_operasyon']
        widgets = {
            'ad': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Operasyon adı giriniz...'
            }),
            'aciklama': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Operasyon açıklaması...'
            }),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sira': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0
            }),
            'akis_dis_operasyon': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'ad': 'Operasyon Adı',
            'aciklama': 'Açıklama',
            'aktif': 'Aktif',
            'sira': 'Sıra',
            'akis_dis_operasyon': 'Canlı akışta dış operasyon',
        }


class DisOperasyonTipiForm(forms.ModelForm):
    operasyon_kodu = forms.SlugField(
        required=False,
        max_length=64,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Boş bırakılırsa adından otomatik üretilir',
        }),
        label='Operasyon kodu',
        help_text='Sistem içi benzersiz kod (ör. galvaniz_kaplama).',
    )

    class Meta:
        model = DisOperasyonTipi
        fields = ['ad', 'operasyon_kodu', 'aktif']
        widgets = {
            'ad': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Dış operasyon adı giriniz...',
            }),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'ad': 'Dış Operasyon Adı',
            'aktif': 'Aktif',
        }


class IstasyonForm(forms.ModelForm):
    class Meta:
        model = Istasyon
        fields = [
            'ad', 'aciklama', 'fotograf', 'maliyet', 'aktif', 'sira', 'cnc_makine_grubu',
            'akis_harita_emoji', 'akis_harita_kisa_aciklama', 'akis_harita_goster', 'akis_tip_dis',
        ]
        widgets = {
            'ad': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'İstasyon adı giriniz...'
            }),
            'aciklama': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'İstasyon açıklaması...'
            }),
            'fotograf': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'maliyet': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sira': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0
            }),
            'cnc_makine_grubu': forms.Select(attrs={'class': 'form-select'}),
            'akis_harita_emoji': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 16}),
            'akis_harita_kisa_aciklama': forms.TextInput(attrs={'class': 'form-control'}),
            'akis_harita_goster': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'akis_tip_dis': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'ad': 'İstasyon Adı',
            'cnc_makine_grubu': 'CNC makine grubu',
            'akis_harita_emoji': 'Canlı akış ikonu (emoji)',
            'akis_harita_kisa_aciklama': 'Canlı akış kısa açıklama',
            'akis_harita_goster': 'Canlı akış haritasında göster',
            'akis_tip_dis': 'Dış operasyon istasyonu',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'cnc_makine_grubu' in self.fields:
            self.fields['cnc_makine_grubu'].required = False


class EkipmanForm(forms.ModelForm):
    class Meta:
        model = Ekipman
        fields = ['ekipman_numarasi', 'ad', 'aciklama', 'fotograf', 'aktif', 'sira']
        widgets = {
            'ekipman_numarasi': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ekipman numarası giriniz...'
            }),
            'ad': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ekipman adı giriniz...'
            }),
            'aciklama': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Ekipman açıklaması...'
            }),
            'fotograf': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sira': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0
            })
        }
        labels = {
            'ekipman_numarasi': 'Ekipman Numarası',
            'ad': 'Ekipman Adı',
        }


class FiksturForm(forms.ModelForm):
    class Meta:
        model = Fikstur
        fields = ['fikstur_numarasi', 'ad', 'aciklama', 'fotograf', 'depo', 'raf', 'aktif', 'sira']
        widgets = {
            'fikstur_numarasi': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Fikstür numarası giriniz...'
            }),
            'ad': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Fikstür adı giriniz...'
            }),
            'aciklama': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Fikstür açıklaması...'
            }),
            'fotograf': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'depo': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_depo'
            }),
            'raf': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_raf'
            }),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sira': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0
            })
        }
        labels = {
            'fikstur_numarasi': 'Fikstür Numarası',
            'ad': 'Fikstür Adı',
            'aciklama': 'Açıklama',
            'fotograf': 'Fikstür Fotoğrafı',
            'depo': 'Depo',
            'raf': 'Raf',
            'aktif': 'Aktif',
            'sira': 'Sıra',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Depo seçenekleri
        from .models import Depo
        self.fields['depo'].queryset = Depo.objects.all().order_by('ad')
        self.fields['depo'].required = False
        self.fields['depo'].empty_label = "Depo Seçin..."
        
        # Raf seçenekleri - Depo seçilmişse sadece o deponun raflarını göster
        from .models import Raf
        depo_id = None
        
        # POST verisindeki depo değerine göre raf queryset'ini güncelle
        if self.data and 'depo' in self.data:
            try:
                depo_id = int(self.data.get('depo'))
            except (ValueError, TypeError):
                pass
        
        # Eğer mevcut bir kayıt düzenleniyorsa ve depo varsa, o deponun raflarını göster
        if self.instance and self.instance.pk and self.instance.depo:
            self.fields['raf'].queryset = Raf.objects.filter(depo=self.instance.depo).order_by('ad')
        elif depo_id:
            # POST verisindeki depo'ya göre rafları yükle (validation için)
            self.fields['raf'].queryset = Raf.objects.filter(depo_id=depo_id).order_by('ad')
        else:
            # Validation için tüm rafları göster (raf opsiyonel ve clean() metodunda kontrol ediliyor)
            self.fields['raf'].queryset = Raf.objects.all().order_by('ad')
        
        self.fields['raf'].required = False
        self.fields['raf'].empty_label = "Önce depo seçin..."
    
    def clean(self):
        cleaned_data = super().clean()
        depo = cleaned_data.get('depo')
        raf = cleaned_data.get('raf')
        
        # Eğer raf seçilmişse, o rafın seçilen depoya ait olduğunu kontrol et
        if raf:
            if not depo:
                raise forms.ValidationError({
                    'raf': 'Raf seçmek için önce bir depo seçmelisiniz.'
                })
            elif raf.depo != depo:
                raise forms.ValidationError({
                    'raf': 'Seçilen raf, seçilen depoya ait değil. Lütfen doğru rafı seçin.'
                })
        
        return cleaned_data

class OlcuAletiTuruForm(forms.ModelForm):
    class Meta:
        model = OlcuAletiTuru
        fields = ['ad', 'sira', 'aktif']
        widgets = {
            'ad': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Alet türü adı giriniz...'
            }),
            'sira': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0
            }),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'ad': 'Alet Türü',
            'sira': 'Sıra',
            'aktif': 'Aktif',
        }


class OlcuAletiForm(forms.ModelForm):
    class Meta:
        model = OlcuAleti
        fields = [
            'alet_turu', 'marka', 'model', 'seri_no', 'fotograf',
            'olcum_araligi', 'hassasiyet',
            'satın_alma_tarihi',
            'kullanim_yeri', 'sorumlu_kisi',
            'kritiklik_seviyesi', 'durum',
            # Şirket İçi Kalibrasyon
            'kalibrasyon_periyot_tipi', 'kalibrasyon_periyot_sayisi',
            'son_kalibrasyon_tarihi', 'sonraki_kalibrasyon_tarihi',
            # Dış Kalibrasyon
            'dis_kalibrasyon_gerekli', 'dis_kalibrasyon_periyot_tipi', 
            'dis_kalibrasyon_periyot_sayisi', 'dis_kalibrasyon_son_tarih', 
            'dis_kalibrasyon_sonraki_tarih',
            'aktif'
        ]
        widgets = {
            'alet_turu': forms.Select(attrs={'class': 'form-select', 'style': 'width: 100%;'}),
            'marka': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Marka...', 'id': 'id_marka', 'list': 'markalar_list'}),
            'model': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Model...'}),
            'seri_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Seri No...'}),
            'fotograf': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'olcum_araligi': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: 0-150 mm'}),
            'hassasiyet': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: ±0.01 mm'}),
            'satın_alma_tarihi': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'kullanim_yeri': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Kullanım yeri / İstasyon...', 'id': 'id_kullanim_yeri', 'list': 'kullanim_yeri_list'}),
            'sorumlu_kisi': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Sorumlu kişi...', 'id': 'id_sorumlu_kisi', 'list': 'sorumlu_kisi_list'}),
            'kritiklik_seviyesi': forms.Select(attrs={'class': 'form-select'}),
            'durum': forms.Select(attrs={'class': 'form-select'}),
            'kalibrasyon_periyot_tipi': forms.Select(attrs={'class': 'form-select', 'id': 'id_kalibrasyon_periyot_tipi'}),
            'kalibrasyon_periyot_sayisi': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'id': 'id_kalibrasyon_periyot_sayisi'}),
            'son_kalibrasyon_tarihi': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'sonraki_kalibrasyon_tarihi': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            # Dış Kalibrasyon
            'dis_kalibrasyon_gerekli': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_dis_kalibrasyon_gerekli'}),
            'dis_kalibrasyon_periyot_tipi': forms.Select(attrs={'class': 'form-select', 'id': 'id_dis_kalibrasyon_periyot_tipi'}),
            'dis_kalibrasyon_periyot_sayisi': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'id': 'id_dis_kalibrasyon_periyot_sayisi'}),
            'dis_kalibrasyon_son_tarih': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'id': 'id_dis_kalibrasyon_son_tarih'}),
            'dis_kalibrasyon_sonraki_tarih': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'id': 'id_dis_kalibrasyon_sonraki_tarih'}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'alet_turu': 'Alet Türü',
            'marka': 'Marka',
            'model': 'Model',
            'seri_no': 'Seri No',
            'fotograf': 'Cihaz Fotoğrafı',
            'olcum_araligi': 'Ölçüm Aralığı',
            'hassasiyet': 'Hassasiyet',
            'satın_alma_tarihi': 'Satın Alma Tarihi',
            'kullanim_yeri': 'Kullanım Yeri / İstasyon',
            'sorumlu_kisi': 'Sorumlu Kişi',
            'kritiklik_seviyesi': 'Kritiklik Seviyesi',
            'durum': 'Durum',
            'kalibrasyon_periyot_tipi': 'Periyot Tipi',
            'kalibrasyon_periyot_sayisi': 'Periyot Sayısı',
            'son_kalibrasyon_tarihi': 'Son Kalibrasyon Tarihi',
            'sonraki_kalibrasyon_tarihi': 'Bir Sonraki Kalibrasyon Tarihi',
            # Dış Kalibrasyon
            'dis_kalibrasyon_gerekli': 'Gerekli',
            'dis_kalibrasyon_periyot_tipi': 'Periyot Tipi',
            'dis_kalibrasyon_periyot_sayisi': 'Periyot Sayısı',
            'dis_kalibrasyon_son_tarih': 'Son Kalibrasyon Tarihi',
            'dis_kalibrasyon_sonraki_tarih': 'Bir Sonraki Kalibrasyon Tarihi',
            'aktif': 'Aktif',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['alet_turu'].queryset = OlcuAletiTuru.objects.filter(aktif=True).order_by('sira', 'ad')
        self.fields['kullanim_yeri'].required = False
        self.fields['sorumlu_kisi'].required = False
        self.fields['olcum_araligi'].required = False
        self.fields['hassasiyet'].required = False
        self.fields['satın_alma_tarihi'].required = False
        self.fields['son_kalibrasyon_tarihi'].required = False
        self.fields['sonraki_kalibrasyon_tarihi'].required = False
        # Dış Kalibrasyon alanları opsiyonel
        self.fields['dis_kalibrasyon_periyot_tipi'].required = False
        self.fields['dis_kalibrasyon_periyot_sayisi'].required = False
        self.fields['dis_kalibrasyon_son_tarih'].required = False
        self.fields['dis_kalibrasyon_sonraki_tarih'].required = False


class KalibrasyonKaydiForm(forms.ModelForm):
    class Meta:
        model = KalibrasyonKaydi
        fields = [
            'kalibrasyon_tarihi', 'kalibrasyon_tipi', 'standart_referansi',
            'sonuc', 'sapma_degeri', 'sertifika_rapor', 'aciklama'
        ]
        widgets = {
            'kalibrasyon_tarihi': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'kalibrasyon_tipi': forms.Select(attrs={'class': 'form-select'}),
            'standart_referansi': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: ISO 17025, firma prosedürü...'}),
            'sonuc': forms.Select(attrs={'class': 'form-select'}),
            'sapma_degeri': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Sapma değeri (varsa)...'}),
            'sertifika_rapor': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf'}),
            'aciklama': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Açıklama...'}),
        }
        labels = {
            'kalibrasyon_tarihi': 'Kalibrasyon Tarihi',
            'kalibrasyon_tipi': 'Kalibrasyon Tipi',
            'standart_referansi': 'Standart Referansı',
            'sonuc': 'Sonuç',
            'sapma_degeri': 'Sapma Değeri',
            'sertifika_rapor': 'Sertifika / Rapor Dosyası (PDF)',
            'aciklama': 'Açıklama',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['standart_referansi'].required = False
        self.fields['sapma_degeri'].required = False
        self.fields['sertifika_rapor'].required = False
        self.fields['aciklama'].required = False


class SigortaForm(forms.ModelForm):
    class Meta:
        model = Sigorta
        fields = [
            'varlik_adi', 'varlik_kimlik_no', 'varlik_aciklama', 'varlik_turu',
            'police_no', 'police_baslangic_tarihi', 'police_bitis_tarihi',
            'police_duzenleyen_firma', 'police_prim_bedeli', 'odeme_hesap_kart',
            'police_dosyasi'
        ]
        widgets = {
            'varlik_adi': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Varlık adı giriniz...'
            }),
            'varlik_kimlik_no': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Varlık kimlik numarası...'
            }),
            'varlik_aciklama': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Varlık açıklaması...'
            }),
            'varlik_turu': forms.Select(attrs={'class': 'form-select'}),
            'police_no': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Poliçe numarası...'
            }),
            'police_baslangic_tarihi': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'police_bitis_tarihi': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'police_duzenleyen_firma': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Poliçeyi düzenleyen firma...'
            }),
            'police_prim_bedeli': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
            'odeme_hesap_kart': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Hesap/kart bilgisi...'
            }),
            'police_dosyasi': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf'
            })
        }
        labels = {
            'varlik_adi': 'Varlık Adı',
            'varlik_kimlik_no': 'Varlık Kimlik Numarası',
            'varlik_aciklama': 'Varlık Açıklaması',
            'varlik_turu': 'Varlık Türü',
            'police_no': 'Poliçe Numarası',
            'police_baslangic_tarihi': 'Poliçe Başlangıç Tarihi',
            'police_bitis_tarihi': 'Poliçe Bitiş Tarihi',
            'police_duzenleyen_firma': 'Poliçeyi Düzenleyen Firma',
            'police_prim_bedeli': 'Poliçe Prim Bedeli',
            'odeme_hesap_kart': 'Ödemenin Yapıldığı Hesap/Kart Bilgisi',
            'police_dosyasi': 'Poliçe Dosyası (PDF)',
        }
class PersonelForm(forms.ModelForm):
    class Meta:
        model = Personel
        fields = [
            # Temel Bilgiler
            'personel_no', 'sicil_no', 'ad', 'soyad', 'telefon', 'email', 'cinsiyet',
            'dogum_tarihi', 'tc_kimlik_no', 'medeni_hali', 'kan_grubu',
            # Nüfus Bilgileri (cilt_no ve sayfa_no çıkarıldı)
            # İş Bilgileri
            'gorev', 'ozel_kod',
            # Ücret
            'saatlik_ucret',
            # Adres Bilgileri
            'adres', 'sehir', 'posta_kodu', 'ulke',
            # Fotoğraf
            'fotograf',
            # Durum (aktif, pdks_takip, bordro_islem çıkarıldı)
        ]
        widgets = {
            'personel_no': forms.TextInput(attrs={'class': 'form-control'}),
            'sicil_no': forms.TextInput(attrs={'class': 'form-control'}),
            'ad': forms.TextInput(attrs={'class': 'form-control'}),
            'soyad': forms.TextInput(attrs={'class': 'form-control'}),
            'telefon': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'cinsiyet': forms.Select(attrs={'class': 'form-select'}),
            'dogum_tarihi': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'tc_kimlik_no': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '11'}),
            'medeni_hali': forms.Select(attrs={'class': 'form-select'}),
            'kan_grubu': forms.Select(attrs={'class': 'form-select'}),
            'gorev': forms.TextInput(attrs={'class': 'form-control'}),
            'ozel_kod': forms.TextInput(attrs={'class': 'form-control'}),
            'saatlik_ucret': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'adres': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'sehir': forms.TextInput(attrs={'class': 'form-control'}),
            'posta_kodu': forms.TextInput(attrs={'class': 'form-control'}),
            'ulke': forms.TextInput(attrs={'class': 'form-control'}),
            'fotograf': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }


class GunlukCalismaForm(forms.ModelForm):
    class Meta:
        model = GunlukCalisma
        fields = [
            'personel', 'tarih', 'calisma_suresi', 'saat_ucreti', 
            'odenecek_tutar', 'odeme_durumu', 'odeme_sekli', 
            'odenen_tutar', 'aciklama'
        ]
        widgets = {
            'personel': forms.Select(attrs={'class': 'form-select', 'id': 'id_personel'}),
            'tarih': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'calisma_suresi': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
                'id': 'id_calisma_suresi'
            }),
            'saat_ucreti': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
                'id': 'id_saat_ucreti'
            }),
            'odenecek_tutar': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
                'readonly': True,
                'id': 'id_odenecek_tutar'
            }),
            'odeme_durumu': forms.Select(attrs={'class': 'form-select'}),
            'odeme_sekli': forms.Select(attrs={'class': 'form-select'}),
            'odenen_tutar': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
            'aciklama': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Açıklama...'
            })
        }
        labels = {
            'personel': 'Personel',
            'tarih': 'Çalışma Tarihi',
            'calisma_suresi': 'Çalışma Süresi (Saat)',
            'saat_ucreti': 'Saat Ücreti (TRY)',
            'odenecek_tutar': 'Ödenecek Tutar (TRY)',
            'odeme_durumu': 'Ödeme Durumu',
            'odeme_sekli': 'Ödeme Şekli',
            'odenen_tutar': 'Ödenen Tutar (TRY)',
            'aciklama': 'Açıklama',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'personel' in self.fields:
            self.fields['personel'].queryset = Personel.objects.filter(aktif=True).order_by('ad', 'soyad')


class AvansOdemeForm(forms.ModelForm):
    class Meta:
        model = AvansOdeme
        fields = ['personel', 'tarih', 'tutar', 'odeme_sekli', 'aciklama']
        widgets = {
            'personel': forms.Select(attrs={'class': 'form-select'}),
            'tarih': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'tutar': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
            'odeme_sekli': forms.Select(attrs={'class': 'form-select'}),
            'aciklama': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Açıklama...'
            })
        }
        labels = {
            'personel': 'Personel',
            'tarih': 'Ödeme Tarihi',
            'tutar': 'Ödenen Tutar (TRY)',
            'odeme_sekli': 'Ödeme Şekli',
            'aciklama': 'Açıklama',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'personel' in self.fields:
            self.fields['personel'].queryset = Personel.objects.filter(aktif=True).order_by('ad', 'soyad')


class PersonelIzinForm(forms.ModelForm):
    class Meta:
        model = PersonelIzin
        fields = ["personel", "izin_tipi", "baslangic_zamani", "bitis_zamani", "aciklama"]
        widgets = {
            "personel": forms.Select(attrs={"class": "form-select"}),
            "izin_tipi": forms.Select(attrs={"class": "form-select"}),
            "baslangic_zamani": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "bitis_zamani": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "aciklama": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Açıklama..."}),
        }
        labels = {
            "personel": "Personel",
            "izin_tipi": "İzin Tipi",
            "baslangic_zamani": "Başlangıç Tarih/Saat",
            "bitis_zamani": "Bitiş Tarih/Saat",
            "aciklama": "Açıklama",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "personel" in self.fields:
            self.fields["personel"].queryset = Personel.objects.filter(aktif=True).order_by("ad", "soyad")

    def clean(self):
        cleaned = super().clean()
        baslangic = cleaned.get("baslangic_zamani")
        bitis = cleaned.get("bitis_zamani")
        if baslangic and bitis and baslangic >= bitis:
            raise forms.ValidationError("Bitiş tarih/saat başlangıçtan sonra olmalı.")
        return cleaned


class PersonelBelgesiForm(forms.ModelForm):
    class Meta:
        model = PersonelBelgesi
        fields = [
            "personel",
            "belge_adi",
            "belge_no",
            "belge_dosyasi",
            "aciklama",
            "yenileme_gerekli",
            "yenileme_tarihi",
            "hatirlatma_gun_once",
        ]
        widgets = {
            "personel": forms.Select(attrs={"class": "form-select"}),
            "belge_adi": forms.TextInput(attrs={"class": "form-control", "placeholder": "Belge adı"}),
            "belge_no": forms.TextInput(attrs={"class": "form-control", "placeholder": "Varsa belge no"}),
            "belge_dosyasi": forms.FileInput(attrs={"class": "form-control"}),
            "aciklama": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "yenileme_gerekli": forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_yenileme_gerekli"}),
            "yenileme_tarihi": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "hatirlatma_gun_once": forms.NumberInput(attrs={"class": "form-control", "min": "1", "placeholder": "Orn: 7"}),
        }
        labels = {
            "yenileme_gerekli": "Yenileme gerekiyor mu?",
            "yenileme_tarihi": "Yenileme Tarihi",
            "hatirlatma_gun_once": "Kaç gün önce hatırlatılsın?",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "personel" in self.fields:
            self.fields["personel"].queryset = Personel.objects.filter(aktif=True).order_by("ad", "soyad")

    def clean(self):
        cleaned = super().clean()
        yenileme_gerekli = cleaned.get("yenileme_gerekli")
        yenileme_tarihi = cleaned.get("yenileme_tarihi")
        hatirlatma_gun_once = cleaned.get("hatirlatma_gun_once")

        if yenileme_gerekli:
            if not yenileme_tarihi:
                self.add_error("yenileme_tarihi", "Yenileme gerekli ise tarih zorunludur.")
            if not hatirlatma_gun_once:
                self.add_error("hatirlatma_gun_once", "Hatırlatma günü zorunludur.")
        else:
            cleaned["yenileme_tarihi"] = None
            cleaned["hatirlatma_gun_once"] = None

        return cleaned

class SiparisForm(forms.ModelForm):
    class Meta:
        model = Siparis
        fields = ['musteri', 'siparis_numarasi', 'olusturulma_tarihi', 'tamamlanma_tarihi', 
                  'etiketler', 'aciklama', 'siparis_mektubu', 'para_birimi', 'siparis_durumu']
        widgets = {
            'musteri': forms.Select(attrs={'class': 'form-select'}),
            'siparis_numarasi': forms.TextInput(attrs={'class': 'form-control'}),
            'olusturulma_tarihi': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'tamamlanma_tarihi': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'etiketler': forms.TextInput(attrs={'class': 'form-control'}),
            'aciklama': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'siparis_mektubu': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,application/pdf'}),
            'para_birimi': forms.Select(attrs={'class': 'form-select'}),
            'siparis_durumu': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'musteri': 'Müşteri',
            'siparis_numarasi': 'Sipariş Numarası',
            'olusturulma_tarihi': 'Sipariş Tarihi',
            'tamamlanma_tarihi': 'Teslim Tarihi',
            'etiketler': 'Etiketler',
            'aciklama': 'Notlar',
            'siparis_mektubu': 'Sipariş Mektubu (PDF)',
            'para_birimi': 'Para Birimi',
            'siparis_durumu': 'Sipariş Durumu',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'musteri' in self.fields:
            from .models import Musteri
            self.fields['musteri'].queryset = Musteri.objects.all().order_by('ad')
            self.fields['musteri'].required = False
        
        # Para birimi için choices'ı ParaBirimi modelinden al
        if 'para_birimi' in self.fields:
            from .models import ParaBirimi
            para_birimleri = ParaBirimi.objects.filter(aktif=True).order_by('kod')
            choices = [('', 'Para Birimi Seçin')]
            for pb in para_birimleri:
                choices.append((pb.kod, f"{pb.sembol} {pb.ad} ({pb.kod})"))
            self.fields['para_birimi'].widget.choices = choices
        if 'siparis_mektubu' in self.fields:
            self.fields['siparis_mektubu'].required = False

    def clean_siparis_mektubu(self):
        dosya = self.cleaned_data.get('siparis_mektubu')
        if not dosya:
            return dosya
        ad = (getattr(dosya, 'name', '') or '').lower()
        if not ad.endswith('.pdf'):
            raise ValidationError('Sipariş mektubu PDF formatında olmalıdır.')
        return dosya

class SiparisKalemiForm(forms.ModelForm):
    class Meta:
        model = SiparisKalemi
        fields = ['stok_item', 'miktar', 'birim_fiyat', 'indirim_yuzdesi', 'aciklama']
        widgets = {
            'stok_item': forms.Select(attrs={'class': 'form-select'}),
            'miktar': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'min': '0'}),
            'birim_fiyat': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'indirim_yuzdesi': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
            'aciklama': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'stok_item': 'Ürün',
            'miktar': 'Miktar',
            'birim_fiyat': 'Birim Fiyat',
            'indirim_yuzdesi': 'İndirim (%)',
            'aciklama': 'Açıklama',
        }

class MusteriForm(forms.ModelForm):
    kategoriler = forms.ModelMultipleChoiceField(
        queryset=Kategori.objects.all().order_by('ad'),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control',
            'size': 8,
            'style': 'min-height: 160px;',
        }),
        label='Etiketler / Kategoriler',
        help_text='Müşterinin ilgilendiği kategorileri seçin. Listeleme ve teklif süreçlerinde filtre olarak kullanılabilir.',
    )

    class Meta:
        model = Musteri
        fields = ['ad', 'telefon', 'email', 'adres', 'kategoriler']
        widgets = {
            'ad': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Müşteri adı giriniz...',
            }),
            'telefon': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Telefon numarası...',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'E-posta adresi...',
            }),
            'adres': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Adres bilgisi...',
            }),
        }
        labels = {
            'ad': 'Müşteri Adı',
            'telefon': 'Telefon',
            'email': 'E-posta',
            'adres': 'Adres',
        }

class SiparisMaliyetiForm(forms.ModelForm):
    """Sipariş maliyeti formu"""
    class Meta:
        model = SiparisMaliyeti
        fields = ['maliyet_tipi', 'aciklama', 'miktar', 'birim_fiyat', 'para_birimi', 'birim', 'kayit_tarihi', 'aciklama_detay']
        widgets = {
            'maliyet_tipi': forms.Select(attrs={'class': 'form-select'}),
            'aciklama': forms.TextInput(attrs={'class': 'form-control'}),
            'miktar': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'min': '0'}),
            'birim_fiyat': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'para_birimi': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '3'}),
            'birim': forms.TextInput(attrs={'class': 'form-control'}),
            'kayit_tarihi': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'aciklama_detay': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'maliyet_tipi': 'Maliyet Tipi',
            'aciklama': 'Açıklama',
            'miktar': 'Miktar',
            'birim_fiyat': 'Birim Fiyat',
            'para_birimi': 'Para Birimi',
            'birim': 'Birim',
            'kayit_tarihi': 'Kayıt Tarihi',
            'aciklama_detay': 'Detay Açıklama',
        }


class SatinalmaForm(forms.ModelForm):
    tedarikci_adi_manuel = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tedarikçi adı (manuel yaz)'}),
        label='Tedarikçi Adı (Manuel)'
    )
    
    class Meta:
        model = Satinalma
        fields = ['tedarikci', 'satinalma_numarasi', 'olusturulma_tarihi', 'tamamlanma_tarihi', 
                  'etiketler', 'lokasyon', 'para_birimi', 'teslim_durumu', 'notlar']
        widgets = {
            'tedarikci': forms.Select(attrs={'class': 'form-select'}),
            'satinalma_numarasi': forms.TextInput(attrs={'class': 'form-control'}),
            'olusturulma_tarihi': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'tamamlanma_tarihi': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'etiketler': forms.TextInput(attrs={'class': 'form-control'}),
            'lokasyon': forms.Select(attrs={'class': 'form-select'}),
            'para_birimi': forms.Select(attrs={'class': 'form-select'}),
            'teslim_durumu': forms.Select(attrs={'class': 'form-select'}),
            'notlar': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }
        labels = {
            'tedarikci': 'Tedarikçi',
            'satinalma_numarasi': 'Satın Alma Numarası',
            'olusturulma_tarihi': 'Oluşturulma Tarihi',
            'tamamlanma_tarihi': 'Tamamlanması Beklenen Tarih',
            'etiketler': 'Etiketler',
            'lokasyon': 'Lokasyon',
            'para_birimi': 'Para Birimi',
            'teslim_durumu': 'Teslim Alındı',
            'notlar': 'Notlar',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'tedarikci' in self.fields:
            from .models import Tedarikci
            self.fields['tedarikci'].queryset = Tedarikci.objects.all().order_by('ad')
            self.fields['tedarikci'].required = False
        
        if 'lokasyon' in self.fields:
            from .models import Depo
            self.fields['lokasyon'].queryset = Depo.objects.all().order_by('ad')
            self.fields['lokasyon'].required = False
        
        # Para birimi için choices'ı ParaBirimi modelinden al
        if 'para_birimi' in self.fields:
            from .models import ParaBirimi
            para_birimleri = ParaBirimi.objects.filter(aktif=True).order_by('kod')
            choices = [('', 'Para Birimi Seçin')]
            for pb in para_birimleri:
                choices.append((pb.kod, f"{pb.sembol} {pb.ad} ({pb.kod})"))
            self.fields['para_birimi'].widget.choices = choices
        
        # Teslim durumu için varsayılan değer (yeni kayıt için)
        if 'teslim_durumu' in self.fields and not (self.instance and self.instance.pk):
            self.fields['teslim_durumu'].initial = 'BEKLIYOR'
        
        # Mevcut kayıt için tedarikci_adi_manuel değerini doldur
        if self.instance and self.instance.pk:
            if not self.instance.tedarikci and self.instance.tedarikci_adi:
                self.fields['tedarikci_adi_manuel'].initial = self.instance.tedarikci_adi
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        # Eğer tedarikçi seçilmemişse ama manuel ad yazılmışsa, tedarikci_adi'ye kaydet
        if not instance.tedarikci and self.cleaned_data.get('tedarikci_adi_manuel'):
            instance.tedarikci_adi = self.cleaned_data['tedarikci_adi_manuel']
        elif instance.tedarikci:
            instance.tedarikci_adi = instance.tedarikci.ad
        if commit:
            instance.save()
        return instance


class SatinalmaKalemiForm(forms.ModelForm):
    class Meta:
        model = SatinalmaKalemi
        fields = ['stok_item', 'miktar', 'birim_fiyat', 'vergi_yuzdesi', 'notlar']
        widgets = {
            'stok_item': forms.Select(attrs={'class': 'form-select'}),
            'miktar': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'min': '0'}),
            'birim_fiyat': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'vergi_yuzdesi': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
            'notlar': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
        labels = {
            'stok_item': 'Stok',
            'miktar': 'Miktar',
            'birim_fiyat': 'Birim Fiyatı',
            'vergi_yuzdesi': 'Vergi (%)',
            'notlar': 'Notlar',
        }


class TalepForm(forms.ModelForm):
    class Meta:
        model = Talep
        fields = [
            "talep_tarihi",
            "departman",
            "kategori",
            "baslik",
            "oncelik",
            "istenen_termin",
            "aciklama",
        ]
        widgets = {
            "talep_tarihi": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "departman": forms.TextInput(attrs={"class": "form-control"}),
            "kategori": forms.Select(attrs={"class": "form-select"}),
            "baslik": forms.TextInput(attrs={"class": "form-control"}),
            "oncelik": forms.Select(attrs={"class": "form-select"}),
            "istenen_termin": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "aciklama": forms.Textarea(attrs={"class": "form-control", "rows": 6}),
        }
        labels = {
            "talep_tarihi": "Talep Tarihi",
            "departman": "Departman / Bölüm",
            "kategori": "Kategori",
            "baslik": "Talep Başlığı",
            "oncelik": "Öncelik",
            "istenen_termin": "İstenen Termin Tarihi",
            "aciklama": "Açıklama / İhtiyaç Nedeni",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            return
        bugun = date.today()
        self.initial.setdefault("departman", "Üretim")
        tt_raw = self.initial.get("talep_tarihi")
        if tt_raw is None:
            tt = bugun
        elif isinstance(tt_raw, str):
            tt = parse_date(tt_raw) or bugun
        else:
            tt = tt_raw
        self.initial.setdefault("talep_tarihi", tt)
        if "istenen_termin" not in self.initial:
            self.initial["istenen_termin"] = tt + timedelta(days=2)


class TalepKalemiForm(forms.ModelForm):
    class Meta:
        model = TalepKalemi
        fields = [
            "kalem_adi",
            "aciklama",
            "miktar",
            "birim",
            "marka_model_tercihi",
            "kullanim_yeri",
            "not_text",
            "durum",
        ]
        widgets = {
            "kalem_adi": forms.TextInput(attrs={"class": "form-control"}),
            "aciklama": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "miktar": forms.NumberInput(attrs={"class": "form-control", "step": "0.001", "min": "0"}),
            "birim": forms.Select(attrs={"class": "form-select"}),
            "marka_model_tercihi": forms.TextInput(attrs={"class": "form-control"}),
            "kullanim_yeri": forms.TextInput(attrs={"class": "form-control"}),
            "not_text": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "durum": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "kalem_adi": "Kalem Adı",
            "aciklama": "Açıklama",
            "miktar": "Miktar",
            "birim": "Birim",
            "marka_model_tercihi": "Marka / Model Tercihi",
            "kullanim_yeri": "Kullanım Yeri",
            "not_text": "Not",
            "durum": "Kalem Durumu",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["birim"].queryset = Birim.objects.all().order_by("ad")
        self.fields["birim"].required = False
        if (not self.instance.pk) and "birim" not in self.initial:
            adet = Birim.objects.filter(ad__iexact="Adet").first()
            if adet:
                self.initial["birim"] = adet.pk


TalepKalemiFormSet = forms.inlineformset_factory(
    Talep,
    TalepKalemi,
    form=TalepKalemiForm,
    extra=1,
    can_delete=True,
    min_num=0,
    validate_min=False,
)


class TalepSatinalmaBilgisiForm(forms.ModelForm):
    class Meta:
        model = TalepSatinalmaBilgisi
        fields = [
            "satinalma_sorumlusu",
            "tedarikci",
            "teklif_alindi",
            "siparis_verildi",
            "alim_yontemi",
            "notlar",
        ]
        widgets = {
            "satinalma_sorumlusu": forms.Select(attrs={"class": "form-select"}),
            "tedarikci": forms.Select(attrs={"class": "form-select"}),
            "teklif_alindi": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "siparis_verildi": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "alim_yontemi": forms.Select(attrs={"class": "form-select"}),
            "notlar": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["satinalma_sorumlusu"].queryset = User.objects.filter(is_active=True).order_by(
            "first_name", "last_name", "username"
        )
        self.fields["satinalma_sorumlusu"].required = False
        self.fields["tedarikci"].queryset = Tedarikci.objects.all().order_by("ad")
        self.fields["tedarikci"].required = False


class TalepKapatForm(forms.Form):
    kapanis_tipi = forms.ChoiceField(choices=Talep.KAPANIS_TIPLERI, widget=forms.Select(attrs={"class": "form-select"}))
    gerceklesen_toplam_tutar = forms.DecimalField(
        required=False,
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    kapanis_tedarikci = forms.ModelChoiceField(
        queryset=Tedarikci.objects.all(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    fatura_no = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    irsaliye_no = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    alim_tarihi = forms.DateField(required=False, widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}))
    teslim_alan_kisi = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    kapanis_notu = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}))


class TalepDosyaForm(forms.ModelForm):
    class Meta:
        model = TalepDosya
        fields = ["dosya", "aciklama", "tip"]
        widgets = {
            "dosya": forms.FileInput(attrs={"class": "form-control"}),
            "aciklama": forms.TextInput(attrs={"class": "form-control"}),
            "tip": forms.Select(attrs={"class": "form-select"}),
        }


class TalepNotEkleForm(forms.Form):
    mesaj = forms.CharField(
        label="Not",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )


class AracForm(forms.ModelForm):
    class Meta:
        model = Arac
        fields = ['plaka', 'marka', 'model', 'yil', 'arac_tipi', 'renk', 'sasi_no', 
                 'motor_no', 'foto', 'ruhsat_pdf', 'aciklama', 'aktif']
        widgets = {
            'plaka': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '34 ABC 123'}),
            'marka': forms.TextInput(attrs={'class': 'form-control'}),
            'model': forms.TextInput(attrs={'class': 'form-control'}),
            'yil': forms.NumberInput(attrs={'class': 'form-control', 'min': '1900', 'max': '2100'}),
            'arac_tipi': forms.Select(attrs={'class': 'form-select'}),
            'renk': forms.TextInput(attrs={'class': 'form-control'}),
            'sasi_no': forms.TextInput(attrs={'class': 'form-control'}),
            'motor_no': forms.TextInput(attrs={'class': 'form-control'}),
            'foto': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'ruhsat_pdf': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf'}),
            'aciklama': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'plaka': 'Plaka',
            'marka': 'Marka',
            'model': 'Model',
            'yil': 'Yıl',
            'arac_tipi': 'Araç Tipi',
            'renk': 'Renk',
            'sasi_no': 'Şasi No',
            'motor_no': 'Motor No',
            'foto': 'Araç Fotoğrafı',
            'ruhsat_pdf': 'Ruhsat PDF',
            'aciklama': 'Açıklama',
            'aktif': 'Aktif',
        }


class AracBelgesiForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        choices = [("", "---------")]
        choices += [
            (t.kod, t.ad)
            for t in AracBelgeTuru.objects.filter(aktif=True).order_by("sira", "ad")
        ]
        initial = None
        if self.instance and self.instance.pk and self.instance.belge_turu:
            initial = self.instance.belge_turu
        self.fields["belge_turu"] = forms.ChoiceField(
            choices=choices,
            required=True,
            initial=initial,
            widget=forms.Select(attrs={"class": "form-select"}),
            label="Belge Türü",
        )
        belge_turu = None
        if self.data:
            belge_turu = self.data.get("belge_turu")
        elif self.instance and self.instance.pk:
            belge_turu = self.instance.belge_turu
        elif self.initial.get("belge_turu"):
            belge_turu = self.initial.get("belge_turu")
        self.fields["gecerlilik_bitis"].required = not AracBelgeTuru.bitis_tarihi_gerekmez_mi(belge_turu)

    def clean(self):
        cleaned_data = super().clean()
        belge_turu = cleaned_data.get("belge_turu")
        if AracBelgeTuru.bitis_tarihi_gerekmez_mi(belge_turu):
            cleaned_data["gecerlilik_bitis"] = None
        elif not cleaned_data.get("gecerlilik_bitis"):
            self.add_error("gecerlilik_bitis", "Geçerlilik bitiş tarihi zorunludur.")
        return cleaned_data

    def clean_belge_turu(self):
        kod = self.cleaned_data.get("belge_turu")
        if not kod:
            return kod
        if not AracBelgeTuru.objects.filter(kod=kod, aktif=True).exists():
            raise forms.ValidationError("Geçersiz belge türü seçildi.")
        return kod

    class Meta:
        model = AracBelgesi
        fields = ['arac', 'belge_turu', 'gecerlilik_baslangic', 'gecerlilik_bitis',
                 'hasar_foto', 'belge_no', 'aciklama']
        widgets = {
            'arac': forms.Select(attrs={'class': 'form-select'}),
            'belge_turu': forms.Select(attrs={'class': 'form-select'}),
            'gecerlilik_baslangic': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'gecerlilik_bitis': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'hasar_foto': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'belge_no': forms.TextInput(attrs={'class': 'form-control'}),
            'aciklama': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'arac': 'Araç',
            'belge_turu': 'Belge Türü',
            'gecerlilik_baslangic': 'Geçerlilik Başlangıç Tarihi',
            'gecerlilik_bitis': 'Geçerlilik Bitiş Tarihi',
            'hasar_foto': 'Hasar Fotoğrafı (Sadece hasar belgesi için)',
            'belge_no': 'Belge No',
            'aciklama': 'Açıklama',
        }


class GayrimenkulForm(forms.ModelForm):
    class Meta:
        model = Gayrimenkul
        fields = [
            "ad",
            "tip",
            "sahiplik_tipi",
            "il",
            "ilce",
            "adres",
            "ada_parsel",
            "tapu_no",
            "metrekare",
            "kullanim_durumu",
            "sorumlu_kisi",
            "aciklama",
            "alis_veya_kira_bedeli",
            "para_birimi",
            "kira_baslangic_tarihi",
            "kira_bitis_tarihi",
            "yillik_emlak_vergisi",
            "vergi_odeme_periyodu",
            "sigorta_police_no",
            "sigorta_firmasi",
            "sigorta_baslangic_tarihi",
            "sigorta_bitis_tarihi",
            "sigorta_tutari",
            "aidat_site_gideri",
            "bakim_giderleri_notu",
            "yonetim_notlari",
        ]
        widgets = {
            "ad": forms.TextInput(attrs={"class": "form-control"}),
            "tip": forms.Select(attrs={"class": "form-select"}),
            "sahiplik_tipi": forms.Select(attrs={"class": "form-select"}),
            "il": forms.TextInput(attrs={"class": "form-control"}),
            "ilce": forms.TextInput(attrs={"class": "form-control"}),
            "adres": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "ada_parsel": forms.TextInput(attrs={"class": "form-control"}),
            "tapu_no": forms.TextInput(attrs={"class": "form-control"}),
            "metrekare": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "kullanim_durumu": forms.Select(attrs={"class": "form-select"}),
            "sorumlu_kisi": forms.TextInput(attrs={"class": "form-control"}),
            "aciklama": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "alis_veya_kira_bedeli": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "para_birimi": forms.TextInput(attrs={"class": "form-control", "maxlength": "3"}),
            "kira_baslangic_tarihi": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "kira_bitis_tarihi": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "yillik_emlak_vergisi": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "vergi_odeme_periyodu": forms.Select(attrs={"class": "form-select"}),
            "sigorta_police_no": forms.TextInput(attrs={"class": "form-control"}),
            "sigorta_firmasi": forms.TextInput(attrs={"class": "form-control"}),
            "sigorta_baslangic_tarihi": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "sigorta_bitis_tarihi": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "sigorta_tutari": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "aidat_site_gideri": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "bakim_giderleri_notu": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "yonetim_notlari": forms.Textarea(attrs={"class": "form-control", "rows": 6}),
        }


class GayrimenkulIslemiForm(forms.ModelForm):
    class Meta:
        model = GayrimenkulIslemi
        fields = [
            "gayrimenkul",
            "islem_tipi",
            "aciklama",
            "tutar",
            "para_birimi",
            "vade_tarihi",
            "odeme_tarihi",
            "durum",
            "dosya",
            "hatirlatma_tarihi",
            "not_metni",
        ]
        widgets = {
            "gayrimenkul": forms.Select(attrs={"class": "form-select"}),
            "islem_tipi": forms.Select(attrs={"class": "form-select"}),
            "aciklama": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "tutar": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "para_birimi": forms.TextInput(attrs={"class": "form-control", "maxlength": "3"}),
            "vade_tarihi": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "odeme_tarihi": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "durum": forms.Select(attrs={"class": "form-select"}),
            "dosya": forms.FileInput(attrs={"class": "form-control"}),
            "hatirlatma_tarihi": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "not_metni": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class GayrimenkulDosyaForm(forms.ModelForm):
    class Meta:
        model = GayrimenkulDosya
        fields = ["gayrimenkul", "baslik", "dosya", "aciklama"]
        widgets = {
            "gayrimenkul": forms.Select(attrs={"class": "form-select"}),
            "baslik": forms.TextInput(attrs={"class": "form-control"}),
            "dosya": forms.FileInput(attrs={"class": "form-control"}),
            "aciklama": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class UretimStandartiForm(forms.ModelForm):
    """Üretim Standart formu"""
    class Meta:
        model = UretimStandarti
        fields = ['kod', 'ad', 'aciklama', 'pdf_dosya', 'olusturma_tarihi', 'revizyon_tarihi', 'revizyon_aciklama', 'aktif', 'sira']
        widgets = {
            'kod': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Örn: UST-001'
            }),
            'ad': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Standart adı giriniz...'
            }),
            'aciklama': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Standart açıklaması...'
            }),
            'pdf_dosya': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf'
            }),
            'olusturma_tarihi': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'revizyon_tarihi': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'revizyon_aciklama': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Revizyon açıklaması...'
            }),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sira': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0
            })
        }
        labels = {
            'kod': 'Standart Kodu',
            'ad': 'Standart Adı',
            'aciklama': 'Açıklama',
            'pdf_dosya': 'PDF Dosyası',
            'olusturma_tarihi': 'İlk Oluşturma Tarihi',
            'revizyon_tarihi': 'Son Revizyon Tarihi',
            'revizyon_aciklama': 'Revizyon Açıklaması',
            'aktif': 'Aktif',
            'sira': 'Sıra',
        }


class UretimStandartiRevizyonForm(forms.Form):
    """Standart revizyon formu - önceki versiyonu arşive alır"""
    yeni_pdf_dosya = forms.FileField(
        required=True,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf'
        }),
        label='Yeni PDF Dosyası'
    )
    revizyon_tarihi = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label='Revizyon Tarihi'
    )
    revizyon_aciklama = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Revizyon açıklaması...'
        }),
        label='Revizyon Açıklaması'
    )


class BankaHesabiForm(forms.ModelForm):
    """Banka hesabı formu"""
    class Meta:
        model = BankaHesabi
        fields = ['hesap_adi', 'banka_adi', 'iban', 'para_birimi', 'hesap_tipi', 'hesap_sahibi', 
                 'sube_kodu', 'hesap_no', 'fotograf', 'aciklama', 'aktif']
        widgets = {
            'hesap_adi': forms.TextInput(attrs={'class': 'form-control'}),
            'banka_adi': forms.TextInput(attrs={'class': 'form-control'}),
            'iban': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'TR00 0000 0000 0000 0000 0000 00'}),
            'para_birimi': forms.Select(attrs={'class': 'form-select'}),
            'hesap_tipi': forms.Select(attrs={'class': 'form-select'}),
            'hesap_sahibi': forms.TextInput(attrs={'class': 'form-control'}),
            'sube_kodu': forms.TextInput(attrs={'class': 'form-control'}),
            'hesap_no': forms.TextInput(attrs={'class': 'form-control'}),
            'fotograf': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'aciklama': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'hesap_adi': 'Hesap Adı',
            'banka_adi': 'Banka Adı',
            'iban': 'IBAN Numarası',
            'para_birimi': 'Hesap para birimi',
            'hesap_tipi': 'Hesap Tipi',
            'hesap_sahibi': 'Hesap Sahibi',
            'sube_kodu': 'Şube Kodu',
            'hesap_no': 'Hesap Numarası',
            'fotograf': 'Fotoğraf',
            'aciklama': 'Açıklama',
            'aktif': 'Aktif',
        }


class KrediKartiForm(forms.ModelForm):
    """Kredi kartı formu"""
    class Meta:
        model = KrediKarti
        fields = ['kart_adi', 'kart_numarasi', 'son_kullanim_tarihi', 'cvv', 
                 'kart_sahibi', 'banka_adi', 'fotograf', 'aciklama', 'aktif']
        widgets = {
            'kart_adi': forms.TextInput(attrs={'class': 'form-control'}),
            'kart_numarasi': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '0000 0000 0000 0000', 'maxlength': '19'}),
            'son_kullanim_tarihi': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'MM/YY', 'maxlength': '5'}),
            'cvv': forms.TextInput(attrs={'class': 'form-control', 'type': 'password', 'maxlength': '4', 'autocomplete': 'off'}),
            'kart_sahibi': forms.TextInput(attrs={'class': 'form-control'}),
            'banka_adi': forms.TextInput(attrs={'class': 'form-control'}),
            'fotograf': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'aciklama': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'kart_adi': 'Kart Adı',
            'kart_numarasi': 'Kart Numarası',
            'son_kullanim_tarihi': 'Son Kullanma Tarihi',
            'cvv': 'CVV Kodu',
            'kart_sahibi': 'Kart Sahibi',
            'banka_adi': 'Banka Adı',
            'fotograf': 'Fotoğraf',
            'aciklama': 'Açıklama',
            'aktif': 'Aktif',
        }
    
    def clean_kart_numarasi(self):
        """Kart numarasını temizle ve doğrula"""
        kart_numarasi = self.cleaned_data.get('kart_numarasi', '').replace(' ', '').replace('-', '')
        if len(kart_numarasi) < 13 or len(kart_numarasi) > 19:
            raise ValidationError('Kart numarası 13-19 haneli olmalıdır.')
        if not kart_numarasi.isdigit():
            raise ValidationError('Kart numarası sadece rakam içermelidir.')
        return kart_numarasi
    
    def clean_son_kullanim_tarihi(self):
        """Son kullanma tarihini doğrula"""
        tarih = self.cleaned_data.get('son_kullanim_tarihi', '')
        if len(tarih) != 5 or tarih[2] != '/':
            raise ValidationError('Son kullanma tarihi MM/YY formatında olmalıdır (örn: 12/25)')
        try:
            ay = int(tarih[:2])
            yil = int(tarih[3:])
            if ay < 1 or ay > 12:
                raise ValidationError('Ay 01-12 arasında olmalıdır.')
            if yil < 0 or yil > 99:
                raise ValidationError('Yıl 00-99 arasında olmalıdır.')
        except ValueError:
            raise ValidationError('Son kullanma tarihi MM/YY formatında olmalıdır (örn: 12/25)')
        return tarih


def _turkish_money_to_decimal_string(value):
    """POST'tan gelen TR para metnini (örn. 1.123.450,45 veya 1123450.45) Decimal için dizgeye çevirir."""
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    s = str(value).strip().replace(" ", "").replace("\u00a0", "")
    if not s:
        return None
    neg = False
    if s.startswith("-"):
        neg = True
        s = s[1:]
    if not s:
        return None
    num_str = None
    if "," in s and "." in s:
        num_str = s.replace(".", "").replace(",", ".")
    elif s.count(",") > 1:
        parts = s.split(",")
        dec = parts[-1]
        num_str = "".join(parts[:-1]).replace(".", "") + "." + dec
    elif "," in s:
        num_str = s.replace(",", ".")
    elif "." in s:
        last = s.rfind(".")
        after = s[last + 1 :]
        if 0 < len(after) <= 2 and last > 0:
            before = s[:last].replace(".", "")
            num_str = before + "." + after
        else:
            num_str = s.replace(".", "")
    else:
        num_str = s
    if neg:
        num_str = "-" + num_str
    return num_str


class TurkishMoneyDecimalField(forms.DecimalField):
    """Binlik ayırıcı nokta, ondalık virgül (tr-TR) ile girilen tutarları kabul eder."""

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, Decimal):
            value = format(value, "f")
        try:
            normalized = _turkish_money_to_decimal_string(value)
            if normalized is None:
                return None
        except (TypeError, ValueError):
            raise forms.ValidationError(self.error_messages["invalid"], code="invalid")
        return super().to_python(normalized)


class AylikOdemeForm(forms.ModelForm):
    """Aylık ödeme formu"""
    tutar = TurkishMoneyDecimalField(
        max_digits=12,
        decimal_places=2,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "id": "id_tutar",
                "inputmode": "decimal",
                "autocomplete": "off",
                "placeholder": "Örn: 1.123.450,45",
            }
        ),
    )
    tekrar_sayisi = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=12,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'id': 'id_tekrar_sayisi',
            'min': '1',
            'max': '12',
            'style': 'display: none;'
        }),
        label='Tekrar Sayısı',
        help_text='Bu ödemenin kaç kez tekrarlanacağını belirtin (1-12 arası)'
    )
    
    class Meta:
        model = AylikOdeme
        fields = ['odeme_aciklamasi', 'odeme_sekli', 'banka_hesabi', 'kredi_karti',
                 'kayit_tarihi', 'odeme_tarihi', 'tutar', 'para_birimi', 'tekrar_eden', 'aktif',
                 'odeme_durumu', 'odeme_yapildi_tarih', 'hatirlatma_gun_once', 'aciklama']
        widgets = {
            'odeme_aciklamasi': forms.TextInput(attrs={'class': 'form-control'}),
            'odeme_sekli': forms.Select(attrs={'class': 'form-select', 'id': 'id_odeme_sekli'}),
            'banka_hesabi': forms.Select(attrs={'class': 'form-select', 'id': 'id_banka_hesabi'}),
            'kredi_karti': forms.Select(attrs={'class': 'form-select', 'id': 'id_kredi_karti'}),
            'kayit_tarihi': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'odeme_tarihi': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'tekrar_eden': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_tekrar_eden'}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'odeme_durumu': forms.Select(attrs={'class': 'form-select'}),
            'odeme_yapildi_tarih': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'hatirlatma_gun_once': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '365',
                'id': 'id_hatirlatma_gun_once',
            }),
            'aciklama': forms.Textarea(attrs={'class': 'form-control', 'rows': 8}),
            'para_birimi': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'odeme_aciklamasi': 'Ödeme Açıklaması',
            'odeme_sekli': 'Ödeme Şekli',
            'banka_hesabi': 'Banka Hesabı',
            'kredi_karti': 'Kredi Kartı',
            'kayit_tarihi': 'Kayıt Tarihi',
            'odeme_tarihi': 'Ödeme Tarihi',
            'tutar': 'Tutar',
            'tekrar_eden': 'Tekrar Eden Ödeme',
            'aktif': 'Aktif',
            'odeme_durumu': 'Ödeme Durumu',
            'odeme_yapildi_tarih': 'Ödeme Yapıldı Tarihi',
            'hatirlatma_gun_once': 'Kaç gün önce hatırlatılsın?',
            'aciklama': 'Açıklama',
            'para_birimi': 'Para Birimi',
        }
    
    def __init__(self, *args, **kwargs):
        plan_taksit_sayisi = kwargs.pop("plan_taksit_sayisi", None)
        super().__init__(*args, **kwargs)
        # Sadece aktif olanları göster
        self.fields['banka_hesabi'].queryset = BankaHesabi.objects.filter(aktif=True)
        self.fields['kredi_karti'].queryset = KrediKarti.objects.filter(aktif=True)
        
        # Para birimi queryset - sadece aktif olanlar
        from .models import ParaBirimi
        self.fields['para_birimi'].queryset = ParaBirimi.objects.filter(aktif=True)
        
        # Düzenleme: ana kayıt veya çok taksitli planda tekrar sayısı alanı görünsün
        show_tekrar_sayisi = False
        if self.instance and self.instance.pk:
            if self.instance.tekrar_eden:
                show_tekrar_sayisi = True
            elif plan_taksit_sayisi and plan_taksit_sayisi > 1:
                show_tekrar_sayisi = True
        if show_tekrar_sayisi:
            self.fields["tekrar_sayisi"].widget.attrs["style"] = "display: block;"
            self.fields["tekrar_sayisi"].required = False
        
        # Ödeme şekline göre alanları başlangıçta gizle
        if self.instance and self.instance.pk:
            odeme_sekli = self.instance.odeme_sekli
        else:
            odeme_sekli = self.data.get('odeme_sekli', '') if self.data else ''
        
        if odeme_sekli == 'BANKA_HESABI' or odeme_sekli == 'HAVALE_EFT':
            self.fields['banka_hesabi'].required = True
            self.fields['kredi_karti'].required = False
            self.fields['kredi_karti'].widget.attrs['style'] = 'display:none;'
        elif odeme_sekli == 'KREDI_KARTI':
            self.fields['kredi_karti'].required = True
            self.fields['banka_hesabi'].required = False
            self.fields['banka_hesabi'].widget.attrs['style'] = 'display:none;'
        else:
            self.fields['banka_hesabi'].required = False
            self.fields['kredi_karti'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        odeme_sekli = cleaned_data.get('odeme_sekli')
        banka_hesabi = cleaned_data.get('banka_hesabi')
        kredi_karti = cleaned_data.get('kredi_karti')
        tekrar_eden = cleaned_data.get('tekrar_eden', False)
        tekrar_sayisi = cleaned_data.get('tekrar_sayisi')
        
        if odeme_sekli in ['BANKA_HESABI', 'HAVALE_EFT']:
            if not banka_hesabi:
                raise ValidationError({'banka_hesabi': 'Banka hesabı seçilmelidir.'})
        elif odeme_sekli == 'KREDI_KARTI':
            if not kredi_karti:
                raise ValidationError({'kredi_karti': 'Kredi kartı seçilmelidir.'})
        
        # Tekrar eden ödeme seçilmişse tekrar sayısı kontrolü
        if tekrar_eden:
            if not tekrar_sayisi or tekrar_sayisi < 1 or tekrar_sayisi > 12:
                raise ValidationError({'tekrar_sayisi': 'Tekrar sayısı 1 ile 12 arasında olmalıdır.'})

        hg = cleaned_data.get("hatirlatma_gun_once")
        if hg is not None and (hg < 1 or hg > 365):
            self.add_error("hatirlatma_gun_once", "1 ile 365 gün arasında giriniz.")
        
        return cleaned_data


# ============================================================================
# Kalite Yönetimi Modülü Formları
# ============================================================================

class ComplaintForm(forms.ModelForm):
    """Şikayet/Uygunsuzluk formu"""
    class Meta:
        model = Complaint
        fields = [
            'type', 'customer', 'related_order', 'product', 'product_revision',
            'lot_serial', 'category', 'severity', 'affected_qty', 'description', 'status'
        ]
        widgets = {
            'type': forms.Select(attrs={'class': 'form-select'}),
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'related_order': forms.Select(attrs={'class': 'form-select'}),
            'product': forms.Select(attrs={'class': 'form-select'}),
            'product_revision': forms.TextInput(attrs={'class': 'form-control'}),
            'lot_serial': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.TextInput(attrs={'class': 'form-control'}),
            'severity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5}),
            'affected_qty': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'min': '0'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 8}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'type': 'Tip',
            'customer': 'Müşteri',
            'related_order': 'İlgili Sipariş',
            'product': 'Ürün',
            'product_revision': 'Ürün Revizyonu',
            'lot_serial': 'Lot/Seri No',
            'category': 'Kategori',
            'severity': 'Şiddet (1-5)',
            'affected_qty': 'Etkilenen Miktar',
            'description': 'Açıklama',
            'status': 'Durum',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Musteri.objects.all().order_by('ad')
        self.fields['product'].queryset = StokItem.objects.filter(arsivli=False).order_by('ad')
        self.fields['related_order'].required = False
        # İlgili sipariş seçim kutusunu daha büyük yap
        self.fields['related_order'].widget.attrs['style'] = 'width: 100%; min-height: 40px;'
        self.fields['product_revision'].required = False
        self.fields['lot_serial'].required = False


class ComplaintAttachmentForm(forms.ModelForm):
    """Şikayet eki formu"""
    class Meta:
        model = ComplaintAttachment
        fields = ['file', 'note']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'file': 'Dosya',
            'note': 'Not',
        }


class CapaActionForm(forms.ModelForm):
    """CAPA Aksiyonu formu"""
    class Meta:
        model = CapaAction
        fields = [
            'action_type', 'root_cause_method', 'root_cause_text',
            'action_text', 'owner', 'due_date', 'status'
        ]
        widgets = {
            'action_type': forms.Select(attrs={'class': 'form-select'}),
            'root_cause_method': forms.Select(attrs={'class': 'form-select'}),
            'root_cause_text': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'action_text': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'owner': forms.Select(attrs={'class': 'form-select'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'action_type': 'Aksiyon Tipi',
            'root_cause_method': 'Kök Neden Analiz Yöntemi',
            'root_cause_text': 'Kök Neden',
            'action_text': 'Aksiyon',
            'owner': 'Sorumlu',
            'due_date': 'Bitiş Tarihi',
            'status': 'Durum',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['owner'].queryset = User.objects.filter(is_active=True).order_by('username')
        self.fields['root_cause_method'].required = False


class EcoChangeForm(forms.ModelForm):
    """ECO (Mühendislik Değişiklik Emri) formu"""
    class Meta:
        model = EcoChange
        fields = [
            'complaint', 'change_type', 'product', 'from_revision',
            'to_revision', 'description', 'effective_from_date'
        ]
        widgets = {
            'complaint': forms.Select(attrs={'class': 'form-select'}),
            'change_type': forms.Select(attrs={'class': 'form-select'}),
            'product': forms.Select(attrs={'class': 'form-select'}),
            'from_revision': forms.TextInput(attrs={'class': 'form-control'}),
            'to_revision': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'effective_from_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }
        labels = {
            'complaint': 'İlgili Şikayet',
            'change_type': 'Değişiklik Tipi',
            'product': 'Ürün',
            'from_revision': 'Önceki Revizyon',
            'to_revision': 'Yeni Revizyon',
            'description': 'Açıklama',
            'effective_from_date': 'Geçerlilik Başlangıç Tarihi',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['complaint'].queryset = Complaint.objects.all().order_by('-created_at')
        self.fields['product'].queryset = StokItem.objects.filter(arsivli=False).order_by('ad')
        self.fields['complaint'].required = False
        self.fields['from_revision'].required = False


class AlertRuleForm(forms.ModelForm):
    """Uyarı Kuralı formu"""
    class Meta:
        model = AlertRule
        fields = [
            'scope', 'product', 'product_revision', 'customer', 'category',
            'severity_threshold', 'message', 'level', 'active',
            'valid_from', 'valid_to'
        ]
        widgets = {
            'scope': forms.Select(attrs={'class': 'form-select', 'onchange': 'updateScopeFields()'}),
            'product': forms.Select(attrs={'class': 'form-select'}),
            'product_revision': forms.TextInput(attrs={'class': 'form-control'}),
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.TextInput(attrs={'class': 'form-control'}),
            'severity_threshold': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'level': forms.Select(attrs={'class': 'form-select'}),
            'active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'valid_from': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'valid_to': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        }
        labels = {
            'scope': 'Kapsam',
            'product': 'Ürün',
            'product_revision': 'Ürün Revizyonu',
            'customer': 'Müşteri',
            'category': 'Kategori',
            'severity_threshold': 'Şiddet Eşiği',
            'message': 'Mesaj',
            'level': 'Seviye',
            'active': 'Aktif',
            'valid_from': 'Geçerlilik Başlangıç',
            'valid_to': 'Geçerlilik Bitiş',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = StokItem.objects.filter(arsivli=False).order_by('ad')
        self.fields['customer'].queryset = Musteri.objects.all().order_by('ad')
        self.fields['product'].required = False
        self.fields['product_revision'].required = False
        self.fields['customer'].required = False
        self.fields['category'].required = False
        self.fields['severity_threshold'].required = False
        self.fields['valid_to'].required = False


class UretimDegisiklikKaydiForm(forms.ModelForm):
    """Üretim değişiklik takip formu"""

    class Meta:
        model = UretimDegisiklikKaydi
        fields = [
            "urun",
            "degisiklik_tipi",
            "baslik",
            "aciklama",
            "teknik_resim_guncellenecek",
            "kati_model_guncellenecek",
            "tekos_recete_guncellenecek",
            "cnc_programi_guncellenecek",
            "oncelik",
            "termin_tarihi",
            "ek_not",
            "durum",
            "kapatma_notu",
        ]
        widgets = {
            "urun": forms.Select(attrs={"class": "form-select"}),
            "degisiklik_tipi": forms.TextInput(attrs={"class": "form-control", "placeholder": "Örn: Parça değişikliği, teknik revizyon"}),
            "baslik": forms.TextInput(attrs={"class": "form-control", "placeholder": "Kısa başlık"}),
            "aciklama": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Sorunu/değişiklik ihtiyacını detaylı yazın"}),
            "teknik_resim_guncellenecek": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "kati_model_guncellenecek": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "tekos_recete_guncellenecek": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "cnc_programi_guncellenecek": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "oncelik": forms.Select(attrs={"class": "form-select"}),
            "termin_tarihi": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "ek_not": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "durum": forms.Select(attrs={"class": "form-select"}),
            "kapatma_notu": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Tamamlandığında kapatma notu girin"}),
        }
        labels = {
            "urun": "Ürün",
            "degisiklik_tipi": "Değişiklik tipi",
            "baslik": "Başlık",
            "aciklama": "Açıklama",
            "teknik_resim_guncellenecek": "Teknik resim güncellenecek",
            "kati_model_guncellenecek": "Katı model güncellenecek",
            "tekos_recete_guncellenecek": "Tekos reçetesi güncellenecek",
            "cnc_programi_guncellenecek": "CNC programı güncellenecek",
            "oncelik": "Öncelik",
            "termin_tarihi": "Termin",
            "ek_not": "Ek not",
            "durum": "Durum",
            "kapatma_notu": "Kapatma notu",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["urun"].queryset = StokItem.objects.filter(arsivli=False).order_by("stok_kodu", "ad")
        self.fields["urun"].required = False
        self.fields["termin_tarihi"].required = False
        self.fields["ek_not"].required = False
        self.fields["kapatma_notu"].required = False


class ControlPlanForm(forms.ModelForm):
    """Kontrol Planı formu"""
    class Meta:
        model = ControlPlan
        fields = ['product', 'revision', 'effective_from', 'status', 'description']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'revision': forms.TextInput(attrs={'class': 'form-control'}),
            'effective_from': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'product': 'Ürün',
            'revision': 'Revizyon',
            'effective_from': 'Geçerlilik Başlangıç Tarihi',
            'status': 'Durum',
            'description': 'Açıklama',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = StokItem.objects.filter(arsivli=False).order_by('ad')
        self.fields['description'].required = False


class ControlItemForm(forms.ModelForm):
    """Kontrol Planı Maddesi formu - Güncellenmiş versiyon"""
    class Meta:
        model = ControlItem
        fields = [
            'operation_step', 'name', 'inspection_type', 'unit', 'nominal', 
            'min_value', 'max_value', 'text_criteria', 'method',
            'frequency_type', 'frequency_n', 'sample_size',
            'criticality', 'requires_instrument', 'requires_attachment', 
            'requires_ack', 'display_order'
        ]
        widgets = {
            'operation_step': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'inspection_type': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.TextInput(attrs={'class': 'form-control'}),
            'nominal': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'min_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'max_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'text_criteria': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'method': forms.TextInput(attrs={'class': 'form-control'}),
            'frequency_type': forms.Select(attrs={'class': 'form-select'}),
            'frequency_n': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'sample_size': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'criticality': forms.Select(attrs={'class': 'form-select'}),
            'requires_instrument': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requires_attachment': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requires_ack': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
        }
        labels = {
            'operation_step': 'Operasyon Adımı',
            'name': 'Kontrol Adı',
            'inspection_type': 'Kontrol Tipi',
            'unit': 'Birim',
            'nominal': 'Nominal Değer',
            'min_value': 'Min. Değer',
            'max_value': 'Max. Değer',
            'text_criteria': 'Metin Kriterleri',
            'method': 'Ölçüm Metodu',
            'frequency_type': 'Frekans Tipi',
            'frequency_n': 'Frekans N Değeri',
            'sample_size': 'Örnek Boyutu',
            'criticality': 'Kritiklik',
            'requires_instrument': 'Ölçü Aleti Gerekli',
            'requires_attachment': 'Ek Dosya Gerekli',
            'requires_ack': 'Onay Gerekli',
            'display_order': 'Görüntüleme Sırası',
        }
    
    def __init__(self, *args, **kwargs):
        plan = kwargs.pop('plan', None)
        super().__init__(*args, **kwargs)
        
        # Operasyon adımlarını plan'a göre filtrele
        if plan:
            recete = plan.product.recete_set.first()
            if recete:
                self.fields['operation_step'].queryset = recete.operasyonlar.all().order_by('sira')
        else:
            self.fields['operation_step'].queryset = ReceteOperasyon.objects.none()
        
        # İsteğe bağlı alanlar
        optional_fields = ['operation_step', 'unit', 'nominal', 'min_value', 'max_value', 
                          'text_criteria', 'method', 'frequency_n', 'sample_size', 'display_order']
        for field in optional_fields:
            self.fields[field].required = False


class WorkOrderInspectionForm(forms.ModelForm):
    """İş emri kontrol kaydı formu"""
    class Meta:
        model = WorkOrderInspection
        fields = [
            'control_item', 'sample_no', 'measured_value', 'pass_fail',
            'instrument', 'attachment', 'notes', 'disposition', 
            'disposition_reason'
        ]
        widgets = {
            'control_item': forms.Select(attrs={'class': 'form-select'}),
            'sample_no': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'measured_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'pass_fail': forms.Select(attrs={'class': 'form-select'}),
            'instrument': forms.Select(attrs={'class': 'form-select'}),
            'attachment': forms.FileInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'disposition': forms.Select(attrs={'class': 'form-select'}),
            'disposition_reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'control_item': 'Kontrol Maddesi',
            'sample_no': 'Örnek No',
            'measured_value': 'Ölçülen Değer',
            'pass_fail': 'Sonuç',
            'instrument': 'Kullanılan Ölçü Aleti',
            'attachment': 'Ek Dosya',
            'notes': 'Notlar',
            'disposition': 'Disposition',
            'disposition_reason': 'Disposition Nedeni',
        }
    
    def __init__(self, *args, **kwargs):
        work_order = kwargs.pop('work_order', None)
        operation_step = kwargs.pop('operation_step', None)
        super().__init__(*args, **kwargs)
        
        # Kontrol maddelerini filtrele
        if operation_step:
            recete = work_order.recete if work_order else None
            if recete:
                # ControlPlan'ı bul
                product = recete.urun
                control_plan = ControlPlan.objects.filter(
                    product=product, 
                    status='ACTIVE'
                ).first()
                if control_plan:
                    self.fields['control_item'].queryset = control_plan.items.filter(
                        operation_step=operation_step
                    ).order_by('display_order')
        
        # İsteğe bağlı alanlar
        optional_fields = ['sample_no', 'measured_value', 'instrument', 'attachment', 
                          'notes', 'disposition', 'disposition_reason']
        for field in optional_fields:
            self.fields[field].required = False
        
        # Kalibrasyon geçerli ölçü aletlerini filtrele
        from datetime import date
        self.fields['instrument'].queryset = OlcuAleti.objects.filter(
            aktif=True,
            durum='AKTIF'
        ).exclude(
            sonraki_kalibrasyon_tarihi__lt=date.today()
        ).order_by('seri_no')


class QualityGateForm(forms.ModelForm):
    """Kalite geçidi formu"""
    class Meta:
        model = QualityGate
        fields = ['operation_step', 'gate_type', 'applies_to_critical_only', 'active']
        widgets = {
            'operation_step': forms.Select(attrs={'class': 'form-select'}),
            'gate_type': forms.Select(attrs={'class': 'form-select'}),
            'applies_to_critical_only': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'operation_step': 'Operasyon Adımı',
            'gate_type': 'Geçit Tipi',
            'applies_to_critical_only': 'Sadece Kritik Kontrollere Uygula',
            'active': 'Aktif',
        }


class NonconformanceAutoRuleForm(forms.ModelForm):
    """Uygunsuzluk otomatik kuralı formu"""
    class Meta:
        model = NonconformanceAutoRule
        fields = [
            'name', 'description', 'trigger_type', 'trigger_count',
            'action_type', 'product', 'category', 'default_severity',
            'default_category', 'active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'trigger_type': forms.Select(attrs={'class': 'form-select'}),
            'trigger_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'action_type': forms.Select(attrs={'class': 'form-select'}),
            'product': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'default_severity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5}),
            'default_category': forms.TextInput(attrs={'class': 'form-control'}),
            'active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': 'Kural Adı',
            'description': 'Açıklama',
            'trigger_type': 'Tetikleme Tipi',
            'trigger_count': 'Tetikleme Sayısı',
            'action_type': 'Aksiyon Tipi',
            'product': 'Belirli Ürün',
            'category': 'Belirli Kategori',
            'default_severity': 'Varsayılan Şiddet',
            'default_category': 'Varsayılan Kategori',
            'active': 'Aktif',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = StokItem.objects.filter(arsivli=False).order_by('ad')
        self.fields['category'].queryset = Kategori.objects.all().order_by('ad')
        
        # İsteğe bağlı alanlar
        optional_fields = ['description', 'product', 'category', 'default_category']
        for field in optional_fields:
            self.fields[field].required = False


class KurulumDosyasiForm(forms.ModelForm):
    """Kurulum dosyası formu"""
    class Meta:
        model = KurulumDosyasi
        fields = ['urun', 'urun_parcasi', 'istasyon', 'aciklama', 'versiyon', 'pdf_dosya', 'aktif']
        widgets = {
            'urun': forms.HiddenInput(),  # JavaScript ile doldurulacak
            'urun_parcasi': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Örn: Alt Plaka, Üst Plaka, Yan Duvar',
                'list': 'urun-parcasi-list'
            }),
            'istasyon': forms.Select(attrs={
                'class': 'form-select'
            }),
            'aciklama': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Kurulum dosyası açıklaması...'
            }),
            'versiyon': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Örn: 1.0, 1.1, 2.0'
            }),
            'pdf_dosya': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf'
            }),
            'aktif': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'urun': 'Ürün',
            'urun_parcasi': 'Ürün Parçası',
            'istasyon': 'İstasyon',
            'aciklama': 'Açıklama',
            'versiyon': 'Versiyon',
            'pdf_dosya': 'PDF Dosyası',
            'aktif': 'Aktif',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # İstasyon queryset'i
        if 'istasyon' in self.fields:
            self.fields['istasyon'].queryset = Istasyon.objects.filter(aktif=True).order_by('sira', 'ad')
        
        # İsteğe bağlı alanlar (PDF dosyası dahil — kullanıcı sonradan da yükleyebilir)
        optional_fields = ['istasyon', 'aciklama', 'pdf_dosya']
        for field in optional_fields:
            if field in self.fields:
                self.fields[field].required = False


def suggest_next_cnc_revision_code(program):
    """
    Bu programa ait revizyon kodlarının sonundaki en büyük tam sayıyı bulur,
    bir sonraki sayıyı aynı önek ve sıfır dolgusuyla döndürür (örn. R01 → R02).
    Sonunda sayı yoksa veya hiç revizyon yoksa R01 döner.
    """
    codes = [
        c.strip()
        for c in CncProgramRevision.objects.filter(program=program).values_list(
            'revision_code', flat=True
        )
        if c and str(c).strip()
    ]
    if not codes:
        return 'R01'

    best_num = -1
    best_code = None
    for code in codes:
        m = re.search(r'(\d+)\s*$', code)
        if m:
            n = int(m.group(1))
            if n > best_num:
                best_num = n
                best_code = code

    if best_num < 0 or not best_code:
        return 'R01'

    next_num = best_num + 1
    m = re.match(r'^(.*?)(\d+)\s*$', best_code)
    if not m:
        return f'R{next_num:02d}'
    prefix, old_digits = m.group(1), m.group(2)
    width = len(old_digits)
    if len(str(next_num)) <= width:
        new_suffix = str(next_num).zfill(width)
    else:
        new_suffix = str(next_num)
    return prefix + new_suffix


class CncProgramForm(forms.ModelForm):
    """CNC Program Formu - İlk program tanımıyla birlikte dosya da yüklenebilir"""

    program_file = forms.FileField(
        required=False,
        label='Program Dosyası (.nc veya .txt)',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.nc,.txt'}),
        help_text='İlk revizyon (R01) için yüklenecek dosya. Sadece .nc veya .txt'
    )
    revision_note = forms.CharField(
        required=False,
        label='Revizyon Notu',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Örn: İlk program tanımı'
        }),
        help_text='Yüklenen ilk revizyon için açıklama (opsiyonel)'
    )

    class Meta:
        model = CncProgram
        fields = ['product', 'urun_parcasi', 'machine_type', 'machine_name', 'program_name', 'program_number', 'file_format', 'dosya_konumu', 'status']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select', 'id': 'id_product'}),
            'urun_parcasi': forms.Select(attrs={'class': 'form-select', 'id': 'id_urun_parcasi'}),
            'machine_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_machine_type'}),
            'machine_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: Doosan Lynx, Haas VF2'}),
            'program_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: BD410_TORNA_OP10'}),
            'program_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: O1234'}),
            'file_format': forms.Select(attrs={'class': 'form-select'}),
            'dosya_konumu': forms.Select(attrs={'class': 'form-select', 'id': 'id_dosya_konumu'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'product': 'Ürün',
            'urun_parcasi': 'Ürün Parçası (Reçete Bileşeni)',
            'machine_type': 'Makine Tipi',
            'machine_name': 'Makine Adı',
            'program_name': 'Program Adı',
            'program_number': 'Program Numarası',
            'file_format': 'Dosya Formatı',
            'dosya_konumu': 'Dosya Konumu',
            'status': 'Durum',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ürün queryset'i - sadece URUN tipindeki stoklar
        if 'product' in self.fields:
            self.fields['product'].queryset = StokItem.objects.filter(
                stok_tipi='URUN'
            ).order_by('stok_kodu')

        # Dosya konumu alanı opsiyonel; seçenekler JS ile makine tipine göre AJAX ile dolduruluyor.
        # queryset'i tüm klasörlerle bırakıyoruz ki ModelChoiceField validation'ı geçsin
        # (kullanıcı JS ile farklı bir klasör seçtiğinde de pk geçerli kabul edilsin).
        if 'dosya_konumu' in self.fields:
            self.fields['dosya_konumu'].required = False
            self.fields['dosya_konumu'].empty_label = '— Seçiniz (önce makine tipi seçin) —'

        # Ürün parçası alanı opsiyonel; seçenekler client tarafında AJAX ile dolduruluyor.
        if 'urun_parcasi' in self.fields:
            self.fields['urun_parcasi'].required = False
            # Düzenleme/POST sonrası mevcut değer için widget'a tek choice ekle ki seçili
            # bir option olarak render edilsin (aksi halde Select widget'ında option yok).
            current_val = None
            if self.is_bound:
                current_val = (self.data.get('urun_parcasi') or '').strip()
            elif self.instance and self.instance.pk:
                current_val = (self.instance.urun_parcasi or '').strip()
            choices = [('', '— Seçiniz (önce ürün seçin) —')]
            if current_val:
                choices.append((current_val, current_val))
            self.fields['urun_parcasi'].widget.choices = choices

        # Düzenleme modunda current_revision değiştirilemez
        if self.instance and self.instance.pk:
            if 'current_revision' in self.fields:
                self.fields['current_revision'].widget.attrs['readonly'] = True

            # Düzenleme modunda eğer program zaten bir revizyona sahipse,
            # dosya yükleme alanını gizleyebilmek için bayrak set ediyoruz.
            # (View ve template bu bayrağa göre davranır.)
            try:
                self.has_existing_revisions = self.instance.revisions.exists()
            except Exception:
                self.has_existing_revisions = False
        else:
            self.has_existing_revisions = False

    def clean_program_file(self):
        file = self.cleaned_data.get('program_file')
        if file and hasattr(file, 'name'):
            ext = file.name.split('.')[-1].lower()
            if ext not in ['nc', 'txt']:
                raise ValidationError('Sadece .nc veya .txt dosyaları yüklenebilir.')
        return file


class CncProgramRevisionForm(forms.ModelForm):
    """CNC Program Revizyon Formu"""
    
    class Meta:
        model = CncProgramRevision
        fields = ['revision_code', 'revision_type', 'file_path', 'revision_note', 'is_active']
        widgets = {
            'revision_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: R01, R02'}),
            'revision_type': forms.Select(attrs={'class': 'form-select'}),
            'file_path': forms.FileInput(attrs={'class': 'form-control', 'accept': '.nc,.txt'}),
            'revision_note': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Revizyon değişikliklerini açıklayın...'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'revision_code': 'Revizyon Kodu',
            'revision_type': 'Revizyon Tipi',
            'file_path': 'Program Dosyası (.nc veya .txt)',
            'revision_note': 'Revizyon Notu',
            'is_active': 'Aktif Yap',
        }
    
    def __init__(self, *args, **kwargs):
        self.program = kwargs.pop('program', None)
        super().__init__(*args, **kwargs)

        # UUID pk için model oluşturulur oluşturulmaz pk atanır; "yeni kayıt" için _state.adding kullan.
        is_new_revision = getattr(self.instance._state, 'adding', True)

        # Yeni revizyon eklenirken dosya zorunlu
        if is_new_revision:
            self.fields['file_path'].required = True
        else:
            # Kayıtlı revizyon düzenlenirken dosya zorunlu değil
            self.fields['file_path'].required = False

        # Revizyon notu zorunlu
        self.fields['revision_note'].required = True

        # Yeni revizyon: varsayılan kod = mevcut en yüksek son sayı + 1 (alan düzenlenebilir kalır).
        # ModelForm'da instance boş alanları için fields[].initial yetmez; self.initial kullan.
        if self.program and is_new_revision and not self.is_bound:
            suggested = suggest_next_cnc_revision_code(self.program)
            self.initial['revision_code'] = suggested
            self.fields['revision_code'].initial = suggested
    
    def clean_file_path(self):
        file = self.cleaned_data.get('file_path')
        if file:
            # Dosya uzantısı kontrolü
            if hasattr(file, 'name'):
                ext = file.name.split('.')[-1].lower()
                if ext not in ['nc', 'txt']:
                    raise ValidationError('Sadece .nc veya .txt dosyaları yüklenebilir.')
        return file
    
    def clean_revision_code(self):
        revision_code = self.cleaned_data.get('revision_code')
        if self.program and revision_code:
            # Aynı program için aynı revizyon kodu olmamalı
            existing = CncProgramRevision.objects.filter(
                program=self.program,
                revision_code=revision_code
            )
            if self.instance and self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError(f'Bu revizyon kodu ({revision_code}) bu program için zaten kullanılıyor.')
        return revision_code


class CncEkipmanForm(forms.ModelForm):
    """CNC torna / freze / ortak ekipman tanım formu."""

    class Meta:
        model = CncEkipman
        fields = [
            "machine_scope",
            "ekipman_numarasi",
            "barkod_envanter_no",
            "ad",
            "marka",
            "model_kodu",
            "fotograf",
            "teknik_pdf",
            "aciklama",
            "aktif",
            "sira",
        ]
        widgets = {
            "machine_scope": forms.Select(attrs={"class": "form-select"}),
            "ekipman_numarasi": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Opsiyonel — iç envanter veya takım no."}
            ),
            "barkod_envanter_no": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Barkod veya depo envanter numarası (opsiyonel)"}
            ),
            "ad": forms.TextInput(attrs={"class": "form-control", "placeholder": "Örn: Hidrolik sıkıştırma ünitesi"}),
            "marka": forms.TextInput(attrs={"class": "form-control", "placeholder": "Opsiyonel"}),
            "model_kodu": forms.TextInput(attrs={"class": "form-control", "placeholder": "Opsiyonel"}),
            "fotograf": forms.FileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "teknik_pdf": forms.FileInput(attrs={"class": "form-control", "accept": ".pdf,application/pdf"}),
            "aciklama": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "aktif": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sira": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "1"}),
        }
        labels = {
            "machine_scope": "Kapsam",
            "ekipman_numarasi": "Ekipman numarası",
            "barkod_envanter_no": "Barkod / envanter no",
            "ad": "Ekipman adı",
            "marka": "Marka",
            "model_kodu": "Model",
            "fotograf": "Fotoğraf",
            "teknik_pdf": "Teknik PDF",
            "aciklama": "Açıklama",
            "aktif": "Aktif",
            "sira": "Sıra",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ekipman_numarasi"].required = False
        self.fields["barkod_envanter_no"].required = False
        self.fields["marka"].required = False
        self.fields["model_kodu"].required = False
        self.fields["aciklama"].required = False
        self.fields["fotograf"].required = False
        self.fields["teknik_pdf"].required = False

    def clean_teknik_pdf(self):
        f = self.cleaned_data.get("teknik_pdf")
        if f and getattr(f, "name", ""):
            name = f.name.lower()
            if not name.endswith(".pdf"):
                raise ValidationError("Teknik dosya yalnızca PDF olmalıdır.")
        return f

    def clean_fotograf(self):
        f = self.cleaned_data.get("fotograf")
        if f and getattr(f, "name", ""):
            name = f.name.lower()
            ok = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
            if not any(name.endswith(ext) for ext in ok):
                raise ValidationError("Fotoğraf için yaygın bir görüntü formatı seçin (örn. JPG, PNG).")
        return f


# ============================================================================
# BELGE YÖNETİMİ FORMLARI
# ============================================================================

class DocumentTypeForm(forms.ModelForm):
    """Belge Türü Formu"""

    category = forms.CharField(
        max_length=50,
        label='Kategori',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = DocumentType.get_category_choices()
        self.fields['category'].widget.choices = choices
        posted_category = None
        if self.data:
            posted_category = (self.data.get('category') or '').strip()
        elif self.instance and self.instance.pk:
            posted_category = self.instance.category
        if posted_category and posted_category not in {value for value, _ in choices}:
            self.fields['category'].widget.choices = list(choices) + [(posted_category, posted_category)]

    def _post_clean(self):
        category_field = DocumentType._meta.get_field('category')
        original_choices = category_field.choices
        extended = list(DocumentType.get_category_choices())
        category = self.cleaned_data.get('category')
        if category and category not in {value for value, _ in extended}:
            extended.append((category, category))
        category_field.choices = extended
        try:
            super()._post_clean()
        finally:
            category_field.choices = original_choices
    
    class Meta:
        model = DocumentType
        fields = ['code', 'name', 'category', 'default_risk_level', 'default_reminder_days', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: ISO9001, CE, SGK'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: ISO 9001 Sertifikası'}),
            'default_risk_level': forms.Select(attrs={'class': 'form-select'}),
            'default_reminder_days': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '[90,60,30,7]'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'code': 'Kod',
            'name': 'Ad',
            'category': 'Kategori',
            'default_risk_level': 'Varsayılan Risk Seviyesi',
            'default_reminder_days': 'Varsayılan Hatırlatma Günleri (JSON)',
            'is_active': 'Aktif',
        }

    def clean_category(self):
        category = (self.cleaned_data.get('category') or '').strip()
        if not category:
            raise ValidationError('Kategori boş olamaz.')
        if len(category) > 50:
            raise ValidationError('Kategori en fazla 50 karakter olabilir.')
        return category
    
    def clean_default_reminder_days(self):
        days_str = self.cleaned_data.get('default_reminder_days', '')
        if days_str:
            try:
                import json
                days_list = json.loads(days_str)
                if not isinstance(days_list, list):
                    raise ValidationError('JSON formatı bir liste olmalıdır: [90,60,30,7]')
                if not all(isinstance(x, int) and x > 0 for x in days_list):
                    raise ValidationError('Tüm değerler pozitif tam sayı olmalıdır')
                return days_str
            except json.JSONDecodeError:
                raise ValidationError('Geçersiz JSON formatı. Örnek: [90,60,30,7]')
        return days_str


class DocumentForm(forms.ModelForm):
    """Belge Formu"""
    
    class Meta:
        model = Document
        fields = [
            'type', 'title', 'issuer_authority', 'issue_date', 'valid_from', 'valid_until',
            'description', 'document_no', 'risk_level', 'owner_user', 'department',
            'confidentiality', 'requires_original', 'storage_location', 'renewal_required',
            'renewal_lead_days', 'tags', 'notes_internal'
        ]
        widgets = {
            'type': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'issuer_authority': forms.TextInput(attrs={'class': 'form-control'}),
            'issue_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'valid_from': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'valid_until': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'document_no': forms.TextInput(attrs={'class': 'form-control'}),
            'risk_level': forms.Select(attrs={'class': 'form-select'}),
            'owner_user': forms.Select(attrs={'class': 'form-select'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
            'confidentiality': forms.Select(attrs={'class': 'form-select'}),
            'requires_original': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'storage_location': forms.TextInput(attrs={'class': 'form-control'}),
            'renewal_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'renewal_lead_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'tags': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Virgülle ayrılmış etiketler'}),
            'notes_internal': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Belge türü queryset - sadece aktif türler
        if 'type' in self.fields:
            self.fields['type'].queryset = DocumentType.objects.filter(is_active=True)
        
        # Owner user queryset
        if 'owner_user' in self.fields:
            self.fields['owner_user'].queryset = User.objects.filter(is_active=True).order_by('username')
        
        # Düzenleme modunda status görünmez (otomatik hesaplanır)
        if self.instance and self.instance.pk:
            # Status readonly yapılabilir veya gizlenebilir
            pass


class DocumentFileForm(forms.ModelForm):
    """Belge Dosyası Formu (Yeni Versiyon)"""
    
    class Meta:
        model = DocumentFile
        fields = ['file', 'change_note']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'}),
            'change_note': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Bu versiyon için değişiklik notunu girin...'}),
        }
        labels = {
            'file': 'Dosya',
            'change_note': 'Değişiklik Notu',
        }
    
    def __init__(self, *args, **kwargs):
        self.document = kwargs.pop('document', None)
        super().__init__(*args, **kwargs)
    
    def clean_change_note(self):
        change_note = self.cleaned_data.get('change_note', '')
        if self.document:
            # Eğer versiyon > 1 ise change_note zorunlu
            existing_files = self.document.files.filter(is_deleted=False).count()
            if existing_files > 0 and len(change_note.strip()) < 5:
                raise ValidationError('Yeni versiyon için değişiklik notu en az 5 karakter olmalıdır.')
        return change_note


class DocumentRenewalForm(forms.ModelForm):
    """Belge Yenileme Formu"""
    
    class Meta:
        model = DocumentRenewal
        fields = ['renewal_due_date', 'external_reference', 'notes', 'status']
        widgets = {
            'renewal_due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'external_reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Başvuru no / e-devlet takip no'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'renewal_due_date': 'Hedef Tarih',
            'external_reference': 'Dış Referans',
            'notes': 'Notlar',
            'status': 'Durum',
        }


class GelistirmeTalepForm(forms.ModelForm):
    class Meta:
        model = GelistirmeTalebi
        fields = ['baslik', 'aciklama']
        widgets = {
            'baslik': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Talep başlığı'}),
            'aciklama': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Talep açıklaması'}),
        }
