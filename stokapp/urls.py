from django.urls import path

from .views_canli_akis import (
    api_canli_akis_haritasi,
    api_canli_akis_is_emri_detay,
    canli_akis_haritasi,
)
from .views_uretim_degisim import (
    uretim_degisim_listesi,
    uretim_degisim_ekle,
    uretim_degisim_duzenle,
    uretim_degisim_goruntule,
    uretim_degisim_kapat,
)
from .views_uretim import (
    uretim_emri_listesi, uretim_emri_ekle, uretim_emri_detay,
    api_uretim_emri_urun_ara,
    uretim_emri_baslat, uretim_emri_tamamla,
    uretim_emri_toplu_islem,
    uretim_emri_iptal, uretim_emri_sil, asama_durum_guncelle,
    uretim_planlama, uretim_planlama_atama,
    uretim_planlama_export_pdf,
    uretim_planlama_gorev_detay, uretim_planlama_gorev_aksiyon,
    uretim_planlama_gorev_not_ekle, uretim_planlama_gorev_sorun_bildir,
    uretim_planlama_gorev_talimat, uretim_planlama_gorev_plan_guncelle,
    uretim_emri_listesi_export_excel, uretim_emri_listesi_export_pdf,
    uretim_raporlari, uretim_raporlari_api_liste, uretim_raporlari_api_ozet,
    uretim_raporlari_export_excel, uretim_raporlari_export_pdf,
    uretim_raporlari_api_detay, uretim_durus_raporlari,
    uretim_durus_raporlari_api_liste, uretim_durus_raporlari_api_ozet,
    uretim_durus_raporlari_api_grafikler, uretim_durus_raporlari_export_excel,
    uretim_durus_raporlari_export_pdf
)
from .views_takim import (
    takim_listesi, takim_detay, takim_raporlari, takim_secenek_yonetimi,
    create_tool, create_tool_option, get_tools, get_tool_detail, log_tool_usage,
    create_tool_change, get_tool_reports
)

from .views_depo import (
    depo_listesi, depo_ekle, depo_duzenle, depo_sil,
    raf_listesi, raf_ekle, raf_duzenle, raf_sil
)

from .views_kategori import (
    kategori_listesi, kategori_ekle, kategori_duzenle, kategori_sil,
    tedarikci_listesi, tedarikci_ekle, tedarikci_duzenle, tedarikci_sil, tedarikci_stoklari,
    birim_listesi, birim_ekle, birim_duzenle, birim_sil,
    musteri_listesi, musteri_ekle, musteri_duzenle, musteri_sil, musteri_siparisleri
)

from .views_transfer import stok_transfer, stok_transfer_listesi
from . import views
from .views_gunluk_yonetim import api_gunluk_yonetim_ozet, gunluk_yonetim_paneli
from .views_enerji import (
    api_enerji_haftalik_plan,
    api_enerji_hava_tahmini,
    api_enerji_ozet,
    api_enerji_planlama_ozet,
    api_enerji_transfer_switch_demo,
    enerji_dashboard,
    enerji_planlama,
)
from .views_yetkilendirme import (
    yetkilendirme_kullanici_roller,
    yetkilendirme_kullanicilar,
    yetkilendirme_rol_duzenle,
    yetkilendirme_rol_ekle,
    yetkilendirme_rol_sil,
    yetkilendirme_roller,
    yetkilendirme_yetkiler,
)
from .views_detay import stok_detay
from .views_api import api_check_stok_kodu, api_shelves, api_quick_add, api_personel_bilgi, api_stok_fiyat
from .views_tekora import (
    tekora_ping,
    tekora_system_summary,
    tekora_chat_page,
    tekora_chat_api,
    tekora_tool_search_stock,
    tekora_tool_create_purchase_request,
    tekora_tool_analyze_critical_stock,
    tekora_tool_production_intelligence,
    tekora_tool_tool_intelligence,
    tekora_semantic_search,
)
from .views_hareket import (
    stok_giris, stok_cikis, 
    stok_hareket_listesi, stok_hareket_duzenle, stok_hareket_sil, stok_toplu_hareket,
    stok_hareket_listesi_export_excel, stok_hareket_listesi_export_pdf
)
from .views_stok_sayim import (
    stok_sayim_basla,
    stok_sayim_baslat,
    stok_sayim_calis,
    stok_sayim_iptal,
    stok_sayim_listesi,
    stok_sayim_rapor,
    stok_sayim_rapor_excel,
    stok_sayim_rapor_pdf,
    stok_sayim_sil,
)
from .views_stokitem import stok_ekle, stok_duzenle, stok_sil, stok_toplu_sil, stok_qrcode, stok_kopyala, stok_recete_maliyetleri, stok_etiket_yazdir, stok_ek_dosya_sil
from .views_stok_tamamlanma import (
    stok_tamamlanma_ayarlari,
    stok_tamamlanma_raporu,
    stok_tamamlanma_raporu_export_excel,
    stok_tamamlanma_raporu_export_pdf,
)
from .views_fiyat import fiyat_gecmisi, fiyat_gecmisi_listesi
from .views_para_birimi import (
    para_birimi_listesi, para_birimi_ekle, para_birimi_duzenle, para_birimi_sil
)
from .views_ayarlar import (
    genel_ayarlar, hata_raporlari, hata_raporu_coz, hata_raporu_sil,
    yedekle_altyapi, yedekle_veriler, geri_yukle_altyapi, geri_yukle_veriler,
    gelistirme_talep_listesi, gelistirme_talep_ekle, gelistirme_talep_duzenle,
    gelistirme_talep_kapat, yapim_asamasinda, veri_yedekleme,
    genel_ayarlar_cc_test_mail,
    genel_ayarlar_smtp_test_mail,
    genel_ayarlar_imap_test,
)
from .views_skala import skala_entegrasyon, skala_stok_export, skala_cari_export, skala_recete_export
from .views_import import (
    veri_ice_aktarma, download_stok_template, download_tedarikci_template, 
    download_musteri_template, import_stok_excel, import_tedarikci_excel, import_musteri_excel
)
from .views_yazdirma import (
    yazdirma_sablonlari_listesi, yazdirma_sablonu_duzenle, yazdirma_sablonu_onizleme,
    yazdirma_sablonu_api_save
)
from .views_uretim_kontrol import (
    uretim_kontrol_ana,
    uretim_kontrol_urun,
    uretim_kontrol_sablon,
    uretim_kontrol_sablon_yonetim,
    uretim_kontrol_plan_olustur,
    uretim_kontrol_plan_duzenle,
    uretim_kontrol_plan_sil,
    uretim_kontrol_adim_ekle,
    uretim_kontrol_adim_duzenle,
    uretim_kontrol_adim_sil,
    uretim_kontrol_adim_sira,
    uretim_kontrol_revizyon_detay,
    uretim_kontrol_baslat,
    uretim_kontrol_olcum,
    uretim_kontrol_sonuc,
    uretim_kontrol_sonuc_duzenle,
    uretim_kontrol_pdf,
    uretim_kontrol_oturum_arsivle,
    uretim_kontrol_oturum_arsivden_cikar,
    api_uretim_kontrol_urun_ara,
    api_uretim_kontrol_alt_parca,
    api_uretim_kontrol_planlar,
    api_uretim_kontrol_plan_detay,
    api_uretim_kontrol_session_result,
    api_uretim_kontrol_session_finish,
)
from .views_recete import (
    recete_listesi, recete_ekle, recete_detay, recete_duzenle, recete_sil, recete_kopyala,
    recete_detay_export_pdf,
    recete_stok_ara, recete_kaynak_ara, recete_disaridan_kopyala,
    recete_detay_ekle, recete_detay_degistir, recete_detay_sil,
    recete_detay_sira_kaydet, recete_operasyon_sira_kaydet,
    recete_operasyon_listesi, recete_operasyon_ekle, recete_operasyon_duzenle, recete_operasyon_sil,
    istasyon_maliyet_getir
)
from .views_recete_dis import (
    recete_dis_operasyon_listesi, recete_dis_operasyon_ekle, recete_dis_operasyon_duzenle,
    recete_dis_operasyon_sil, dis_operasyon_tipi_ekle,
)
from .views_talimat import (
    recete_talimat_listesi, recete_talimat_ekle, recete_talimat_duzenle, recete_talimat_sil,
    recete_talimat_olcu_ekle, recete_talimat_olcu_duzenle, recete_talimat_olcu_sil,
    recete_talimat_dosya_ekle, recete_talimat_dosya_sil,
    recete_talimat_ekipman_ekle, recete_talimat_ekipman_sil,
    recete_talimat_fikstur_ekle, recete_talimat_fikstur_sil,
    recete_talimat_olcu_aleti_ekle, recete_talimat_olcu_aleti_sil,
    recete_talimat_program_ekle, recete_talimat_program_sil,
    recete_talimat_aciklama_ekle, recete_talimat_aciklama_duzenle, recete_talimat_aciklama_sil,
    recete_talimat_kurulum_dosyasi_ekle, recete_talimat_kurulum_dosyasi_sil, recete_talimat_kurulum_dosyalari_listesi
)
from .views_kullanici import (
    kullanici_listesi, kullanici_ekle, kullanici_duzenle, 
    kullanici_sil, kullanici_sifre_sifirla
)
from .views_operasyon import (
    operasyon_listesi, operasyon_ekle, operasyon_duzenle, 
    operasyon_sil, operasyon_durum_degistir
)
from .views_dis_operasyon_tipi import (
    dis_operasyon_tipi_listesi, dis_operasyon_tipi_ekle_sayfa, dis_operasyon_tipi_duzenle,
    dis_operasyon_tipi_sil, dis_operasyon_tipi_durum_degistir,
)
from .views_istasyon import (
    istasyon_listesi, istasyon_ekle, istasyon_duzenle, 
    istasyon_sil, istasyon_durum_degistir
)
from .views_ekipman import (
    ekipman_listesi, ekipman_ekle, ekipman_duzenle,
    ekipman_sil, ekipman_durum_degistir
)
from .views_fikstur import (
    fikstur_listesi, fikstur_ekle, fikstur_duzenle,
    fikstur_sil, fikstur_durum_degistir
)
from .views_olcu_aleti import (
    olcu_aleti_listesi, olcu_aleti_ekle, olcu_aleti_duzenle, olcu_aleti_sil, olcu_aleti_durum_degistir,
    olcu_aleti_turu_listesi, olcu_aleti_turu_ekle, olcu_aleti_turu_duzenle, olcu_aleti_turu_sil,
    kalibrasyon_ekle, olcu_aleti_dashboard, olcu_aleti_export_pdf
)
from .views_kalite import (
    complaint_listesi, complaint_detay, complaint_ekle, complaint_duzenle, complaint_sil,
    complaint_ekle_attachment,
    capa_action_ekle, capa_action_duzenle, capa_action_sil,
    eco_listesi, eco_detay, eco_ekle, eco_duzenle, eco_onayla, eco_reddet, eco_sil,
    alert_rule_listesi, alert_rule_ekle, alert_rule_duzenle, alert_rule_sil,
    control_plan_listesi, control_plan_detay, control_plan_ekle, control_item_ekle,
    api_get_alerts
)
from .views_inspection import (
    inspection_dashboard, work_order_inspection_listesi, inspection_ekle_modal,
    api_get_required_inspections, api_get_valid_instruments, api_get_control_item,
)
from .views_arac import (
    arac_listesi, arac_ekle, arac_detay, arac_duzenle, arac_sil,
    arac_belgesi_ekle, arac_belgesi_duzenle, arac_belgesi_guncelle, arac_belgesi_sil,
    api_arac_belge_turu_ekle,
)
from .views_gayrimenkul import (
    gayrimenkul_listesi,
    gayrimenkul_ekle,
    gayrimenkul_duzenle,
    gayrimenkul_detay,
    gayrimenkul_arsivle,
    gayrimenkul_islem_ekle,
    gayrimenkul_islem_duzenle,
    gayrimenkul_dosya_ekle,
)
from .views_finansal import (
    banka_hesaplari_listesi, banka_hesabi_ekle, banka_hesabi_duzenle, banka_hesabi_sil,
    kredi_kartlari_listesi, kredi_karti_ekle, kredi_karti_duzenle, kredi_karti_sil,
    aylik_odemeler_listesi, aylik_odeme_ekle, aylik_odeme_duzenle, aylik_odeme_sil,
    aylik_odeme_odendi_isaretle, get_odeme_sekli_options
)
from .views_sigorta import (
    sigorta_listesi, sigorta_ekle, sigorta_duzenle, 
    sigorta_arsivle, sigorta_sil
)
from .views_uretim_standartlari import (
    uretim_standarti_listesi, uretim_standarti_ekle, uretim_standarti_detay,
    uretim_standarti_duzenle, uretim_standarti_sil, uretim_standarti_revizyon_ekle,
    uretim_standarti_pdf_indir, uretim_standarti_pdf_sil, uretim_standarti_arsiv_pdf_indir, uretim_standarti_durum_degistir
)
from .views_cnc_program import (
    cnc_program_listesi, cnc_program_ekle, cnc_program_detay, cnc_program_duzenle,
    cnc_program_sil, cnc_program_revizyon_ekle, cnc_program_revizyon_indir,
    cnc_program_revizyon_rollback, api_cnc_programlar_urun, cnc_program_urun_ara
)
from .views_cnc_dosya_agaci import (
    cnc_dosya_agaci_listesi,
    cnc_dosya_agaci_api_tree,
    cnc_dosya_agaci_api_create,
    cnc_dosya_agaci_api_update,
    cnc_dosya_agaci_api_delete,
    cnc_dosya_agaci_api_move,
    cnc_dosya_agaci_makina_listesi,
    cnc_dosya_agaci_makina_ekle,
    cnc_dosya_agaci_makina_sil,
    cnc_dosya_agaci_makina_api_istasyonlar,
)
from .views_cnc_ekipman import (
    cnc_ekipman_listesi,
    cnc_ekipman_ekle,
    cnc_ekipman_duzenle,
    cnc_ekipman_sil,
)
from .views_arge import (
    arge_asama_yakinda,
    arge_dosya_ekle,
    arge_dosya_indir,
    arge_dosya_listesi,
    arge_dosya_sil,
    arge_proje_arsivle,
    arge_proje_detay,
    arge_proje_duzenle,
    arge_proje_ekle,
    arge_proje_listesi,
    arge_revizyon_duzenle,
    arge_revizyon_ekle,
    arge_revizyon_listesi,
    arge_revizyon_sil,
)
from .views_document import (
    document_listesi, document_detay, document_ekle, document_duzenle,
    document_dosya_yukle, document_dosya_indir, document_dashboard,
    document_type_listesi, document_type_ekle, document_type_duzenle,
    api_document_type_category_ekle,
)
from .views_kurulum import (
    kurulum_dosyalari_listesi, kurulum_dosyasi_ekle, kurulum_dosyasi_detay,
    kurulum_dosyasi_duzenle, kurulum_dosyasi_sil, kurulum_dosyasi_urun_ara,
    kurulum_dosyasi_recete_bilesenleri, kurulum_dosyasi_cnc_ekipman_secenekleri_api,
    kurulum_dosyasi_pdf_indir, kurulum_dosyasi_arsiv_pdf_indir, kurulum_dosyasi_arsiv_listesi
)
from .views_personel import (
    personel_listesi, personel_ekle, personel_duzenle,
    gunluk_calisma_listesi, gunluk_calisma_ekle, gunluk_calisma_duzenle, gunluk_calisma_sil,
    avans_odeme_ekle, avans_odeme_duzenle, avans_odeme_sil,
    personel_izin_listesi, personel_izin_duzenle, personel_izin_sil,
    personel_detay, personel_belgeleri, personel_belgesi_ekle, personel_belgesi_duzenle,
    personel_belgesi_arsivle, personel_belgesi_sil
)
from .views_siparis import (
    siparis_listesi, siparis_ekle, siparis_detay, siparis_duzenle, siparis_sil, siparis_uretim_emri_olustur,
    siparis_maliyetleri, siparis_maliyeti_duzenle, siparis_maliyeti_sil, siparis_maliyetleri_listesi,
    siparis_maliyetleri_export_pdf,
    teslimat_bekleyen_kalemleri_export_pdf,
    siparis_onayla, siparis_onay_mail_alici_sec, siparis_onay_mail_onay,
    siparis_reddet, siparis_teslim_et,
    start_production_from_order, fulfill_from_stock, fulfill_from_inproduction, produce_remaining, produce_full, apply_siparis_kalem_kararlari, siparis_items_api,
)
from .views_teklif import (
    teklif_listesi,
    teklif_ekle,
    teklif_duzenle,
    teklif_sil,
    teklif_detay,
    teklif_pdf_indir,
    teklif_gonder,
    teklif_mail_alici_sec,
    teklif_mail_onay,
    teklif_musteri_cevabi_onay,
    teklif_musteri_cevabi_red,
    teklif_onay_kalemler_json,
    teklif_sartlari_onizle,
)
from .views_satinalma import (
    satinalma_listesi, satinalma_ekle, satinalma_detay, satinalma_duzenle, satinalma_sil,
    satinalma_tamamini_teslim, satinalma_ksimi_teslim, satinalma_ksimi_teslim_modal,
    satinalma_detay_popup, satinalma_kismi_teslimat, satinalma_tam_teslimat,
    teklif_talep_formu, teklif_talep_formu_pdf, teklif_talep_formu_email,
    teklif_formu_teknik_resim_isle, uretim_malzemesi_planla, uretim_malzemesi_planla_pdf, satinalma_items_api,
    teklif_girisi, siparis_formu, siparis_formu_pdf, siparis_formu_email,
    satinalma_mail_alici_sec, satinalma_mail_onay,
)
from .views_rfq import (
    rfq_olustur, rfq_duzenle, rfq_detay, rfq_sil,
    rfq_oneri_tedarikciler_api,
    rfq_mail_alici_sec, rfq_mail_gonder,
    rfq_teklif_girisi, rfq_karsilastirma, rfq_kazananlari_kaydet,
    rfq_siparise_donustur, rfq_siparis_mail_secimi,
    rfq_siparis_mail_baslat, rfq_siparis_mail_atla,
)
from .views_performans import tedarikci_performans
from .views_talep_yonetimi import (
    talep_listesi,
    talep_ekle,
    talep_duzenle,
    talep_detay,
    talep_durum_aksiyon,
    talep_satinalmaya_aktar,
    talep_kapat,
    talep_arsivle,
)
from .views_approval_requests import (
    ai_approval_center,
    approval_requests_collection_api,
    approval_request_detail_api,
    approval_request_approve_api,
    approval_request_reject_api,
    approval_requests_bulk_approve_api,
    approval_requests_bulk_reject_api,
    approval_request_seed_demo_api,
    simulate_email_order_api,
    cleanup_approval_email_texts_api,
    approval_requests_refresh_pending_email_api,
    approval_request_refresh_analysis_api,
)
from .views_mail import test_read_mails_imap_api

