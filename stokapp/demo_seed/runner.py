"""Tüm modüller için demo sunum verisi oluşturur."""

from __future__ import annotations

import random
from decimal import Decimal

from django.db import transaction

from stokapp.demo_seed.helpers import (
    DEMO_MARKER,
    code,
    d,
    demo_nc,
    demo_pdf,
    dt,
    get_seed_user,
    log_created,
    money,
    pick,
)
from stokapp.models import (
    AlertRule,
    ArGeProje,
    Arac,
    AracBelgesi,
    AracBelgeTuru,
    AylikOdeme,
    AvansOdeme,
    BankaHesabi,
    Birim,
    Cari,
    Complaint,
    CapaAction,
    ControlItem,
    ControlPlan,
    Depo,
    DisOperasyon,
    DisOperasyonTipi,
    Document,
    DocumentType,
    EcoChange,
    Ekipman,
    Fikstur,
    Gayrimenkul,
    GelistirmeTalebi,
    GunlukCalisma,
    Istasyon,
    Kategori,
    KrediKarti,
    KurulumDosyasi,
    Musteri,
    MusteriIlgiliKisi,
    OlcuAleti,
    OlcuAletiTuru,
    Operasyon,
    ParaBirimi,
    Personel,
    PersonelBelgesi,
    Raf,
    Recete,
    ReceteDetay,
    ReceteOperasyon,
    Satinalma,
    SatinalmaKalemi,
    Sigorta,
    Siparis,
    SiparisKalemi,
    StokItem,
    StokHareketi,
    Talep,
    TalepKalemi,
    Tedarikci,
    TedarikciIlgiliKisi,
    Teklif,
    TeklifKalemi,
    TeklifTalebi,
    TeklifTalebiKalemi,
    TeklifTalebiTedarikci,
    UretimEmri,
    UretimStandarti,
    CncProgram,
    CncProgramRevision,
)