from django.conf import settings
from django.conf.urls.static import static

app_name = "stokapp"

urlpatterns = [
    # Ana ekran / dashboard
    path("", views.dashboard, name="dashboard"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/tekora-toggle/", views.tekora_aktiflik_toggle, name="tekora_aktiflik_toggle"),
    path("ana-sayfa/", views.ana_sayfa, name="ana_sayfa"),
    path("gunluk-yonetim-paneli/", gunluk_yonetim_paneli, name="gunluk_yonetim_paneli"),
    path("api/gunluk-yonetim-ozet/", api_gunluk_yonetim_ozet, name="api_gunluk_yonetim_ozet"),
    path("enerji-dashboard/", enerji_dashboard, name="enerji_dashboard"),
    path("enerji-planlama/", enerji_planlama, name="enerji_planlama"),
    path("api/enerji-ozet/", api_enerji_ozet, name="api_enerji_ozet"),
    path("api/enerji-haftalik-plan/", api_enerji_haftalik_plan, name="api_enerji_haftalik_plan"),
    path("api/enerji-hava-tahmini/", api_enerji_hava_tahmini, name="api_enerji_hava_tahmini"),
    path("api/enerji-planlama-ozet/", api_enerji_planlama_ozet, name="api_enerji_planlama_ozet"),
    path(
        "api/enerji-transfer-switch-demo/",
        api_enerji_transfer_switch_demo,
        name="api_enerji_transfer_switch_demo",
    ),
    path("api/tekora/ping/", tekora_ping, name="api_tekora_ping"),
    path("api/tekora/system-summary/", tekora_system_summary, name="tekora_system_summary"),
    path("tekora/", tekora_chat_page, name="tekora_chat"),
    path("api/tekora/chat/", tekora_chat_api, name="tekora_chat_api"),
    path(
        "api/tekora/tools/search-stock/",
        tekora_tool_search_stock,
        name="tekora_tool_search_stock",
    ),
    path(
        "api/tekora/tools/create-purchase-request/",
        tekora_tool_create_purchase_request,
        name="tekora_tool_create_purchase_request",
    ),
    path(
        "api/tekora/tools/analyze-critical-stock/",
        tekora_tool_analyze_critical_stock,
        name="tekora_tool_analyze_critical_stock",
    ),
    path(
        "api/tekora/tools/production-intelligence/",
        tekora_tool_production_intelligence,
        name="tekora_tool_production_intelligence",
    ),
    path(
        "api/tekora/tools/tool-intelligence/",
        tekora_tool_tool_intelligence,
        name="tekora_tool_tool_intelligence",
    ),
    path(
        "api/tekora/semantic-search/",
        tekora_semantic_search,
        name="tekora_semantic_search",
    ),
    path("ai-approval-center/", ai_approval_center, name="ai_approval_center"),
    path(
        "approval-requests/refresh-pending-email",
        approval_requests_refresh_pending_email_api,
        name="approval_requests_refresh_pending_email_api",
    ),
    path("approval-requests", approval_requests_collection_api, name="approval_requests_collection_api"),
    path(
        "approval-requests/<uuid:pk>/refresh-analysis",
        approval_request_refresh_analysis_api,
        name="approval_request_refresh_analysis_api",
    ),
    path("approval-requests/<uuid:pk>", approval_request_detail_api, name="approval_request_detail_api"),
    path("approval-requests/<uuid:pk>/approve", approval_request_approve_api, name="approval_request_approve_api"),
    path("approval-requests/<uuid:pk>/reject", approval_request_reject_api, name="approval_request_reject_api"),
    path("approval-requests/bulk-approve", approval_requests_bulk_approve_api, name="approval_requests_bulk_approve_api"),
    path("approval-requests/bulk-reject", approval_requests_bulk_reject_api, name="approval_requests_bulk_reject_api"),
    path(
        "approval-requests/cleanup-email-texts",
        cleanup_approval_email_texts_api,
        name="cleanup_approval_email_texts_api",
    ),
    path("approval-requests/seed-demo", approval_request_seed_demo_api, name="approval_request_seed_demo_api"),
    path("simulate-email-order", simulate_email_order_api, name="simulate_email_order_api"),
    path("test-read-mails-imap", test_read_mails_imap_api, name="test_read_mails_imap_api"),

    # Fiyat Geçmişi
    path("fiyat-gecmisi/<int:pk>/", fiyat_gecmisi, name="fiyat_gecmisi"),
    path("fiyat-gecmisi/", fiyat_gecmisi_listesi, name="fiyat_gecmisi_listesi"),

    # Depo ve Raf Yönetimi
    path("depo/", depo_listesi, name="depo_listesi"),
    path("depo/ekle/", depo_ekle, name="depo_ekle"),
    path("depo/duzenle/<int:pk>/", depo_duzenle, name="depo_duzenle"),
    path("depo/sil/<int:pk>/", depo_sil, name="depo_sil"),
    path("raf/", raf_listesi, name="raf_listesi"),
    path("raf/ekle/", raf_ekle, name="raf_ekle"),
    path("raf/duzenle/<int:pk>/", raf_duzenle, name="raf_duzenle"),
    path("raf/sil/<int:pk>/", raf_sil, name="raf_sil"),

        # Üretim Emirleri
    path("uretim/emirler/", uretim_emri_listesi, name="uretim_emri_listesi"),
    path("uretim/emirler/export/excel/", uretim_emri_listesi_export_excel, name="uretim_emri_listesi_export_excel"),
    path("uretim/emirler/export/pdf/", uretim_emri_listesi_export_pdf, name="uretim_emri_listesi_export_pdf"),
    path("uretim/emirler/ekle/", uretim_emri_ekle, name="uretim_emri_ekle"),
    path("uretim/emirler/urun-ara/", api_uretim_emri_urun_ara, name="api_uretim_emri_urun_ara"),
    path("uretim/emir/<int:pk>/", uretim_emri_detay, name="uretim_emri_detay"),
    path("uretim/emirler/toplu/", uretim_emri_toplu_islem, name="uretim_emri_toplu_islem"),
    path("uretim/emir/<int:pk>/baslat/", uretim_emri_baslat, name="uretim_emri_baslat"),
    path("uretim/emir/<int:pk>/tamamla/", uretim_emri_tamamla, name="uretim_emri_tamamla"),
    path("uretim/emir/<int:pk>/iptal/", uretim_emri_iptal, name="uretim_emri_iptal"),
    path("uretim/emir/<int:pk>/sil/", uretim_emri_sil, name="uretim_emri_sil"),
    path("uretim/canli-akis-haritasi/", canli_akis_haritasi, name="canli_akis_haritasi"),
    path("api/uretim/canli-akis-haritasi/", api_canli_akis_haritasi, name="api_canli_akis_haritasi"),
    path(
        "api/uretim/canli-akis-haritasi/is-emri/<int:pk>/",
        api_canli_akis_is_emri_detay,
        name="api_canli_akis_is_emri_detay",
    ),
    path("uretim/asama/<int:asama_id>/durum/", asama_durum_guncelle, name="asama_durum_guncelle"),
    path("uretim/planlama/", uretim_planlama, name="uretim_planlama"),
    path("uretim/planlama/export/pdf/", uretim_planlama_export_pdf, name="uretim_planlama_export_pdf"),
    path("uretim/planlama/atama/", uretim_planlama_atama, name="uretim_planlama_atama"),
    path("uretim/planlama/gorev/<int:asama_id>/detay/", uretim_planlama_gorev_detay, name="uretim_planlama_gorev_detay"),
    path("uretim/planlama/gorev/<int:asama_id>/plan/", uretim_planlama_gorev_plan_guncelle, name="uretim_planlama_gorev_plan_guncelle"),
    path("uretim/planlama/gorev/<int:asama_id>/aksiyon/", uretim_planlama_gorev_aksiyon, name="uretim_planlama_gorev_aksiyon"),
    path("uretim/planlama/gorev/<int:asama_id>/not/", uretim_planlama_gorev_not_ekle, name="uretim_planlama_gorev_not_ekle"),
    path("uretim/planlama/gorev/<int:asama_id>/sorun/", uretim_planlama_gorev_sorun_bildir, name="uretim_planlama_gorev_sorun_bildir"),
    path("uretim/planlama/gorev/<int:asama_id>/talimat/", uretim_planlama_gorev_talimat, name="uretim_planlama_gorev_talimat"),
    path("uretim/raporlar/", uretim_raporlari, name="uretim_raporlari"),
    path("uretim/raporlar/export/excel/", uretim_raporlari_export_excel, name="uretim_raporlari_export_excel"),
    path("uretim/raporlar/export/pdf/", uretim_raporlari_export_pdf, name="uretim_raporlari_export_pdf"),
    path("uretim/raporlar/api/liste/", uretim_raporlari_api_liste, name="uretim_raporlari_api_liste"),
    path("uretim/raporlar/api/ozet/", uretim_raporlari_api_ozet, name="uretim_raporlari_api_ozet"),
    path("uretim/raporlar/api/detay/<int:asama_id>/", uretim_raporlari_api_detay, name="uretim_raporlari_api_detay"),
    path("uretim/durus-raporlari/", uretim_durus_raporlari, name="uretim_durus_raporlari"),
    path("uretim/durus-raporlari/api/liste/", uretim_durus_raporlari_api_liste, name="uretim_durus_raporlari_api_liste"),
    path("uretim/durus-raporlari/api/ozet/", uretim_durus_raporlari_api_ozet, name="uretim_durus_raporlari_api_ozet"),
    path("uretim/durus-raporlari/api/grafikler/", uretim_durus_raporlari_api_grafikler, name="uretim_durus_raporlari_api_grafikler"),
    path("uretim/durus-raporlari/export/excel/", uretim_durus_raporlari_export_excel, name="uretim_durus_raporlari_export_excel"),
    path("uretim/durus-raporlari/export/pdf/", uretim_durus_raporlari_export_pdf, name="uretim_durus_raporlari_export_pdf"),
    path("uretim/degisiklikler/", uretim_degisim_listesi, name="uretim_degisim_listesi"),
    path("uretim/degisiklikler/ekle/", uretim_degisim_ekle, name="uretim_degisim_ekle"),
    path("uretim/degisiklikler/<int:pk>/duzenle/", uretim_degisim_duzenle, name="uretim_degisim_duzenle"),
    path("uretim/degisiklikler/<int:pk>/goruntule/", uretim_degisim_goruntule, name="uretim_degisim_goruntule"),
    path("uretim/degisiklikler/<int:pk>/kapat/", uretim_degisim_kapat, name="uretim_degisim_kapat"),
    path("uretim/takim-yonetimi/", takim_listesi, name="takim_listesi"),
    path("uretim/takim-yonetimi/secenekler/", takim_secenek_yonetimi, name="takim_secenek_yonetimi"),
    path("uretim/takim-yonetimi/<int:pk>/", takim_detay, name="takim_detay"),
    path("uretim/takim-raporlari/", takim_raporlari, name="takim_raporlari"),
    path("api/tools/create/", create_tool, name="create_tool"),
    path("api/tools/options/create/", create_tool_option, name="create_tool_option"),
    path("api/tools/", get_tools, name="get_tools"),
    path("api/tools/<int:pk>/", get_tool_detail, name="get_tool_detail"),
    path("api/tools/log-usage/", log_tool_usage, name="log_tool_usage"),
    path("api/tools/change/", create_tool_change, name="create_tool_change"),
    path("api/tools/reports/", get_tool_reports, name="get_tool_reports"),
    
    # Üretim Reçeteleri
    path("uretim/receteler/", recete_listesi, name="recete_listesi"),
    path("uretim/recete/ekle/", recete_ekle, name="recete_ekle"),
    path("uretim/recete/<int:pk>/", recete_detay, name="recete_detay"),
    path("uretim/recete/<int:pk>/export/pdf/", recete_detay_export_pdf, name="recete_detay_export_pdf"),
    path("uretim/recete/<int:pk>/duzenle/", recete_duzenle, name="recete_duzenle"),
    path("uretim/recete/<int:pk>/sil/", recete_sil, name="recete_sil"),
    path("uretim/recete/<int:pk>/kopyala/", recete_kopyala, name="recete_kopyala"),
    path("uretim/recete/stok-ara/", recete_stok_ara, name="recete_stok_ara"),
    path("uretim/recete/kaynak-ara/", recete_kaynak_ara, name="recete_kaynak_ara"),
    path("uretim/recete/<int:pk>/disaridan-kopyala/", recete_disaridan_kopyala, name="recete_disaridan_kopyala"),
    path("uretim/recete/<int:pk>/detay-ekle/", recete_detay_ekle, name="recete_detay_ekle"),
    path("uretim/recete/<int:pk>/detay/<int:detay_id>/degistir/", recete_detay_degistir, name="recete_detay_degistir"),
    path("uretim/recete/<int:pk>/detay/<int:detay_id>/sil/", recete_detay_sil, name="recete_detay_sil"),
    path("uretim/recete/<int:pk>/detay-sira/", recete_detay_sira_kaydet, name="recete_detay_sira_kaydet"),
    path("uretim/recete/<int:pk>/operasyon-sira/", recete_operasyon_sira_kaydet, name="recete_operasyon_sira_kaydet"),
    path("uretim/recete/<int:pk>/operasyonlar/", recete_operasyon_listesi, name="recete_operasyon_listesi"),
    path("uretim/recete/<int:pk>/operasyon-ekle/", recete_operasyon_ekle, name="recete_operasyon_ekle"),
    path("uretim/recete/<int:pk>/operasyon/<int:operasyon_id>/duzenle/", recete_operasyon_duzenle, name="recete_operasyon_duzenle"),
    path("uretim/recete/<int:pk>/operasyon/<int:operasyon_id>/sil/", recete_operasyon_sil, name="recete_operasyon_sil"),
    path("uretim/recete/<int:pk>/dis-operasyonlar/", recete_dis_operasyon_listesi, name="recete_dis_operasyon_listesi"),
    path("uretim/recete/<int:pk>/dis-operasyon-ekle/", recete_dis_operasyon_ekle, name="recete_dis_operasyon_ekle"),
    path("uretim/recete/<int:pk>/dis-operasyon/<int:item_id>/duzenle/", recete_dis_operasyon_duzenle, name="recete_dis_operasyon_duzenle"),
    path("uretim/recete/<int:pk>/dis-operasyon/<int:item_id>/sil/", recete_dis_operasyon_sil, name="recete_dis_operasyon_sil"),
    path("uretim/dis-operasyon-tipi-ekle/", dis_operasyon_tipi_ekle, name="dis_operasyon_tipi_ekle"),

    # Üretim Kontrol
    path("uretim/kontrol/", uretim_kontrol_ana, name="uretim_kontrol_ana"),
    path("uretim/kontrol/urun/<int:product_pk>/", uretim_kontrol_urun, name="uretim_kontrol_urun"),
    path("uretim/kontrol/sablon/<int:plan_pk>/", uretim_kontrol_sablon, name="uretim_kontrol_sablon"),
    path("uretim/kontrol/sablon-yonetim/", uretim_kontrol_sablon_yonetim, name="uretim_kontrol_sablon_yonetim"),
    path("uretim/kontrol/plan/olustur/", uretim_kontrol_plan_olustur, name="uretim_kontrol_plan_olustur"),
    path("uretim/kontrol/plan/<int:pk>/duzenle/", uretim_kontrol_plan_duzenle, name="uretim_kontrol_plan_duzenle"),
    path("uretim/kontrol/plan/<int:pk>/sil/", uretim_kontrol_plan_sil, name="uretim_kontrol_plan_sil"),
    path("uretim/kontrol/plan/<int:plan_pk>/adim/ekle/", uretim_kontrol_adim_ekle, name="uretim_kontrol_adim_ekle"),
    path("uretim/kontrol/adim/<int:step_pk>/duzenle/", uretim_kontrol_adim_duzenle, name="uretim_kontrol_adim_duzenle"),
    path("uretim/kontrol/adim/<int:step_pk>/sil/", uretim_kontrol_adim_sil, name="uretim_kontrol_adim_sil"),
    path("uretim/kontrol/plan/<int:plan_pk>/adim-sira/", uretim_kontrol_adim_sira, name="uretim_kontrol_adim_sira"),
    path("uretim/kontrol/revizyon/<int:archive_pk>/", uretim_kontrol_revizyon_detay, name="uretim_kontrol_revizyon_detay"),
    path("uretim/kontrol/baslat/", uretim_kontrol_baslat, name="uretim_kontrol_baslat"),
    path("uretim/kontrol/oturum/<int:session_pk>/adim/<int:step_index>/", uretim_kontrol_olcum, name="uretim_kontrol_olcum"),
    path("uretim/kontrol/oturum/<int:session_pk>/sonuc/", uretim_kontrol_sonuc, name="uretim_kontrol_sonuc"),
    path("uretim/kontrol/sonuc/<int:result_pk>/duzenle/", uretim_kontrol_sonuc_duzenle, name="uretim_kontrol_sonuc_duzenle"),
    path("uretim/kontrol/oturum/<int:session_pk>/pdf/", uretim_kontrol_pdf, name="uretim_kontrol_pdf"),
    path("uretim/kontrol/oturum/<int:session_pk>/arsivle/", uretim_kontrol_oturum_arsivle, name="uretim_kontrol_oturum_arsivle"),
    path("uretim/kontrol/oturum/<int:session_pk>/arsivden-cikar/", uretim_kontrol_oturum_arsivden_cikar, name="uretim_kontrol_oturum_arsivden_cikar"),
    path("api/uretim-kontrol/urun-ara/", api_uretim_kontrol_urun_ara, name="api_uretim_kontrol_urun_ara"),
    path("api/uretim-kontrol/alt-parca/", api_uretim_kontrol_alt_parca, name="api_uretim_kontrol_alt_parca"),
    path("api/uretim-kontrol/plans/", api_uretim_kontrol_planlar, name="api_uretim_kontrol_planlar"),
    path("api/uretim-kontrol/plans/<int:pk>/", api_uretim_kontrol_plan_detay, name="api_uretim_kontrol_plan_detay"),
    path("api/uretim-kontrol/session/<int:session_pk>/result/", api_uretim_kontrol_session_result, name="api_uretim_kontrol_session_result"),
    path("api/uretim-kontrol/session/<int:session_pk>/finish/", api_uretim_kontrol_session_finish, name="api_uretim_kontrol_session_finish"),
    path("istasyon/<int:istasyon_id>/maliyet/", istasyon_maliyet_getir, name="istasyon_maliyet_getir"),
    # Talimatlar
    path("uretim/recete/<int:pk>/talimatlar/", recete_talimat_listesi, name="recete_talimat_listesi"),
    path("uretim/recete/<int:pk>/talimat-ekle/", recete_talimat_ekle, name="recete_talimat_ekle"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/duzenle/", recete_talimat_duzenle, name="recete_talimat_duzenle"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/sil/", recete_talimat_sil, name="recete_talimat_sil"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/olcu-ekle/", recete_talimat_olcu_ekle, name="recete_talimat_olcu_ekle"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/olcu/<int:olcu_id>/duzenle/", recete_talimat_olcu_duzenle, name="recete_talimat_olcu_duzenle"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/olcu/<int:olcu_id>/sil/", recete_talimat_olcu_sil, name="recete_talimat_olcu_sil"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/dosya-ekle/", recete_talimat_dosya_ekle, name="recete_talimat_dosya_ekle"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/dosya/<int:dosya_id>/sil/", recete_talimat_dosya_sil, name="recete_talimat_dosya_sil"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/ekipman-ekle/", recete_talimat_ekipman_ekle, name="recete_talimat_ekipman_ekle"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/ekipman/<int:ekipman_id>/sil/", recete_talimat_ekipman_sil, name="recete_talimat_ekipman_sil"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/fikstur-ekle/", recete_talimat_fikstur_ekle, name="recete_talimat_fikstur_ekle"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/fikstur/<int:fikstur_id>/sil/", recete_talimat_fikstur_sil, name="recete_talimat_fikstur_sil"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/olcu-aleti-ekle/", recete_talimat_olcu_aleti_ekle, name="recete_talimat_olcu_aleti_ekle"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/olcu-aleti/<int:olcu_aleti_id>/sil/", recete_talimat_olcu_aleti_sil, name="recete_talimat_olcu_aleti_sil"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/program-ekle/", recete_talimat_program_ekle, name="recete_talimat_program_ekle"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/program/<int:program_id>/sil/", recete_talimat_program_sil, name="recete_talimat_program_sil"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/aciklama-ekle/", recete_talimat_aciklama_ekle, name="recete_talimat_aciklama_ekle"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/aciklama/<int:aciklama_id>/duzenle/", recete_talimat_aciklama_duzenle, name="recete_talimat_aciklama_duzenle"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/aciklama/<int:aciklama_id>/sil/", recete_talimat_aciklama_sil, name="recete_talimat_aciklama_sil"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/kurulum-dosyasi-ekle/", recete_talimat_kurulum_dosyasi_ekle, name="recete_talimat_kurulum_dosyasi_ekle"),
    path("uretim/recete/<int:pk>/talimat/<int:talimat_id>/kurulum-dosyasi/<int:kurulum_dosyasi_id>/sil/", recete_talimat_kurulum_dosyasi_sil, name="recete_talimat_kurulum_dosyasi_sil"),
    path("uretim/recete/<int:pk>/kurulum-dosyalari/", recete_talimat_kurulum_dosyalari_listesi, name="recete_talimat_kurulum_dosyalari_listesi"),

    # Üretim Standartları
    path("uretim/standartlar/", uretim_standarti_listesi, name="uretim_standarti_listesi"),
    path("uretim/standartlar/ekle/", uretim_standarti_ekle, name="uretim_standarti_ekle"),
    path("uretim/standartlar/<int:pk>/", uretim_standarti_detay, name="uretim_standarti_detay"),
    path("uretim/standartlar/<int:pk>/duzenle/", uretim_standarti_duzenle, name="uretim_standarti_duzenle"),
    path("uretim/standartlar/<int:pk>/sil/", uretim_standarti_sil, name="uretim_standarti_sil"),
    path("uretim/standartlar/<int:pk>/revizyon-ekle/", uretim_standarti_revizyon_ekle, name="uretim_standarti_revizyon_ekle"),
    path("uretim/standartlar/<int:pk>/pdf-indir/", uretim_standarti_pdf_indir, name="uretim_standarti_pdf_indir"),
    path("uretim/standartlar/<int:pk>/pdf-sil/", uretim_standarti_pdf_sil, name="uretim_standarti_pdf_sil"),
    path("uretim/standartlar/arsiv/<int:pk>/pdf-indir/", uretim_standarti_arsiv_pdf_indir, name="uretim_standarti_arsiv_pdf_indir"),
    path("uretim/standartlar/<int:pk>/durum-degistir/", uretim_standarti_durum_degistir, name="uretim_standarti_durum_degistir"),
    
    # Kurulum Dosyaları
    path("uretim/kurulum-dosyalari/", kurulum_dosyalari_listesi, name="kurulum_dosyalari_listesi"),
    path("uretim/kurulum-dosyalari/ekle/", kurulum_dosyasi_ekle, name="kurulum_dosyasi_ekle"),
    path("uretim/kurulum-dosyalari/urun-ara/", kurulum_dosyasi_urun_ara, name="kurulum_dosyasi_urun_ara"),
    path("uretim/kurulum-dosyalari/urun/<int:urun_id>/recete-bilesenleri/", kurulum_dosyasi_recete_bilesenleri, name="kurulum_dosyasi_recete_bilesenleri"),
    path("uretim/kurulum-dosyalari/cnc-ekipman-secenekleri/", kurulum_dosyasi_cnc_ekipman_secenekleri_api, name="kurulum_dosyasi_cnc_ekipman_secenekleri"),
    path("uretim/kurulum-dosyalari/<int:pk>/", kurulum_dosyasi_detay, name="kurulum_dosyasi_detay"),
    path("uretim/kurulum-dosyalari/<int:pk>/duzenle/", kurulum_dosyasi_duzenle, name="kurulum_dosyasi_duzenle"),
    path("uretim/kurulum-dosyalari/<int:pk>/sil/", kurulum_dosyasi_sil, name="kurulum_dosyasi_sil"),
    path("uretim/kurulum-dosyalari/<int:pk>/pdf-indir/", kurulum_dosyasi_pdf_indir, name="kurulum_dosyasi_pdf_indir"),
    path("uretim/kurulum-dosyalari/<int:pk>/arsiv/", kurulum_dosyasi_arsiv_listesi, name="kurulum_dosyasi_arsiv_listesi"),
    path("uretim/kurulum-dosyalari/arsiv/<int:pk>/pdf-indir/", kurulum_dosyasi_arsiv_pdf_indir, name="kurulum_dosyasi_arsiv_pdf_indir"),
    
    # CNC Programlar
    path("uretim/cnc-programlar/", cnc_program_listesi, name="cnc_program_listesi"),
    path("uretim/cnc-programlar/ekle/", cnc_program_ekle, name="cnc_program_ekle"),
    path("uretim/cnc-programlar/urun-ara/", cnc_program_urun_ara, name="cnc_program_urun_ara"),
    path("uretim/cnc-programlar/<uuid:program_id>/", cnc_program_detay, name="cnc_program_detay"),
    path("uretim/cnc-programlar/<uuid:program_id>/duzenle/", cnc_program_duzenle, name="cnc_program_duzenle"),
    path("uretim/cnc-programlar/<uuid:program_id>/sil/", cnc_program_sil, name="cnc_program_sil"),
    path("uretim/cnc-programlar/<uuid:program_id>/revizyon-ekle/", cnc_program_revizyon_ekle, name="cnc_program_revizyon_ekle"),
    path("uretim/cnc-programlar/revizyon/<uuid:revision_id>/indir/", cnc_program_revizyon_indir, name="cnc_program_revizyon_indir"),
    path("uretim/cnc-programlar/revizyon/<uuid:revision_id>/rollback/", cnc_program_revizyon_rollback, name="cnc_program_revizyon_rollback"),
    path("api/cnc-programlar/urun/<int:product_id>/", api_cnc_programlar_urun, name="api_cnc_programlar_urun"),

    # CNC Dosya Ağacı
    path("uretim/cnc-dosya-agaci/", cnc_dosya_agaci_listesi, name="cnc_dosya_agaci_listesi"),
    path("uretim/cnc-dosya-agaci/makinalar/", cnc_dosya_agaci_makina_listesi, name="cnc_dosya_agaci_makina_listesi"),
    path("api/cnc-dosya-agaci/tree/", cnc_dosya_agaci_api_tree, name="cnc_dosya_agaci_api_tree"),
    path("api/cnc-dosya-agaci/klasor/ekle/", cnc_dosya_agaci_api_create, name="cnc_dosya_agaci_api_create"),
    path("api/cnc-dosya-agaci/klasor/<int:pk>/guncelle/", cnc_dosya_agaci_api_update, name="cnc_dosya_agaci_api_update"),
    path("api/cnc-dosya-agaci/klasor/<int:pk>/sil/", cnc_dosya_agaci_api_delete, name="cnc_dosya_agaci_api_delete"),
    path("api/cnc-dosya-agaci/klasor/<int:pk>/tasi/", cnc_dosya_agaci_api_move, name="cnc_dosya_agaci_api_move"),
    path("api/cnc-dosya-agaci/makina/ekle/", cnc_dosya_agaci_makina_ekle, name="cnc_dosya_agaci_makina_ekle"),
    path("api/cnc-dosya-agaci/makina/sil/", cnc_dosya_agaci_makina_sil, name="cnc_dosya_agaci_makina_sil"),
    path("api/cnc-dosya-agaci/makina/istasyonlar/", cnc_dosya_agaci_makina_api_istasyonlar, name="cnc_dosya_agaci_makina_api_istasyonlar"),
    # CNC Ekipmanlar
    path("uretim/cnc-ekipmanlar/", cnc_ekipman_listesi, name="cnc_ekipman_listesi"),
    path("uretim/cnc-ekipmanlar/ekle/", cnc_ekipman_ekle, name="cnc_ekipman_ekle"),
    path("uretim/cnc-ekipmanlar/<int:pk>/duzenle/", cnc_ekipman_duzenle, name="cnc_ekipman_duzenle"),
    path("uretim/cnc-ekipmanlar/<int:pk>/sil/", cnc_ekipman_sil, name="cnc_ekipman_sil"),

    # Ar-Ge Çalışmaları
    path("uretim/arge/projeler/", arge_proje_listesi, name="arge_proje_listesi"),
    path("uretim/arge/projeler/ekle/", arge_proje_ekle, name="arge_proje_ekle"),
    path("uretim/arge/projeler/<int:pk>/", arge_proje_detay, name="arge_proje_detay"),
    path("uretim/arge/projeler/<int:pk>/duzenle/", arge_proje_duzenle, name="arge_proje_duzenle"),
    path("uretim/arge/projeler/<int:pk>/arsivle/", arge_proje_arsivle, name="arge_proje_arsivle"),
    path("uretim/arge/revizyonlar/", arge_revizyon_listesi, name="arge_revizyon_listesi"),
    path("uretim/arge/projeler/<int:proje_pk>/revizyon/ekle/", arge_revizyon_ekle, name="arge_revizyon_ekle"),
    path("uretim/arge/revizyon/<int:pk>/duzenle/", arge_revizyon_duzenle, name="arge_revizyon_duzenle"),
    path("uretim/arge/revizyon/<int:pk>/sil/", arge_revizyon_sil, name="arge_revizyon_sil"),
    path("uretim/arge/dosyalar/", arge_dosya_listesi, name="arge_dosya_listesi"),
    path("uretim/arge/projeler/<int:pk>/dosya-ekle/", arge_dosya_ekle, name="arge_dosya_ekle"),
    path("uretim/arge/dosya/<int:pk>/indir/", arge_dosya_indir, name="arge_dosya_indir"),
    path("uretim/arge/dosya/<int:pk>/sil/", arge_dosya_sil, name="arge_dosya_sil"),
    path("uretim/arge/yakinda/", arge_asama_yakinda, name="arge_asama_yakinda"),

     # Stok işlemleri
    path("stok/ekle/", stok_ekle, name="stok_ekle"),
    path("stok/ekle/<int:pk>/", stok_ekle, name="stok_ekle"),  # Stok detay için
    path("stok/<int:pk>/qrcode/", stok_qrcode, name="stok_qrcode"),
    path("stok/<int:pk>/kopyala/", stok_kopyala, name="stok_kopyala"),
    path("stok/<int:pk>/recete-maliyetleri/", stok_recete_maliyetleri, name="stok_recete_maliyetleri"),
    path("stok/etiket-yazdir/", stok_etiket_yazdir, name="stok_etiket_yazdir"),
    path("stok/hizli-uretim/", views.stok_hizli_uretim_olustur, name="stok_hizli_uretim_olustur"),
    path("stok/duzenle/<int:pk>/", stok_duzenle, name="stok_duzenle"),
    path("stok/sil/<int:pk>/", stok_sil, name="stok_sil"),
    path("stok/<int:pk>/ek-dosya/<int:dosya_id>/sil/", stok_ek_dosya_sil, name="stok_ek_dosya_sil"),
    path("stok/toplu-sil/", stok_toplu_sil, name="stok_toplu_sil"),
    path("stok-listesi/", views.stok_listesi, name="stok_listesi"),
    path("stok-listesi/export/excel/", views.stok_listesi_export_excel, name="stok_listesi_export_excel"),
    path("stok-listesi/export/pdf/", views.stok_listesi_export_pdf, name="stok_listesi_export_pdf"),
    path("stok/tamamlanma-raporu/", stok_tamamlanma_raporu, name="stok_tamamlanma_raporu"),
    path("stok/tamamlanma-raporu/export/excel/", stok_tamamlanma_raporu_export_excel, name="stok_tamamlanma_raporu_export_excel"),
    path("stok/tamamlanma-raporu/export/pdf/", stok_tamamlanma_raporu_export_pdf, name="stok_tamamlanma_raporu_export_pdf"),
    path("ayarlar/stok-tamamlanma/", stok_tamamlanma_ayarlari, name="stok_tamamlanma_ayarlari"),
    path("giris/", stok_giris, name="stok_giris"),
    path("cikis/", stok_cikis, name="stok_cikis"),
    path("sayim/", stok_sayim_listesi, name="stok_sayim_listesi"),
    path("sayim/yeni/", stok_sayim_baslat, name="stok_sayim_baslat"),
    path("sayim/<int:pk>/basla/", stok_sayim_basla, name="stok_sayim_basla"),
    path("sayim/<int:pk>/say/", stok_sayim_calis, name="stok_sayim_calis"),
    path("sayim/<int:pk>/rapor/", stok_sayim_rapor, name="stok_sayim_rapor"),
    path("sayim/<int:pk>/rapor/excel/", stok_sayim_rapor_excel, name="stok_sayim_rapor_excel"),
    path("sayim/<int:pk>/rapor/pdf/", stok_sayim_rapor_pdf, name="stok_sayim_rapor_pdf"),
    path("sayim/<int:pk>/iptal/", stok_sayim_iptal, name="stok_sayim_iptal"),
    path("sayim/<int:pk>/sil/", stok_sayim_sil, name="stok_sayim_sil"),
    path("hareketler/", stok_hareket_listesi, name="stok_hareket_listesi"),
    path("hareketler/toplu/", stok_toplu_hareket, name="stok_toplu_hareket"),
    path("hareketler/export/excel/", stok_hareket_listesi_export_excel, name="stok_hareket_listesi_export_excel"),
    path("hareketler/export/pdf/", stok_hareket_listesi_export_pdf, name="stok_hareket_listesi_export_pdf"),
    path("hareketler/duzenle/<int:pk>/", stok_hareket_duzenle, name="stok_hareket_duzenle"),
    path("hareketler/sil/<int:pk>/", stok_hareket_sil, name="stok_hareket_sil"),
    path("transfer/", stok_transfer, name="stok_transfer"),  # ← Bu satırı ekleyin
    path("transfer/liste/", stok_transfer_listesi, name="stok_transfer_listesi"),  # ← Bu satırı ekleyin
    path("detay/<int:pk>/", stok_detay, name="stok_detay"),

    # Raporlar
    path("rapor/kritik-stok/", views.kritik_stok_raporu, name="kritik_stok_raporu"),
    path("rapor/kritik-stok/excel/", views.kritik_stok_raporu_excel, name="kritik_stok_raporu_excel"),
    path("rapor/kritik-stok/pdf/", views.kritik_stok_raporu_pdf, name="kritik_stok_raporu_pdf"),
    path("rapor/stok-hareket/", views.stok_hareket_raporu, name="stok_hareket_raporu"),
    path("rapor/stok-hareket/excel/", views.stok_hareket_raporu_excel, name="stok_hareket_raporu_excel"),
    path("rapor/stok-hareket/pdf/", views.stok_hareket_raporu_pdf, name="stok_hareket_raporu_pdf"),

    # Excel import / export
    path("excel/import/", views.excel_import_page, name="excel_import_page"),
    path("excel/import-stok/", views.import_stok_excel, name="import_stok_excel"),
    path("excel/export-stok/", views.export_stok_listesi, name="export_stok_listesi"),
    path("excel/export-hareketler/", views.export_stok_hareketleri, name="export_stok_hareketleri"),
    path("excel/template/", views.download_template, name="download_template"),

    # Barkod
    path("barkod/sorgula/", views.barkod_sorgula, name="barkod_sorgula"),
    path("barkod/olustur/<str:stok_kodu>/", views.barkod_olustur, name="barkod_olustur"),
    path("barkod/arayuz/", views.barkod_arayuzu, name="barkod_arayuzu"),

    # Cariler
    path("cariler/", views.cariler_liste, name="cariler_liste"),
    path("cariler/ekle/", views.cari_ekle, name="cari_ekle"),
    path("cariler/duzenle/<int:cari_id>/", views.cari_duzenle, name="cari_duzenle"),

    # API
    path("api/check-stok-kodu/", api_check_stok_kodu, name="api_check_stok_kodu"),
    path("api/shelves/", api_shelves, name="api_shelves"),
    path("api/stok-fiyat/<int:pk>/", api_stok_fiyat, name="api_stok_fiyat"),
    path("api/quick-add/<str:kind>/", api_quick_add, name="api_quick_add"),
    path("api/personel/<int:pk>/", api_personel_bilgi, name="api_personel_bilgi"),

    # Kategori Yönetimi
    path("kategori/", kategori_listesi, name="kategori_listesi"),
    path("kategori/ekle/", kategori_ekle, name="kategori_ekle"),
    path("kategori/duzenle/<int:pk>/", kategori_duzenle, name="kategori_duzenle"),
    path("kategori/sil/<int:pk>/", kategori_sil, name="kategori_sil"),
    
    # Tedarikçi Yönetimi
    path("tedarikci/", tedarikci_listesi, name="tedarikci_listesi"),
    path("tedarikci/ekle/", tedarikci_ekle, name="tedarikci_ekle"),
    path("tedarikci/<int:pk>/stoklar/", tedarikci_stoklari, name="tedarikci_stoklari"),
    path("tedarikci/duzenle/<int:pk>/", tedarikci_duzenle, name="tedarikci_duzenle"),
    path("tedarikci/sil/<int:pk>/", tedarikci_sil, name="tedarikci_sil"),
    
    # Birim Yönetimi
    path("birim/", birim_listesi, name="birim_listesi"),
    path("birim/ekle/", birim_ekle, name="birim_ekle"),
    path("birim/duzenle/<int:pk>/", birim_duzenle, name="birim_duzenle"),
    path("birim/sil/<int:pk>/", birim_sil, name="birim_sil"),

    # Para Birimi Yönetimi
    path("para-birimi/", para_birimi_listesi, name="para_birimi_listesi"),
    path("para-birimi/ekle/", para_birimi_ekle, name="para_birimi_ekle"),
    path("para-birimi/duzenle/<int:pk>/", para_birimi_duzenle, name="para_birimi_duzenle"),
    path("para-birimi/sil/<int:pk>/", para_birimi_sil, name="para_birimi_sil"),

    # Ayarlar
    path("ayarlar/hata-raporlari/", hata_raporlari, name="hata_raporlari"),
    path("ayarlar/hata-raporlari/<int:pk>/coz/", hata_raporu_coz, name="hata_raporu_coz"),
    path("ayarlar/hata-raporlari/<int:pk>/sil/", hata_raporu_sil, name="hata_raporu_sil"),
    path("ayarlar/veri-yedekleme/", veri_yedekleme, name="veri_yedekleme"),
    path("ayarlar/mobil/", yapim_asamasinda, {'modul': 'mobil'}, name="ayarlar_mobil"),
    path("ayarlar/abonelik/", yapim_asamasinda, {'modul': 'abonelik'}, name="ayarlar_abonelik"),
    path("ayarlar/tum-verileri-sil/", yapim_asamasinda, {'modul': 'tum-verileri-sil'}, name="ayarlar_tum_verileri_sil"),
    path("ayarlar/genel/", genel_ayarlar, name="genel_ayarlar"),
    path("ayarlar/genel/cc-test-mail/", genel_ayarlar_cc_test_mail, name="genel_ayarlar_cc_test_mail"),
    path("ayarlar/genel/smtp-test-mail/", genel_ayarlar_smtp_test_mail, name="genel_ayarlar_smtp_test_mail"),
    path("ayarlar/genel/imap-test/", genel_ayarlar_imap_test, name="genel_ayarlar_imap_test"),
    path("ayarlar/gelistirme-talepleri/", gelistirme_talep_listesi, name="gelistirme_talep_listesi"),
    path("ayarlar/gelistirme-talepleri/ekle/", gelistirme_talep_ekle, name="gelistirme_talep_ekle"),
    path("ayarlar/gelistirme-talepleri/<int:pk>/duzenle/", gelistirme_talep_duzenle, name="gelistirme_talep_duzenle"),
    path("ayarlar/gelistirme-talepleri/<int:pk>/kapat/", gelistirme_talep_kapat, name="gelistirme_talep_kapat"),
    path("ayarlar/yetkilendirme/roller/", yetkilendirme_roller, name="yetkilendirme_roller"),
    path("ayarlar/yetkilendirme/roller/ekle/", yetkilendirme_rol_ekle, name="yetkilendirme_rol_ekle"),
    path("ayarlar/yetkilendirme/roller/<int:pk>/duzenle/", yetkilendirme_rol_duzenle, name="yetkilendirme_rol_duzenle"),
    path("ayarlar/yetkilendirme/roller/<int:pk>/sil/", yetkilendirme_rol_sil, name="yetkilendirme_rol_sil"),
    path("ayarlar/yetkilendirme/kullanicilar/", yetkilendirme_kullanicilar, name="yetkilendirme_kullanicilar"),
    path("ayarlar/yetkilendirme/kullanicilar/<int:pk>/roller/", yetkilendirme_kullanici_roller, name="yetkilendirme_kullanici_roller"),
    path("ayarlar/yetkilendirme/yetkiler/", yetkilendirme_yetkiler, name="yetkilendirme_yetkiler"),
    
    # Yedekleme ve Geri Yükleme
    path("ayarlar/yedekle/altyapi/", yedekle_altyapi, name="yedekle_altyapi"),
    path("ayarlar/yedekle/veriler/", yedekle_veriler, name="yedekle_veriler"),
    path("ayarlar/geri-yukle/altyapi/", geri_yukle_altyapi, name="geri_yukle_altyapi"),
    path("ayarlar/geri-yukle/veriler/", geri_yukle_veriler, name="geri_yukle_veriler"),
    
    # Skala Suite Entegrasyon
    path("ayarlar/skala-entegrasyon/", skala_entegrasyon, name="skala_entegrasyon"),
    path("ayarlar/skala-entegrasyon/stok-export/", skala_stok_export, name="skala_stok_export"),
    path("ayarlar/skala-entegrasyon/cari-export/", skala_cari_export, name="skala_cari_export"),
    path("ayarlar/skala-entegrasyon/recete-export/", skala_recete_export, name="skala_recete_export"),
    
    # Yazdırma Şablonları
    path("ayarlar/yazdirma-sablonlari/", yazdirma_sablonlari_listesi, name="yazdirma_sablonlari_listesi"),
    path("ayarlar/yazdirma-sablonu/<int:pk>/duzenle/", yazdirma_sablonu_duzenle, name="yazdirma_sablonu_duzenle"),
    path("ayarlar/yazdirma-sablonu/<int:pk>/onizle/", yazdirma_sablonu_onizleme, name="yazdirma_sablonu_onizleme"),
    path("ayarlar/yazdirma-sablonu/<int:pk>/api-save/", yazdirma_sablonu_api_save, name="yazdirma_sablonu_api_save"),
    
    # Veri İçe Aktarma
    path("ayarlar/veri-ice-aktarma/", veri_ice_aktarma, name="veri_ice_aktarma"),
    path("ayarlar/veri-ice-aktarma/stok-sablon/", download_stok_template, name="download_stok_template"),
    path("ayarlar/veri-ice-aktarma/tedarikci-sablon/", download_tedarikci_template, name="download_tedarikci_template"),
    path("ayarlar/veri-ice-aktarma/musteri-sablon/", download_musteri_template, name="download_musteri_template"),
    path("ayarlar/veri-ice-aktarma/stok-yukle/", import_stok_excel, name="import_stok_excel"),
    path("ayarlar/veri-ice-aktarma/tedarikci-yukle/", import_tedarikci_excel, name="import_tedarikci_excel"),
    path("ayarlar/veri-ice-aktarma/musteri-yukle/", import_musteri_excel, name="import_musteri_excel"),

    # Kullanıcı Yönetimi
    path("kullanici/", kullanici_listesi, name="kullanici_listesi"),
    path("kullanici/ekle/", kullanici_ekle, name="kullanici_ekle"),
    path("kullanici/duzenle/<int:pk>/", kullanici_duzenle, name="kullanici_duzenle"),
    path("kullanici/sil/<int:pk>/", kullanici_sil, name="kullanici_sil"),
    path("kullanici/sifre-sifirla/<int:pk>/", kullanici_sifre_sifirla, name="kullanici_sifre_sifirla"),

    # Operasyon Yönetimi
    path("operasyon/", operasyon_listesi, name="operasyon_listesi"),
    path("operasyon/ekle/", operasyon_ekle, name="operasyon_ekle"),
    path("operasyon/duzenle/<int:pk>/", operasyon_duzenle, name="operasyon_duzenle"),
    path("operasyon/sil/<int:pk>/", operasyon_sil, name="operasyon_sil"),
    path("operasyon/<int:pk>/durum-degistir/", operasyon_durum_degistir, name="operasyon_durum_degistir"),

    # Dış Operasyon Tipi Yönetimi (Ayarlar)
    path("dis-operasyon/", dis_operasyon_tipi_listesi, name="dis_operasyon_tipi_listesi"),
    path("dis-operasyon/ekle/", dis_operasyon_tipi_ekle_sayfa, name="dis_operasyon_tipi_ekle_sayfa"),
    path("dis-operasyon/duzenle/<int:pk>/", dis_operasyon_tipi_duzenle, name="dis_operasyon_tipi_duzenle"),
    path("dis-operasyon/sil/<int:pk>/", dis_operasyon_tipi_sil, name="dis_operasyon_tipi_sil"),
    path("dis-operasyon/<int:pk>/durum-degistir/", dis_operasyon_tipi_durum_degistir, name="dis_operasyon_tipi_durum_degistir"),

    # İstasyon Yönetimi
    path("istasyon/", istasyon_listesi, name="istasyon_listesi"),
    path("istasyon/ekle/", istasyon_ekle, name="istasyon_ekle"),
    path("istasyon/duzenle/<int:pk>/", istasyon_duzenle, name="istasyon_duzenle"),
    path("istasyon/sil/<int:pk>/", istasyon_sil, name="istasyon_sil"),
    path("istasyon/<int:pk>/durum-degistir/", istasyon_durum_degistir, name="istasyon_durum_degistir"),
    
    # Ekipmanlar
    path("ekipman/", ekipman_listesi, name="ekipman_listesi"),
    path("ekipman/ekle/", ekipman_ekle, name="ekipman_ekle"),
    path("ekipman/duzenle/<int:pk>/", ekipman_duzenle, name="ekipman_duzenle"),
    path("ekipman/sil/<int:pk>/", ekipman_sil, name="ekipman_sil"),
    path("ekipman/<int:pk>/durum-degistir/", ekipman_durum_degistir, name="ekipman_durum_degistir"),
    
    # Fikstürler
    path("fikstur/", fikstur_listesi, name="fikstur_listesi"),
    path("fikstur/ekle/", fikstur_ekle, name="fikstur_ekle"),
    path("fikstur/duzenle/<int:pk>/", fikstur_duzenle, name="fikstur_duzenle"),
    path("fikstur/sil/<int:pk>/", fikstur_sil, name="fikstur_sil"),
    path("fikstur/<int:pk>/durum-degistir/", fikstur_durum_degistir, name="fikstur_durum_degistir"),

    # Ölçü Aletleri
    path("olcu-aleti/", olcu_aleti_listesi, name="olcu_aleti_listesi"),
    path("olcu-aleti/dashboard/", olcu_aleti_dashboard, name="olcu_aleti_dashboard"),
    path("olcu-aleti/export-pdf/", olcu_aleti_export_pdf, name="olcu_aleti_export_pdf"),
    path("olcu-aleti/ekle/", olcu_aleti_ekle, name="olcu_aleti_ekle"),
    path("olcu-aleti/duzenle/<int:pk>/", olcu_aleti_duzenle, name="olcu_aleti_duzenle"),
    path("olcu-aleti/sil/<int:pk>/", olcu_aleti_sil, name="olcu_aleti_sil"),
    path("olcu-aleti/<int:pk>/durum-degistir/", olcu_aleti_durum_degistir, name="olcu_aleti_durum_degistir"),
    path("olcu-aleti/<int:alet_id>/kalibrasyon-ekle/", kalibrasyon_ekle, name="kalibrasyon_ekle"),
    
    # Ölçü Aleti Türleri
    path("olcu-aleti-turu/", olcu_aleti_turu_listesi, name="olcu_aleti_turu_listesi"),
    path("olcu-aleti-turu/ekle/", olcu_aleti_turu_ekle, name="olcu_aleti_turu_ekle"),
    path("olcu-aleti-turu/duzenle/<int:pk>/", olcu_aleti_turu_duzenle, name="olcu_aleti_turu_duzenle"),
    path("olcu-aleti-turu/sil/<int:pk>/", olcu_aleti_turu_sil, name="olcu_aleti_turu_sil"),

    # Kalite Yönetimi - Şikayet/Uygunsuzluk
    path("uretim/kalite/sikayetler/", complaint_listesi, name="complaint_listesi"),
    path("uretim/kalite/sikayet/<int:pk>/", complaint_detay, name="complaint_detay"),
    path("uretim/kalite/sikayet/ekle/", complaint_ekle, name="complaint_ekle"),
    path("uretim/kalite/sikayet/<int:pk>/duzenle/", complaint_duzenle, name="complaint_duzenle"),
    path("uretim/kalite/sikayet/<int:pk>/sil/", complaint_sil, name="complaint_sil"),
    path("uretim/kalite/sikayet/<int:complaint_id>/ekle-attachment/", complaint_ekle_attachment, name="complaint_ekle_attachment"),
    
    # CAPA Aksiyonları
    path("uretim/kalite/sikayet/<int:complaint_id>/capa-ekle/", capa_action_ekle, name="capa_action_ekle"),
    path("uretim/kalite/capa/<int:pk>/duzenle/", capa_action_duzenle, name="capa_action_duzenle"),
    path("uretim/kalite/capa/<int:pk>/sil/", capa_action_sil, name="capa_action_sil"),
    
    # ECO (Engineering Change Order)
    path("uretim/kalite/eco/", eco_listesi, name="eco_listesi"),
    path("uretim/kalite/eco/<int:pk>/", eco_detay, name="eco_detay"),
    path("uretim/kalite/eco/ekle/", eco_ekle, name="eco_ekle"),
    path("uretim/kalite/eco/<int:pk>/duzenle/", eco_duzenle, name="eco_duzenle"),
    path("uretim/kalite/eco/<int:pk>/onayla/", eco_onayla, name="eco_onayla"),
    path("uretim/kalite/eco/<int:pk>/reddet/", eco_reddet, name="eco_reddet"),
    path("uretim/kalite/eco/<int:pk>/sil/", eco_sil, name="eco_sil"),
    
    # Üretim Uyarı Kuralları
    path("uretim/kalite/uyarilar/", alert_rule_listesi, name="alert_rule_listesi"),
    path("uretim/kalite/uyari/ekle/", alert_rule_ekle, name="alert_rule_ekle"),
    path("uretim/kalite/uyari/<int:pk>/duzenle/", alert_rule_duzenle, name="alert_rule_duzenle"),
    path("uretim/kalite/uyari/<int:pk>/sil/", alert_rule_sil, name="alert_rule_sil"),
    
    # Kontrol Planları
    path("kalite/kontrol-planlari/", control_plan_listesi, name="control_plan_listesi"),
    path("kalite/kontrol-plani/<int:pk>/", control_plan_detay, name="control_plan_detay"),
    path("kalite/kontrol-plani/ekle/", control_plan_ekle, name="control_plan_ekle"),
    path("kalite/kontrol-plani/<int:plan_id>/item-ekle/", control_item_ekle, name="control_item_ekle"),
    
    # Üretim Süreci Kontrol (In-Process Inspection)
    path("kalite/uretim-sureci-kontrol/", inspection_dashboard, name="inspection_dashboard"),
    path("kalite/inspection/work-order/<int:work_order_pk>/", work_order_inspection_listesi, name="work_order_inspection_listesi"),
    path("kalite/inspection/work-order/<int:work_order_pk>/operation/<int:operation_step_pk>/ekle/", inspection_ekle_modal, name="inspection_ekle_modal"),
    
    # API Endpoints
    path("api/kalite/uyarilar/", api_get_alerts, name="api_get_alerts"),
    path("api/kalite/inspection/required/<int:work_order_pk>/<int:operation_step_pk>/", api_get_required_inspections, name="api_get_required_inspections"),
    path("api/kalite/inspection/item/<int:item_pk>/", api_get_control_item, name="api_get_control_item"),
    path("api/kalite/instruments/valid/", api_get_valid_instruments, name="api_get_valid_instruments"),

    # Araç Yönetimi
    path("arac/", arac_listesi, name="arac_listesi"),
    path("arac/ekle/", arac_ekle, name="arac_ekle"),
    path("arac/<int:pk>/", arac_detay, name="arac_detay"),
    path("arac/<int:pk>/duzenle/", arac_duzenle, name="arac_duzenle"),
    path("arac/<int:pk>/sil/", arac_sil, name="arac_sil"),
    path("api/arac/belge-turu/ekle/", api_arac_belge_turu_ekle, name="api_arac_belge_turu_ekle"),
    path("arac/<int:arac_pk>/belge/ekle/", arac_belgesi_ekle, name="arac_belgesi_ekle"),
    path("arac/belge/<int:pk>/duzenle/", arac_belgesi_duzenle, name="arac_belgesi_duzenle"),
    path("arac/belge/<int:pk>/guncelle/", arac_belgesi_guncelle, name="arac_belgesi_guncelle"),
    path("arac/belge/<int:pk>/sil/", arac_belgesi_sil, name="arac_belgesi_sil"),

    # Gayrimenkul yönetimi
    path("gayrimenkul/", gayrimenkul_listesi, name="gayrimenkul_listesi"),
    path("gayrimenkul/ekle/", gayrimenkul_ekle, name="gayrimenkul_ekle"),
    path("gayrimenkul/<int:pk>/", gayrimenkul_detay, name="gayrimenkul_detay"),
    path("gayrimenkul/<int:pk>/duzenle/", gayrimenkul_duzenle, name="gayrimenkul_duzenle"),
    path("gayrimenkul/<int:pk>/arsivle/", gayrimenkul_arsivle, name="gayrimenkul_arsivle"),
    path("gayrimenkul/<int:gm_pk>/islem/ekle/", gayrimenkul_islem_ekle, name="gayrimenkul_islem_ekle"),
    path("gayrimenkul/islem/<int:pk>/duzenle/", gayrimenkul_islem_duzenle, name="gayrimenkul_islem_duzenle"),
    path("gayrimenkul/<int:gm_pk>/dosya/ekle/", gayrimenkul_dosya_ekle, name="gayrimenkul_dosya_ekle"),

    # Sigorta Yönetimi
    path("sigorta/", sigorta_listesi, name="sigorta_listesi"),
    path("sigorta/ekle/", sigorta_ekle, name="sigorta_ekle"),
    path("sigorta/duzenle/<int:pk>/", sigorta_duzenle, name="sigorta_duzenle"),
    path("sigorta/arsivle/<int:pk>/", sigorta_arsivle, name="sigorta_arsivle"),
    path("sigorta/sil/<int:pk>/", sigorta_sil, name="sigorta_sil"),

    # Personel Yönetimi
    path("personel/", personel_listesi, name="personel_listesi"),
    path("personel/ekle/", personel_ekle, name="personel_ekle"),
    path("personel/duzenle/<int:pk>/", personel_duzenle, name="personel_duzenle"),
    path("personel/<int:pk>/", personel_detay, name="personel_detay"),
    path("personel/<int:pk>/belgeler/", personel_belgeleri, name="personel_belgeleri"),
    path("personel/<int:pk>/belgeler/ekle/", personel_belgesi_ekle, name="personel_belgesi_ekle"),
    path("personel/belge/<int:pk>/duzenle/", personel_belgesi_duzenle, name="personel_belgesi_duzenle"),
    path("personel/belge/<int:pk>/arsivle/", personel_belgesi_arsivle, name="personel_belgesi_arsivle"),
    path("personel/belge/<int:pk>/sil/", personel_belgesi_sil, name="personel_belgesi_sil"),
    path("gunluk-calisma/", gunluk_calisma_listesi, name="gunluk_calisma_listesi"),
    path("gunluk-calisma/ekle/", gunluk_calisma_ekle, name="gunluk_calisma_ekle"),
    path("gunluk-calisma/duzenle/<int:pk>/", gunluk_calisma_duzenle, name="gunluk_calisma_duzenle"),
    path("gunluk-calisma/sil/<int:pk>/", gunluk_calisma_sil, name="gunluk_calisma_sil"),
    path("personel-izin/", personel_izin_listesi, name="personel_izin_listesi"),
    path("personel-izin/<int:pk>/duzenle/", personel_izin_duzenle, name="personel_izin_duzenle"),
    path("personel-izin/<int:pk>/sil/", personel_izin_sil, name="personel_izin_sil"),
    path("avans-odeme/ekle/", avans_odeme_ekle, name="avans_odeme_ekle"),
    path("avans-odeme/duzenle/<int:pk>/", avans_odeme_duzenle, name="avans_odeme_duzenle"),
    path("avans-odeme/sil/<int:pk>/", avans_odeme_sil, name="avans_odeme_sil"),

    # Sipariş Yönetimi
    path("siparis/", siparis_listesi, name="siparis_listesi"),
    path("siparis/teslimat-bekleyen-kalemleri/export/pdf/", teslimat_bekleyen_kalemleri_export_pdf, name="teslimat_bekleyen_kalemleri_export_pdf"),
    path("siparis/ekle/", siparis_ekle, name="siparis_ekle"),
    path("siparis/detay/<int:pk>/", siparis_detay, name="siparis_detay"),
    path("siparis/<int:pk>/uretim-emri-olustur/", siparis_uretim_emri_olustur, name="siparis_uretim_emri_olustur"),
    path("siparis/<int:pk>/start-production/", start_production_from_order, name="start_production_from_order"),
    path("siparis/<int:pk>/fulfill-from-stock/", fulfill_from_stock, name="fulfill_from_stock"),
    path("siparis/<int:pk>/fulfill-from-inproduction/", fulfill_from_inproduction, name="fulfill_from_inproduction"),
    path("siparis/<int:pk>/produce-remaining/", produce_remaining, name="produce_remaining"),
    path("siparis/<int:pk>/produce-full/", produce_full, name="produce_full"),
    path("siparis/<int:pk>/apply-kalem-kararlari/", apply_siparis_kalem_kararlari, name="apply_siparis_kalem_kararlari"),
    path("siparis/<int:pk>/items/", siparis_items_api, name="siparis_items_api"),
    path("siparis/<int:pk>/onayla/", siparis_onayla, name="siparis_onayla"),
    path("siparis/<int:pk>/onay-mail/alicilar/", siparis_onay_mail_alici_sec, name="siparis_onay_mail_alici_sec"),
    path("siparis/<int:pk>/onay-mail/onay/", siparis_onay_mail_onay, name="siparis_onay_mail_onay"),
    path("siparis/<int:pk>/reddet/", siparis_reddet, name="siparis_reddet"),
    path("siparis/<int:pk>/teslim-et/", siparis_teslim_et, name="siparis_teslim_et"),
    path("siparis/duzenle/<int:pk>/", siparis_duzenle, name="siparis_duzenle"),
    path("siparis/sil/<int:pk>/", siparis_sil, name="siparis_sil"),
    path("siparis/maliyetler/", siparis_maliyetleri_listesi, name="siparis_maliyetleri_listesi"),
    path("siparis/<int:pk>/maliyetler/", siparis_maliyetleri, name="siparis_maliyetleri"),
    path("siparis/<int:pk>/maliyetler/pdf/", siparis_maliyetleri_export_pdf, name="siparis_maliyetleri_export_pdf"),
    path("siparis/<int:pk>/maliyet/<int:maliyet_id>/duzenle/", siparis_maliyeti_duzenle, name="siparis_maliyeti_duzenle"),
    path("siparis/<int:pk>/maliyet/<int:maliyet_id>/sil/", siparis_maliyeti_sil, name="siparis_maliyeti_sil"),

    path("siparis/teklifler/", teklif_listesi, name="teklif_listesi"),
    path("siparis/teklifler/sartlar-onizle/", teklif_sartlari_onizle, name="teklif_sartlari_onizle"),
    path("siparis/teklifler/ekle/", teklif_ekle, name="teklif_ekle"),
    path("siparis/teklifler/<int:pk>/", teklif_detay, name="teklif_detay"),
    path("siparis/teklifler/<int:pk>/pdf/", teklif_pdf_indir, name="teklif_pdf_indir"),
    path("siparis/teklifler/<int:pk>/duzenle/", teklif_duzenle, name="teklif_duzenle"),
    path("siparis/teklifler/<int:pk>/sil/", teklif_sil, name="teklif_sil"),
    path("siparis/teklifler/<int:pk>/gonder/", teklif_gonder, name="teklif_gonder"),
    path("siparis/teklifler/<int:pk>/gonder/alicilar/", teklif_mail_alici_sec, name="teklif_mail_alici_sec"),
    path("siparis/teklifler/<int:pk>/gonder/onay/", teklif_mail_onay, name="teklif_mail_onay"),
    path("siparis/teklifler/<int:pk>/onay-kalemleri/", teklif_onay_kalemler_json, name="teklif_onay_kalemleri"),
    path("siparis/teklifler/<int:pk>/onayla/", teklif_musteri_cevabi_onay, name="teklif_onayla"),
    path("siparis/teklifler/<int:pk>/reddet/", teklif_musteri_cevabi_red, name="teklif_reddet"),
    
    # Satın Alma Yönetimi
    path("satinalma/", satinalma_listesi, name="satinalma_listesi"),
    path("satinalma/ekle/", satinalma_ekle, name="satinalma_ekle"),
    path("satinalma/uretim-malzemesi-planla/", uretim_malzemesi_planla, name="uretim_malzemesi_planla"),
    path("satinalma/uretim-malzemesi-planla/pdf/", uretim_malzemesi_planla_pdf, name="uretim_malzemesi_planla_pdf"),
    path("satinalma/detay/<int:pk>/", satinalma_detay, name="satinalma_detay"),
    path("satinalma/<int:pk>/items/", satinalma_items_api, name="satinalma_items_api"),
    path("satinalma/duzenle/<int:pk>/", satinalma_duzenle, name="satinalma_duzenle"),
    path("satinalma/sil/<int:pk>/", satinalma_sil, name="satinalma_sil"),
    path("satinalma/tamamini-teslim/<int:pk>/", satinalma_tamamini_teslim, name="satinalma_tamamini_teslim"),
    path("satinalma/ksimi-teslim/<int:pk>/", satinalma_ksimi_teslim, name="satinalma_ksimi_teslim"),
    path("satinalma/ksimi-teslim-modal/<int:pk>/", satinalma_ksimi_teslim_modal, name="satinalma_ksimi_teslim_modal"),
    path("satinalma/<int:pk>/detay-popup/", satinalma_detay_popup, name="satinalma_detay_popup"),
    path("satinalma/<int:pk>/kismi-teslimat/", satinalma_kismi_teslimat, name="satinalma_kismi_teslimat"),
    path("satinalma/<int:pk>/tam-teslimat/", satinalma_tam_teslimat, name="satinalma_tam_teslimat"),
    path("satinalma/teklif-talep-formu/", teklif_talep_formu, name="teklif_talep_formu"),
    path("satinalma/teklif-talep-formu-pdf/", teklif_talep_formu_pdf, name="teklif_talep_formu_pdf"),
    path("satinalma/teklif-talep-formu-email/", teklif_talep_formu_email, name="teklif_talep_formu_email"),
    path("satinalma/mail/alici-sec/", satinalma_mail_alici_sec, name="satinalma_mail_alici_sec"),
    path("satinalma/mail/onay/", satinalma_mail_onay, name="satinalma_mail_onay"),
    path("satinalma/teklif-formu-teknik-resim-isle/", teklif_formu_teknik_resim_isle, name="teklif_formu_teknik_resim_isle"),
    path("satinalma/<int:pk>/teklif-girisi/", teklif_girisi, name="teklif_girisi"),
    path("satinalma/siparis-formu/", siparis_formu, name="siparis_formu"),
    path("satinalma/siparis-formu-pdf/", siparis_formu_pdf, name="siparis_formu_pdf"),
    path("satinalma/siparis-formu-email/", siparis_formu_email, name="siparis_formu_email"),
    path("satinalma/talepler/", talep_listesi, name="talep_listesi"),
    path("satinalma/talepler/ekle/", talep_ekle, name="talep_ekle"),
    path("satinalma/talepler/<int:pk>/", talep_detay, name="talep_detay"),
    path("satinalma/talepler/<int:pk>/duzenle/", talep_duzenle, name="talep_duzenle"),
    path("satinalma/talepler/<int:pk>/durum/", talep_durum_aksiyon, name="talep_durum_aksiyon"),
    path("satinalma/talepler/<int:pk>/satinalmaya-aktar/", talep_satinalmaya_aktar, name="talep_satinalmaya_aktar"),
    path("satinalma/talepler/<int:pk>/kapat/", talep_kapat, name="talep_kapat"),
    path("satinalma/talepler/<int:pk>/arsivle/", talep_arsivle, name="talep_arsivle"),

    # RFQ (Teklif Talebi) — çoklu tedarikçili teklif yönetimi
    path("satinalma/rfq/yeni/", rfq_olustur, name="rfq_olustur"),
    path("satinalma/rfq/<int:pk>/", rfq_detay, name="rfq_detay"),
    path("satinalma/rfq/<int:pk>/duzenle/", rfq_duzenle, name="rfq_duzenle"),
    path("satinalma/rfq/<int:pk>/sil/", rfq_sil, name="rfq_sil"),
    path("satinalma/rfq/oneri-tedarikciler/", rfq_oneri_tedarikciler_api, name="rfq_oneri_tedarikciler_api"),
    path("satinalma/rfq/<int:pk>/mail/alici-sec/", rfq_mail_alici_sec, name="rfq_mail_alici_sec"),
    path("satinalma/rfq/<int:pk>/mail/gonder/", rfq_mail_gonder, name="rfq_mail_gonder"),
    path("satinalma/rfq/<int:pk>/teklif/<int:rfq_tedarikci_pk>/", rfq_teklif_girisi, name="rfq_teklif_girisi"),
    path("satinalma/rfq/<int:pk>/karsilastir/", rfq_karsilastirma, name="rfq_karsilastirma"),
    path("satinalma/rfq/<int:pk>/kazananlari-kaydet/", rfq_kazananlari_kaydet, name="rfq_kazananlari_kaydet"),
    path("satinalma/rfq/<int:pk>/siparise-donustur/", rfq_siparise_donustur, name="rfq_siparise_donustur"),
    path("satinalma/rfq/<int:pk>/siparis-mail/", rfq_siparis_mail_secimi, name="rfq_siparis_mail_secimi"),
    path("satinalma/rfq/<int:pk>/siparis-mail/<int:satinalma_pk>/baslat/", rfq_siparis_mail_baslat, name="rfq_siparis_mail_baslat"),
    path("satinalma/rfq/<int:pk>/siparis-mail/<int:satinalma_pk>/atla/", rfq_siparis_mail_atla, name="rfq_siparis_mail_atla"),

    # Tedarikçi Performans Raporu
    path("cariler/tedarikci-performans/", tedarikci_performans, name="tedarikci_performans"),

    # Müşteri Yönetimi
    path("musteri/", musteri_listesi, name="musteri_listesi"),
    path("musteri/ekle/", musteri_ekle, name="musteri_ekle"),
    path("musteri/<int:pk>/siparisler/", musteri_siparisleri, name="musteri_siparisleri"),
    path("musteri/duzenle/<int:pk>/", musteri_duzenle, name="musteri_duzenle"),
    path("musteri/sil/<int:pk>/", musteri_sil, name="musteri_sil"),
    
    # Finansal Süreçler - Aylık Ödemeler
    path("finansal/aylik-odemeler/", aylik_odemeler_listesi, name="aylik_odemeler_listesi"),
    path("finansal/aylik-odeme/ekle/", aylik_odeme_ekle, name="aylik_odeme_ekle"),
    path("finansal/aylik-odeme/<int:pk>/duzenle/", aylik_odeme_duzenle, name="aylik_odeme_duzenle"),
    path("finansal/aylik-odeme/<int:pk>/sil/", aylik_odeme_sil, name="aylik_odeme_sil"),
    path("finansal/aylik-odeme/<int:pk>/odendi/", aylik_odeme_odendi_isaretle, name="aylik_odeme_odendi_isaretle"),
    path("finansal/odeme-sekli-options/", get_odeme_sekli_options, name="get_odeme_sekli_options"),
    
    # Finansal Süreçler - Banka Hesapları
    path("finansal/banka-hesaplari/", banka_hesaplari_listesi, name="banka_hesaplari_listesi"),
    path("finansal/banka-hesabi/ekle/", banka_hesabi_ekle, name="banka_hesabi_ekle"),
    path("finansal/banka-hesabi/<int:pk>/duzenle/", banka_hesabi_duzenle, name="banka_hesabi_duzenle"),
    path("finansal/banka-hesabi/<int:pk>/sil/", banka_hesabi_sil, name="banka_hesabi_sil"),
    
    # Finansal Süreçler - Kredi Kartları
    path("finansal/kredi-kartlari/", kredi_kartlari_listesi, name="kredi_kartlari_listesi"),
    path("finansal/kredi-karti/ekle/", kredi_karti_ekle, name="kredi_karti_ekle"),
    path("finansal/kredi-karti/<int:pk>/duzenle/", kredi_karti_duzenle, name="kredi_karti_duzenle"),
    path("finansal/kredi-karti/<int:pk>/sil/", kredi_karti_sil, name="kredi_karti_sil"),
    
    # Belgeler
    path("belgeler/", document_listesi, name="document_listesi"),
    path("belgeler/dashboard/", document_dashboard, name="document_dashboard"),
    path("belgeler/ekle/", document_ekle, name="document_ekle"),
    path("belgeler/<int:pk>/", document_detay, name="document_detay"),
    path("belgeler/<int:pk>/duzenle/", document_duzenle, name="document_duzenle"),
    path("belgeler/<int:pk>/dosya-yukle/", document_dosya_yukle, name="document_dosya_yukle"),
    path("belgeler/dosya/<int:file_id>/indir/", document_dosya_indir, name="document_dosya_indir"),
    path("belgeler/turler/", document_type_listesi, name="document_type_listesi"),
    path("belgeler/turler/ekle/", document_type_ekle, name="document_type_ekle"),
    path("belgeler/turler/<int:pk>/duzenle/", document_type_duzenle, name="document_type_duzenle"),
    path("api/belge-turu/kategori/ekle/", api_document_type_category_ekle, name="api_document_type_category_ekle"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