class DemoSeeder:
    def __init__(self, count: int = 4, stdout=None, style=None):
        self.count = max(1, min(count, 10))
        self.stdout = stdout
        self.style = style
        self.user = None
        self.ctx = {}

    def _log(self, label, created, skipped=0):
        if self.stdout and self.style:
            log_created(self.stdout, self.style, label, created, skipped)

    def run(self):
        random.seed(42)
        with transaction.atomic():
            self.user = get_seed_user()
            if not self.user:
                raise RuntimeError('Seed için en az bir kullanıcı gerekli (admin).')
            self._seed_foundation()
            self._seed_partners()
            self._seed_stok()
            self._seed_production_masters()
            self._seed_hr()
            self._seed_finance()
            self._seed_assets()
            self._seed_documents()
            self._seed_commercial()
            self._seed_production_flow()
            self._seed_quality()
            self._seed_arge_misc()
            self._seed_extras()
        return self.ctx

    def _seed_foundation(self):
        n = 0
        birim_data = ['Adet', 'Kg', 'Metre', 'Takım']
        for i, ad in enumerate(birim_data[: self.count], 1):
            _, c = Birim.objects.get_or_create(ad=ad)
            n += c
        self._log('Birim', n)

        n = 0
        pb_data = [
            ('TL', 'Türk Lirası', '₺'),
            ('USD', 'Amerikan Doları', '$'),
            ('EUR', 'Euro', '€'),
            ('GBP', 'İngiliz Sterlini', '£'),
        ]
        paralar = []
        for i, (kod, ad, sembol) in enumerate(pb_data[: self.count], 1):
            obj, c = ParaBirimi.objects.get_or_create(
                kod=kod, defaults={'ad': ad, 'sembol': sembol, 'aktif': True}
            )
            paralar.append(obj)
            n += c
        self.ctx['paralar'] = paralar
        self._log('Para Birimi', n)

        n = 0
        kat_data = [
            ('CNC Parçalar', 'URUN'),
            ('Alüminyum Hammadde', 'HAM_MADDE'),
            ('Kaplama Kimyasalları', 'HAM_MADDE'),
            ('Montaj Setleri', 'YARI_MAMUL'),
        ]
        kategoriler = []
        for i, (ad, tip) in enumerate(kat_data[: self.count], 1):
            obj, c = Kategori.objects.get_or_create(
                ad=f'{DEMO_MARKER} {ad}',
                defaults={'stok_tipi': tip, 'aciklama': f'Demo kategori — {ad}'},
            )
            kategoriler.append(obj)
            n += c
        self.ctx['kategoriler'] = kategoriler
        self._log('Kategori', n)

        n = 0
        depo_data = ['Ana Depo', 'Üretim Hattı', 'Hammadde Ambarı', 'Sevk Alanı']
        depolar = []
        for i, ad in enumerate(depo_data[: self.count], 1):
            obj, c = Depo.objects.get_or_create(ad=f'{DEMO_MARKER} {ad}')
            depolar.append(obj)
            n += c
        self.ctx['depolar'] = depolar
        self._log('Depo', n)

        n = 0
        raflar = []
        for i, depo in enumerate(depolar, 1):
            obj, c = Raf.objects.get_or_create(
                depo=depo, ad=f'Raf-{i:02d}', defaults={}
            )
            raflar.append(obj)
            n += c
        self.ctx['raflar'] = raflar
        self._log('Raf', n)

    def _seed_partners(self):
        n = 0
        ted_data = [
            ('Demir Çelik San. A.Ş.', '0212 555 0101', 'satis@demircelik.demo'),
            ('Kaplama Proses Ltd.', '0262 555 0202', 'info@kaplama.demo'),
            ('CNC Takım Tedarik', '0312 555 0303', 'siparis@cnctakim.demo'),
            ('Lojistik Express', '0232 555 0404', 'kargo@express.demo'),
        ]
        tedarikciler = []
        for i, (ad, tel, email) in enumerate(ted_data[: self.count], 1):
            obj, c = Tedarikci.objects.get_or_create(
                ad=f'{DEMO_MARKER} {ad}',
                defaults={
                    'telefon': tel,
                    'email': email,
                    'adres': f'Organize Sanayi Bölgesi No:{i}, İstanbul',
                    'aktif': True,
                },
            )
            if self.ctx.get('kategoriler'):
                obj.kategoriler.set(self.ctx['kategoriler'][: min(2, len(self.ctx['kategoriler']))])
            tedarikciler.append(obj)
            n += c
            TedarikciIlgiliKisi.objects.get_or_create(
                tedarikci=obj,
                ad_soyad=f'{DEMO_MARKER} Yetkili {i}',
                defaults={
                    'gorev': 'Satış Temsilcisi',
                    'telefon': tel,
                    'email': email,
                    'sira': 0,
                },
            )
        self.ctx['tedarikciler'] = tedarikciler
        self._log('Tedarikçi', n)

        n = 0
        mus_data = [
            ('Teknoloji Makina San.', '0216 555 1101', 'satinalma@teknomak.demo'),
            ('Otomotiv Yan Sanayi A.Ş.', '0224 555 1102', 'uretim@oto.demo'),
            ('Savunma Sistemleri Ltd.', '0312 555 1103', 'tedarik@savunma.demo'),
            ('Enerji Ekipmanları A.Ş.', '0232 555 1104', 'proje@enerji.demo'),
        ]
        musteriler = []
        for i, (ad, tel, email) in enumerate(mus_data[: self.count], 1):
            obj, c = Musteri.objects.get_or_create(
                ad=f'{DEMO_MARKER} {ad}',
                defaults={
                    'telefon': tel,
                    'email': email,
                    'adres': f'Teknopark Cad. No:{i * 10}, Türkiye',
                },
            )
            if self.ctx.get('kategoriler'):
                obj.kategoriler.set(self.ctx['kategoriler'][: min(2, len(self.ctx['kategoriler']))])
            musteriler.append(obj)
            n += c
            MusteriIlgiliKisi.objects.get_or_create(
                musteri=obj,
                ad_soyad=f'{DEMO_MARKER} İlgili {i}',
                defaults={
                    'gorev': 'Satın Alma Müdürü',
                    'telefon': tel,
                    'email': email,
                    'sira': 0,
                },
            )
        self.ctx['musteriler'] = musteriler
        self._log('Müşteri', n)

        n = 0
        for i, musteri in enumerate(musteriler, 1):
            _, c = Cari.objects.get_or_create(
                cari_kodu=code('CAR-M', i),
                defaults={
                    'unvan': musteri.ad,
                    'cari_tipi': 'MUSTERI',
                    'telefon': musteri.telefon,
                    'email': musteri.email,
                    'adres': musteri.adres,
                    'aktif': True,
                },
            )
            n += c
        for i, ted in enumerate(tedarikciler, 1):
            _, c = Cari.objects.get_or_create(
                cari_kodu=code('CAR-T', i),
                defaults={
                    'unvan': ted.ad,
                    'cari_tipi': 'TEDARIKCI',
                    'telefon': ted.telefon,
                    'email': ted.email,
                    'adres': ted.adres,
                    'aktif': True,
                },
            )
            n += c
        self._log('Cari', n)

    def _seed_stok(self):
        n = 0
        stok_specs = [
            ('HM-AL6061', '6061 Alüminyum Blok', 'HAM_MADDE', 'URETIM', 'BILESEN', 850, 120),
            ('UR-BD410', 'BD410 Gövde Parçası', 'URUN', 'URETIM', 'NIHAI_URUN', 4200, 45),
            ('YM-KAP01', 'Kaplama Öncesi Yarı Mamul', 'YARI_MAMUL', 'URETIM', 'BILESEN', 1800, 28),
            ('UR-M8SET', 'M8 Civata Seti', 'URUN', 'SATINAL', 'AL_SAT', 45, 500),
        ]
        stoklar = []
        kategoriler = self.ctx.get('kategoriler', [])
        tedarikciler = self.ctx.get('tedarikciler', [])
        depolar = self.ctx.get('depolar', [])
        raflar = self.ctx.get('raflar', [])
        for i, (sk, ad, tip, urun_tipi, rol, fiyat, miktar) in enumerate(stok_specs[: self.count], 1):
            obj, c = StokItem.objects.get_or_create(
                stok_kodu=code(sk.replace('-', ''), i),
                defaults={
                    'ad': f'{DEMO_MARKER} {ad}',
                    'aciklama': f'Demo stok kartı — {ad}',
                    'kategori': kategoriler[(i - 1) % len(kategoriler)] if kategoriler else Kategori.objects.first(),
                    'tedarikci': tedarikciler[(i - 1) % len(tedarikciler)] if tedarikciler else None,
                    'birim': pick(['Adet', 'Kg', 'Metre']),
                    'alis_fiyati': Decimal(str(fiyat)),
                    'satis_fiyati': Decimal(str(int(fiyat * 1.35))),
                    'mevcut_miktar': Decimal(str(miktar)),
                    'minimum_stok': Decimal('5'),
                    'stok_tipi': tip,
                    'urun_tipi': urun_tipi,
                    'urun_rolu': rol,
                    'depo': depolar[(i - 1) % len(depolar)] if depolar else None,
                    'raf': raflar[(i - 1) % len(raflar)] if raflar else None,
                },
            )
            stoklar.append(obj)
            n += c
        self.ctx['stoklar'] = stoklar
        self._log('Stok Kartı', n)

    def _seed_production_masters(self):
        n = 0
        ops = ['CNC Torna', 'CNC Freze', 'Kaplama', 'Montaj', 'Kalite Kontrol']
        operasyonlar = []
        for i, ad in enumerate(ops[: self.count], 1):
            obj, c = Operasyon.objects.get_or_create(
                ad=f'{DEMO_MARKER} {ad}',
                defaults={'aciklama': f'Demo operasyon — {ad}', 'aktif': True, 'sira': i},
            )
            operasyonlar.append(obj)
            n += c
        self.ctx['operasyonlar'] = operasyonlar
        self._log('Operasyon', n)

        n = 0
        ist_data = [
            ('CNC Torna 1', 'cnc_lathe'),
            ('CNC Freze 1', 'cnc_mill'),
            ('Montaj Tezgahı', ''),
            ('Kalite Masası', ''),
        ]
        istasyonlar = []
        for i, (ad, grp) in enumerate(ist_data[: self.count], 1):
            obj, c = Istasyon.objects.get_or_create(
                ad=f'{DEMO_MARKER} {ad}',
                defaults={
                    'aciklama': f'Demo istasyon — {ad}',
                    'aktif': True,
                    'sira': i,
                    'cnc_makine_grubu': grp,
                    'maliyet': money(200, 450),
                },
            )
            istasyonlar.append(obj)
            n += c
        self.ctx['istasyonlar'] = istasyonlar
        self._log('İstasyon', n)

        n = 0
        ekipmanlar = []
        for i in range(1, self.count + 1):
            obj, c = Ekipman.objects.get_or_create(
                ekipman_numarasi=code('EKP', i),
                defaults={
                    'ad': f'{DEMO_MARKER} Hidrolik Pres {i}',
                    'aciklama': 'Demo ekipman kaydı',
                },
            )
            ekipmanlar.append(obj)
            n += c
        self.ctx['ekipmanlar'] = ekipmanlar
        self._log('Ekipman', n)

        n = 0
        for i in range(1, self.count + 1):
            _, c = Fikstur.objects.get_or_create(
                fikstur_numarasi=code('FIX', i),
                defaults={
                    'ad': f'{DEMO_MARKER} Torna Fikstürü {i}',
                    'depo': self.ctx['depolar'][(i - 1) % len(self.ctx['depolar'])] if self.ctx.get('depolar') else None,
                },
            )
            n += c
        self._log('Fikstür', n)

        n = 0
        tur_adlari = ['Kumpas', 'Mikrometre', 'Kalınlık Ölçer', 'Pürüzlülük Ölçer']
        turler = []
        for i, ad in enumerate(tur_adlari[: self.count], 1):
            obj, c = OlcuAletiTuru.objects.get_or_create(ad=f'{DEMO_MARKER} {ad}')
            turler.append(obj)
            n += c
        n2 = 0
        markalar = ['Mitutoyo', 'Baker', 'Elcometer', 'Haff']
        for i in range(1, self.count + 1):
            _, c = OlcuAleti.objects.get_or_create(
                seri_no=code('SN', i),
                defaults={
                    'marka': markalar[(i - 1) % len(markalar)],
                    'model': f'Model-{i}',
                    'device_type': pick(['digital_caliper', 'outside_micrometer', 'coating_thickness_gauge']),
                    'alet_turu': turler[(i - 1) % len(turler)] if turler else None,
                    'status': 'active' if i < self.count else 'blocked',
                    'department': 'Kalite',
                },
            )
            n2 += c
        self._log('Ölçü Aleti Türü', n)
        self._log('Ölçü Aleti', n2)

    def _seed_hr(self):
        n = 0
        personeller = []
        pers_data = [
            ('Ahmet', 'Yılmaz', 'CNC Operatörü', 380),
            ('Mehmet', 'Kaya', 'Torna Ustası', 420),
            ('Ayşe', 'Demir', 'Kalite Kontrol', 360),
            ('Fatma', 'Öz', 'Depo Sorumlusu', 340),
        ]
        for i, (ad, soyad, gorev, ucret) in enumerate(pers_data[: self.count], 1):
            obj, c = Personel.objects.get_or_create(
                personel_no=code('PRS', i),
                defaults={
                    'ad': ad,
                    'soyad': soyad,
                    'gorev': gorev,
                    'unvan': gorev,
                    'telefon': f'0532 555 {1000 + i}',
                    'email': f'{ad.lower()}.{soyad.lower()}@tekos.demo',
                    'saatlik_ucret': Decimal(str(ucret)),
                    'sehir': pick(['İstanbul', 'Kocaeli', 'Ankara', 'İzmir']),
                    'aktif': True,
                },
            )
            personeller.append(obj)
            n += c
        self.ctx['personeller'] = personeller
        self._log('Personel', n)

        n = 0
        belgeler = ['İş Sağlığı Sertifikası', 'MYK CNC Belgesi', 'SRC 2 Ehliyet', 'İşe Giriş Raporu']
        for i, p in enumerate(personeller, 1):
            _, c = PersonelBelgesi.objects.get_or_create(
                personel=p,
                belge_adi=f'{DEMO_MARKER} {belgeler[(i - 1) % len(belgeler)]}',
                defaults={'yenileme_gerekli': i % 2 == 0},
            )
            n += c
        self._log('Personel Belgesi', n)

        n = 0
        for i, p in enumerate(personeller, 1):
            _, c = GunlukCalisma.objects.get_or_create(
                personel=p,
                tarih=d(i),
                defaults={
                    'calisma_suresi': Decimal(str(pick([6, 7.5, 8, 9, 10]))),
                    'saat_ucreti': p.saatlik_ucret or Decimal('350'),
                },
            )
            n += c
        self._log('Günlük Çalışma', n)

        n = 0
        for i, p in enumerate(personeller, 1):
            _, c = AvansOdeme.objects.get_or_create(
                personel=p,
                tarih=d(i + 5),
                tutar=money(1500, 6000),
                defaults={'aciklama': f'{DEMO_MARKER} avans ödemesi'},
            )
            n += c
        self._log('Avans Ödeme', n)

    def _seed_finance(self):
        n = 0
        bankalar = []
        bank_data = [
            ('Ziraat Bankası', 'TR330006100519786457841326'),
            ('Garanti BBVA', 'TR660006200519786457841327'),
            ('İş Bankası', 'TR440006400519786457841328'),
            ('Yapı Kredi', 'TR460006700519786457841329'),
        ]
        for i, (banka, iban) in enumerate(bank_data[: self.count], 1):
            obj, c = BankaHesabi.objects.get_or_create(
                iban=iban,
                defaults={
                    'hesap_adi': f'{DEMO_MARKER} Ana Hesap {i}',
                    'banka_adi': banka,
                    'hesap_tipi': 'TICARI',
                    'para_birimi': 'TL',
                    'aktif': True,
                },
            )
            bankalar.append(obj)
            n += c
        self.ctx['bankalar'] = bankalar
        self._log('Banka Hesabı', n)

        n = 0
        kartlar = []
        for i in range(1, self.count + 1):
            obj, c = KrediKarti.objects.get_or_create(
                kart_adi=f'{DEMO_MARKER} Şirket Kartı {i}',
                defaults={
                    'kart_numarasi': f'4508 0300 0000 {1000 + i}',
                    'son_kullanim_tarihi': '12/28',
                    'cvv': '123',
                    'banka_adi': pick(['Garanti', 'Yapı Kredi', 'Akbank']),
                    'aktif': True,
                },
            )
            kartlar.append(obj)
            n += c
        self.ctx['kartlar'] = kartlar
        self._log('Kredi Kartı', n)

        n = 0
        odeme_data = [
            ('Fabrika kirası', 'HAVALE_EFT', 'banka'),
            ('Elektrik faturası', 'BANKA_HESABI', 'banka'),
            ('Bulut sunucu aboneliği', 'KREDI_KARTI', 'kart'),
            ('SGK primi', 'HAVALE_EFT', 'banka'),
        ]
        for i, (aciklama, sekli, tip) in enumerate(odeme_data[: self.count], 1):
            _, c = AylikOdeme.objects.get_or_create(
                odeme_aciklamasi=f'{DEMO_MARKER} {aciklama}',
                odeme_tarihi=d(-i * 3),
                defaults={
                    'odeme_sekli': sekli,
                    'kayit_tarihi': d(i * 2),
                    'tutar': money(2500, 85000),
                    'para_birimi': self.ctx['paralar'][0] if self.ctx.get('paralar') else None,
                    'banka_hesabi': bankalar[(i - 1) % len(bankalar)] if tip == 'banka' and bankalar else None,
                    'kredi_karti': kartlar[(i - 1) % len(kartlar)] if tip == 'kart' and kartlar else None,
                    'tekrar_eden': i <= 2,
                    'odeme_durumu': pick(['BEKLEMEDE', 'ODENDI']),
                },
            )
            n += c
        self._log('Aylık Ödeme', n)

    def _seed_assets(self):
        n = 0
        araclar = []
        arac_data = [
            ('34 TEK 01', 'Ford', 'Transit', 2022),
            ('34 TEK 02', 'Renault', 'Megane', 2020),
            ('34 TEK 03', 'Fiat', 'Doblo', 2021),
            ('34 TEK 04', 'Mercedes', 'Sprinter', 2023),
        ]
        for i, (plaka, marka, model, yil) in enumerate(arac_data[: self.count], 1):
            obj, c = Arac.objects.get_or_create(
                plaka=plaka,
                defaults={
                    'marka': marka,
                    'model': model,
                    'yil': yil,
                    'arac_tipi': pick(['BINEK', 'TICARI']),
                    'renk': pick(['Beyaz', 'Gri', 'Mavi', 'Siyah']),
                    'aktif': True,
                },
            )
            araclar.append(obj)
            n += c
        self.ctx['araclar'] = araclar
        self._log('Araç', n)

        tur = AracBelgeTuru.objects.first()
        if tur and araclar:
            n = 0
            for i, arac in enumerate(araclar, 1):
                _, c = AracBelgesi.objects.get_or_create(
                    arac=arac,
                    belge_turu=tur,
                    defaults={
                        'gecerlilik_baslangic': d(365),
                        'gecerlilik_bitis': d(-30 * i),
                        'belge_no': code('AB', i),
                    },
                )
                n += c
            self._log('Araç Belgesi', n)

        n = 0
        gm_data = [
            ('Üretim Fabrikası', 'FABRIKA', 'İstanbul', 'Tuzla'),
            ('Depo Alanı B', 'DEPO', 'Kocaeli', 'Gebze'),
            ('Merkez Ofis', 'OFIS', 'İstanbul', 'Ataşehir'),
            ('Ankara Şube', 'OFIS', 'Ankara', 'Ostim'),
        ]
        for i, (ad, tip, il, ilce) in enumerate(gm_data[: self.count], 1):
            _, c = Gayrimenkul.objects.get_or_create(
                ad=f'{DEMO_MARKER} {ad}',
                il=il,
                ilce=ilce,
                defaults={
                    'tip': tip,
                    'adres': f'{ilce} OSB Cad. No:{i * 5}, {il}',
                    'metrekare': Decimal(str(random.randint(120, 4500))),
                    'sahiplik_tipi': pick(['SAHIP', 'KIRALIK']),
                    'alis_veya_kira_bedeli': money(15000, 250000),
                },
            )
            n += c
        self._log('Gayrimenkul', n)

        n = 0
        sig_data = [
            ('Fabrika Binası', 'Allianz Sigorta'),
            ('İş Makinesi Filosu', 'Anadolu Sigorta'),
            ('Depo Yangın Poliçesi', 'HDI Sigorta'),
            ('Grup Hayat Sigortası', 'Mapfre'),
        ]
        for i, (varlik, firma) in enumerate(sig_data[: self.count], 1):
            _, c = Sigorta.objects.get_or_create(
                police_no=code('POL', i),
                defaults={
                    'varlik_adi': f'{DEMO_MARKER} {varlik}',
                    'varlik_kimlik_no': f'VN-{1000 + i}',
                    'varlik_turu': pick(['SIRKET', 'KISISEL']),
                    'police_baslangic_tarihi': d(180),
                    'police_bitis_tarihi': d(-60 + i * 10),
                    'police_duzenleyen_firma': firma,
                    'police_prim_bedeli': money(8000, 45000),
                    'odeme_hesap_kart': f'{DEMO_MARKER} Kurumsal Kart',
                },
            )
            n += c
        self._log('Sigorta', n)

    def _seed_documents(self):
        n = 0
        types = []
        type_data = [
            ('ISO9001', 'ISO 9001 Sertifikası', 'Sertifika'),
            ('CE-UYG', 'CE Uygunluk Belgesi', 'Uygunluk'),
            ('SGK-ISY', 'SGK İşyeri Tescili', 'İzin'),
            ('YANGIN-R', 'Yangın Güvenlik Raporu', 'Ruhsat'),
        ]
        for i, (c, name, cat) in enumerate(type_data[: self.count], 1):
            obj, c_created = DocumentType.objects.get_or_create(
                code=code('DT', i),
                defaults={
                    'name': f'{DEMO_MARKER} {name}',
                    'category': cat,
                    'default_risk_level': pick(['LOW', 'MEDIUM', 'HIGH']),
                    'is_active': True,
                },
            )
            types.append(obj)
            n += c_created
        self._log('Belge Türü', n)

        n = 0
        issuers = ['TSE', 'SGK', 'İtfaiye Müdürlüğü', 'Belediye']
        for i, dt_obj in enumerate(types, 1):
            _, c = Document.objects.get_or_create(
                title=f'{DEMO_MARKER} {dt_obj.name} 2026',
                type=dt_obj,
                defaults={
                    'issuer_authority': issuers[(i - 1) % len(issuers)],
                    'issue_date': d(90 + i * 10),
                    'valid_from': d(90),
                    'valid_until': d(-120 + i * 15),
                    'document_no': code('DOC', i),
                    'created_by': self.user,
                    'owner_user': self.user,
                    'department': pick(['Kalite', 'İK', 'Üretim', 'Hukuk']),
                    'tags': 'demo,sunum,tekos',
                },
            )
            n += c
        self._log('Belge', n)

    def _seed_commercial(self):
        musteriler = self.ctx.get('musteriler', [])
        stoklar = self.ctx.get('stoklar', [])
        tedarikciler = self.ctx.get('tedarikciler', [])
        if not musteriler or not stoklar:
            return

        n = 0
        teklifler = []
        durumlar = ['draft', 'sent', 'accepted', 'rejected']
        for i, musteri in enumerate(musteriler, 1):
            obj, c = Teklif.objects.get_or_create(
                teklif_no=code('TKF', i),
                defaults={
                    'ad': f'{DEMO_MARKER} Teklif — {musteri.ad}',
                    'musteri': musteri,
                    'musteri_adi': musteri.ad,
                    'duzenleme_tarihi': d(i * 5),
                    'vade_tarihi': d(-30),
                    'durum': durumlar[(i - 1) % len(durumlar)],
                    'toplam_tutar': money(25000, 350000),
                    'para_birimi': pick(['TRY', 'USD', 'EUR']),
                    'olusturan': self.user,
                },
            )
            teklifler.append(obj)
            n += c
            if c or not obj.kalemler.exists():
                TeklifKalemi.objects.get_or_create(
                    teklif=obj,
                    sira=1,
                    defaults={
                        'tip': 'product',
                        'stok_item': stoklar[(i - 1) % len(stoklar)],
                        'miktar': Decimal(str(random.randint(5, 100))),
                        'birim_fiyat': money(500, 5000),
                        'aciklama': f'{DEMO_MARKER} teklif kalemi',
                    },
                )
        self.ctx['teklifler'] = teklifler
        self._log('Teklif', n)

        n = 0
        siparisler = []
        sip_durum = ['ONAY_BEKLIYOR', 'ONAYLANDI', 'TESLIM_EDILDI', 'ONAY_BEKLIYOR']
        for i, musteri in enumerate(musteriler, 1):
            toplam = money(40000, 280000)
            obj, c = Siparis.objects.get_or_create(
                siparis_numarasi=code('SO', i),
                defaults={
                    'musteri': musteri,
                    'toplam': toplam,
                    'para_birimi': pick(['TRY', 'USD']),
                    'olusturulma_tarihi': d(i * 3),
                    'tamamlanma_tarihi': d(-15) if i % 2 == 0 else None,
                    'siparis_durumu': sip_durum[(i - 1) % len(sip_durum)],
                    'uretim_durumu': pick(['BEKLEMEDE', 'DEVAM_EDIYOR', 'TAMAMLANDI']),
                    'etiketler': 'demo,sunum',
                },
            )
            siparisler.append(obj)
            n += c
            if c or not obj.kalemler.exists():
                bf = money(800, 8000)
                mk = Decimal(str(random.randint(10, 80)))
                SiparisKalemi.objects.bulk_create([
                    SiparisKalemi(
                        siparis=obj,
                        stok_item=stoklar[(i - 1) % len(stoklar)],
                        miktar=mk,
                        birim_fiyat=bf,
                        toplam=mk * bf,
                        indirim_yuzdesi=Decimal('0'),
                        aciklama=f'{DEMO_MARKER} sipariş kalemi',
                    )
                ])
        self.ctx['siparisler'] = siparisler
        self._log('Sipariş', n)

        n = 0
        for i, ted in enumerate(tedarikciler, 1):
            obj, c = Satinalma.objects.get_or_create(
                satinalma_numarasi=code('SAT', i),
                defaults={
                    'tedarikci': ted,
                    'olusturulma_tarihi': d(i * 4),
                    'toplam': money(5000, 95000),
                    'para_birimi': 'TRY',
                    'lokasyon': self.ctx['depolar'][0] if self.ctx.get('depolar') else None,
                    'teslim_durumu': pick(['BEKLIYOR', 'KISMI_TESLIM', 'TESLIM_ALINDI']),
                    'notlar': f'{DEMO_MARKER} satın alma kaydı',
                },
            )
            n += c
            if c or not obj.kalemler.exists():
                bf = money(50, 1200)
                mk = Decimal(str(random.randint(5, 200)))
                ara = mk * bf
                SatinalmaKalemi.objects.bulk_create([
                    SatinalmaKalemi(
                        satinalma=obj,
                        stok_item=stoklar[(i - 1) % len(stoklar)],
                        miktar=mk,
                        birim_fiyat=bf,
                        vergi_yuzdesi=Decimal('20'),
                        toplam_fiyat=ara * Decimal('1.2'),
                    )
                ])
        self._log('Satın Alma', n)

        n = 0
        talepler = []
        basliklar = [
            'CNC kesici uç ihtiyacı',
            'Hidrolik yağ filtresi talebi',
            'Ofis yazıcı kartuşu',
            'Acil yedek parça — rulman seti',
        ]
        for i, baslik in enumerate(basliklar[: self.count], 1):
            obj, c = Talep.objects.get_or_create(
                baslik=f'{DEMO_MARKER} {baslik}',
                talep_eden=self.user,
                talep_tarihi=d(i * 2),
                defaults={
                    'departman': pick(['Üretim', 'Bakım', 'Ofis', 'Kalite']),
                    'kategori': pick(['SARF', 'URETIM_MALZ', 'YEDEK_PARCA', 'OFIS']),
                    'oncelik': pick(['NORMAL', 'ACIL', 'DUSUK']),
                    'durum': pick(['YENI', 'INCELEMEDE', 'ONAYLANDI']),
                    'aciklama': f'Demo talep açıklaması — {baslik}',
                },
            )
            talepler.append(obj)
            n += c
            if c or not obj.kalemler.exists():
                TalepKalemi.objects.get_or_create(
                    talep=obj,
                    kalem_adi=f'{DEMO_MARKER} {baslik}',
                    defaults={
                        'miktar': Decimal(str(random.randint(1, 50))),
                        'aciklama': f'Demo talep kalemi — {baslik}',
                    },
                )
        self.ctx['talepler'] = talepler
        self._log('Talep', n)

        n = 0
        rfq_baslik = [
            '6061 alüminyum blok fiyat talebi',
            'Kaplama hizmeti RFQ',
            'CNC takım teklif talebi',
            'Hidrolik pompa yedek parça',
        ]
        for i, baslik in enumerate(rfq_baslik[: self.count], 1):
            obj, c = TeklifTalebi.objects.get_or_create(
                baslik=f'{DEMO_MARKER} {baslik}',
                olusturma_tarihi=d(i),
                defaults={
                    'durum': pick(['TASLAK', 'TEKLIF_BEKLENIYOR', 'DEGERLENDIRMEDE']),
                    'oncelik': pick(['FIYAT', 'TERMIN']),
                    'olusturan': self.user,
                    'son_teklif_tarihi': d(-14),
                    'notlar': 'Demo RFQ kaydı',
                },
            )
            n += c
            if c or not obj.kalemler.exists():
                TeklifTalebiKalemi.objects.get_or_create(
                    rfq=obj,
                    kalem_adi=baslik,
                    defaults={
                        'miktar': Decimal(str(random.randint(10, 500))),
                        'birim': pick(['Adet', 'Kg']),
                    },
                )
            if tedarikciler:
                TeklifTalebiTedarikci.objects.get_or_create(
                    rfq=obj,
                    tedarikci=tedarikciler[(i - 1) % len(tedarikciler)],
                )
        self._log('Teklif Talebi (RFQ)', n)

    def _seed_production_flow(self):
        stoklar = self.ctx.get('stoklar', [])
        if not stoklar:
            return
        urun = next((s for s in stoklar if s.stok_tipi == 'URUN'), stoklar[0])
        hammadde = next((s for s in stoklar if s.stok_tipi == 'HAM_MADDE'), stoklar[0])

        n = 0
        receteler = []
        for i in range(1, self.count + 1):
            st = stoklar[(i - 1) % len(stoklar)]
            obj, c = Recete.objects.get_or_create(
                urun=st,
                versiyon=f'1.{i - 1}',
                defaults={'aktif': True, 'aciklama': f'{DEMO_MARKER} reçete'},
            )
            receteler.append(obj)
            n += c
            if c or not obj.detaylar.exists():
                ReceteDetay.objects.get_or_create(
                    recete=obj,
                    stok_item=hammadde,
                    defaults={'miktar': Decimal('1'), 'birim': 'Kg'},
                )
        self.ctx['receteler'] = receteler
        self._log('Reçete', n)

        ops = self.ctx.get('operasyonlar', [])
        istasyonlar = self.ctx.get('istasyonlar', [])
        if receteler and ops:
            n = 0
            for i, rec in enumerate(receteler, 1):
                _, c = ReceteOperasyon.objects.get_or_create(
                    recete=rec,
                    operasyon=ops[(i - 1) % len(ops)],
                    sira=i,
                    defaults={
                        'istasyon': istasyonlar[(i - 1) % len(istasyonlar)] if istasyonlar else None,
                        'sure_dakika': random.randint(15, 120),
                        'maliyet': money(150, 400),
                    },
                )
                n += c
            self._log('Reçete Operasyon', n)

        n = 0
        standartlar = []
        for i in range(1, self.count + 1):
            obj, c = UretimStandarti.objects.get_or_create(
                kod=code('US', i),
                defaults={
                    'ad': f'{DEMO_MARKER} Üretim Standart Talimatı {i}',
                    'aciklama': 'Demo standart PDF',
                    'olusturma_tarihi': d(200),
                    'pdf_dosya': demo_pdf(f'demo-standart-{i}.pdf'),
                    'aktif': True,
                    'sira': i,
                },
            )
            standartlar.append(obj)
            n += c
        self._log('Üretim Standartı', n)

        if receteler:
            n = 0
            durumlar = ['PLANLANDI', 'BASLADI', 'TAMAMLANDI', 'PLANLANDI']
            for i, rec in enumerate(receteler, 1):
                _, c = UretimEmri.objects.get_or_create(
                    emir_no=code('UE', i),
                    defaults={
                        'recete': rec,
                        'miktar': Decimal(str(random.randint(10, 100))),
                        'production_type': pick(['ORDER', 'STOCK']),
                        'durum': durumlar[(i - 1) % len(durumlar)],
                        'planlanan_baslama': dt(i * 2, 8),
                        'planlanan_bitis': dt(-i, 17),
                        'aciklama': f'{DEMO_MARKER} üretim emri',
                    },
                )
                n += c
            self._log('Üretim Emri', n)

        n = 0
        for i, st in enumerate(stoklar, 1):
            prog, c = CncProgram.objects.get_or_create(
                product=st,
                program_name=f'{DEMO_MARKER}_{st.stok_kodu.split("-")[-1]}_OP10',
                defaults={
                    'machine_type': pick(['cnc_lathe', 'cnc_mill']),
                    'machine_name': pick(['Doosan Lynx', 'Haas VF2', 'Mazak']),
                    'file_format': 'nc',
                    'status': 'active',
                },
            )
            n += c
            if c or not prog.revisions.exists():
                CncProgramRevision.objects.get_or_create(
                    program=prog,
                    revision_code='R01',
                    defaults={
                        'revision_type': 'new',
                        'file_path': demo_nc(f'demo-{i}.nc'),
                        'revision_note': f'{DEMO_MARKER} ilk program revizyonu',
                        'created_by': self.user,
                        'is_active': True,
                    },
                )
        self._log('CNC Program', n)

        istasyonlar = self.ctx.get('istasyonlar', [])
        if urun and istasyonlar:
            n = 0
            for i in range(1, self.count + 1):
                _, c = KurulumDosyasi.objects.get_or_create(
                    urun=urun,
                    urun_parcasi=f'Parça-{i}',
                    versiyon='1.0',
                    defaults={
                        'istasyon': istasyonlar[(i - 1) % len(istasyonlar)],
                        'aciklama': f'{DEMO_MARKER} kurulum dosyası',
                        'pdf_dosya': demo_pdf(f'kurulum-{i}.pdf'),
                        'aktif': True,
                    },
                )
                n += c
            self._log('Kurulum Dosyası', n)

    def _seed_quality(self):
        musteriler = self.ctx.get('musteriler', [])
        stoklar = self.ctx.get('stoklar', [])
        siparisler = self.ctx.get('siparisler', [])
        if not musteriler or not stoklar:
            return

        n = 0
        sikayetler = []
        types = ['COMPLAINT', 'NCR', 'INTERNAL', 'COMPLAINT']
        for i, musteri in enumerate(musteriler, 1):
            obj, c = Complaint.objects.get_or_create(
                customer=musteri,
                product=stoklar[(i - 1) % len(stoklar)],
                category=f'{DEMO_MARKER} Ölçü Sapması',
                defaults={
                    'type': types[(i - 1) % len(types)],
                    'description': f'Demo şikayet kaydı #{i} — tolerans dışı ölçü tespit edildi.',
                    'severity': random.randint(2, 5),
                    'affected_qty': Decimal(str(random.randint(1, 20))),
                    'related_order': siparisler[(i - 1) % len(siparisler)] if siparisler else None,
                    'created_by': self.user,
                    'status': pick(['OPEN', 'IN_REVIEW', 'ACTIONED']),
                },
            )
            sikayetler.append(obj)
            n += c
        self._log('Şikayet/NCR', n)

        n = 0
        for i, st in enumerate(stoklar, 1):
            _, c = EcoChange.objects.get_or_create(
                product=st,
                to_revision=f'R{i}',
                defaults={
                    'change_type': pick(['BOM', 'ROUTING', 'MATERIAL', 'CONTROL_FORM']),
                    'from_revision': f'R{i - 1}' if i > 1 else '',
                    'description': f'{DEMO_MARKER} mühendislik değişiklik emri',
                    'effective_from_date': d(-10 * i),
                    'created_by': self.user,
                    'complaint': sikayetler[(i - 1) % len(sikayetler)] if sikayetler else None,
                },
            )
            n += c
        self._log('ECO', n)

        n = 0
        for i, st in enumerate(stoklar, 1):
            _, c = AlertRule.objects.get_or_create(
                scope='PRODUCT',
                product=st,
                message=f'{DEMO_MARKER} {st.ad} için ekstra kontrol gerekli',
                valid_from=dt(30, 8),
                defaults={
                    'level': pick(['INFO', 'ACK_REQUIRED']),
                    'created_by': self.user,
                    'active': True,
                },
            )
            n += c
        self._log('Uyarı Kuralı', n)

        n = 0
        for i, st in enumerate(stoklar, 1):
            plan, c = ControlPlan.objects.get_or_create(
                product=st,
                revision=f'A{i}',
                defaults={
                    'effective_from': d(60),
                    'created_by': self.user,
                    'description': f'{DEMO_MARKER} kontrol planı',
                    'status': 'ACTIVE',
                },
            )
            n += c
            if c or not plan.items.exists():
                ControlItem.objects.get_or_create(
                    plan=plan,
                    name=f'{DEMO_MARKER} Çap kontrolü',
                    defaults={
                        'inspection_type': 'NUMERIC',
                        'unit': 'mm',
                        'nominal': Decimal('50.000'),
                        'min_value': Decimal('49.950'),
                        'max_value': Decimal('50.050'),
                        'frequency_type': 'FIRST_PIECE',
                        'criticality': pick(['CRITICAL', 'MAJOR']),
                    },
                )
        self._log('Kontrol Planı', n)

    def _seed_arge_misc(self):
        stoklar = self.ctx.get('stoklar', [])
        if stoklar:
            n = 0
            durumlar = ['FIKIR', 'TASARIMDA', 'PROTOTIP', 'TEST']
            for i, st in enumerate(stoklar, 1):
                _, c = ArGeProje.objects.get_or_create(
                    proje_kodu=code('AG', i),
                    defaults={
                        'proje_adi': f'{DEMO_MARKER} {st.ad} geliştirme',
                        'stok_item': st,
                        'sorumlu': self.user,
                        'durum': durumlar[(i - 1) % len(durumlar)],
                        'oncelik': pick(['NORMAL', 'YUKSEK']),
                        'baslangic_tarihi': d(90),
                        'hedef_tarih': d(-60),
                        'aciklama': 'Demo Ar-Ge proje kaydı',
                    },
                )
                n += c
            self._log('Ar-Ge Proje', n)

        n = 0
        gt_baslik = [
            'Canlı akış haritası filtre iyileştirmesi',
            'RFQ karşılaştırma tablosu',
            'Mobil barkod okuma',
            'Teklif PDF şablon güncellemesi',
        ]
        for i, baslik in enumerate(gt_baslik[: self.count], 1):
            _, c = GelistirmeTalebi.objects.get_or_create(
                baslik=f'{DEMO_MARKER} {baslik}',
                defaults={
                    'aciklama': f'Demo geliştirme talebi — {baslik}',
                    'durum': pick(['ACIK', 'TAMAMLANDI']),
                },
            )
            n += c
        self._log('Geliştirme Talebi', n)

    def _seed_extras(self):
        stoklar = self.ctx.get('stoklar', [])
        tedarikciler = self.ctx.get('tedarikciler', [])
        complaints = list(Complaint.objects.filter(category__startswith=DEMO_MARKER)[: self.count])
        uretim_emirleri = list(UretimEmri.objects.filter(emir_no__startswith=f'{DEMO_MARKER}-')[: self.count])

        if complaints:
            n = 0
            for i, comp in enumerate(complaints, 1):
                _, c = CapaAction.objects.get_or_create(
                    complaint=comp,
                    action_text=f'{DEMO_MARKER} Proses parametreleri gözden geçirilecek',
                    defaults={
                        'action_type': pick(['CORRECTIVE', 'PREVENTIVE']),
                        'root_cause_method': '5WHY',
                        'root_cause_text': 'Torna takım aşınması nedeniyle ölçü sapması',
                        'owner': self.user,
                        'due_date': d(-14 + i),
                        'status': pick(['PENDING', 'IN_PROGRESS', 'COMPLETED']),
                    },
                )
                n += c
            self._log('CAPA Aksiyon', n)

        if stoklar and tedarikciler:
            tip = DisOperasyonTipi.objects.filter(aktif=True).first()
            if tip:
                n = 0
                durumlar = ['TASLAK', 'GONDERILDI', 'TEDARIKCIDE', 'TAMAMLANDI']
                for i, st in enumerate(stoklar, 1):
                    _, c = DisOperasyon.objects.get_or_create(
                        operasyon_no=code('DIS', i),
                        defaults={
                            'stok_item': st,
                            'uretim_emri': uretim_emirleri[(i - 1) % len(uretim_emirleri)] if uretim_emirleri else None,
                            'operasyon_tipi': tip,
                            'tedarikci': tedarikciler[(i - 1) % len(tedarikciler)],
                            'gonderim_deposu': self.ctx['depolar'][0] if self.ctx.get('depolar') else None,
                            'gonderilen_miktar': Decimal(str(random.randint(5, 40))),
                            'gonderim_tarihi': d(i * 5),
                            'beklenen_donus_tarihi': d(-10),
                            'birim_fiyat': money(80, 350),
                            'durum': durumlar[(i - 1) % len(durumlar)],
                            'dis_operasyon_lokasyonu': f'{DEMO_MARKER} Tedarikçi deposu',
                        },
                    )
                    n += c
                self._log('Dış Operasyon', n)

        if stoklar:
            n = 0
            tipler = ['GIRIS', 'CIKIS', 'URETIM_GIRIS', 'TRANSFER']
            for i, st in enumerate(stoklar, 1):
                if StokHareketi.objects.filter(referans_no=code('HAR', i)).exists():
                    continue
                StokHareketi.objects.create(
                    stok_item=st,
                    hareket_tipi=tipler[(i - 1) % len(tipler)],
                    miktar=Decimal('5'),
                    birim=st.birim or 'Adet',
                    referans_no=code('HAR', i),
                    depo=self.ctx['depolar'][0] if self.ctx.get('depolar') else None,
                    aciklama=f'{DEMO_MARKER} demo stok hareketi',
                    user=self.user.username,
                    onceki_stok=Decimal('0'),
                    sonraki_stok=Decimal('0'),
                )
                n += 1
            self._log('Stok Hareketi', n)


def run_demo_seed(count=4, stdout=None, style=None):
    seeder = DemoSeeder(count=count, stdout=stdout, style=style)
    return seeder.run()
