# Generated manually for In-Process Inspection module
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def migrate_controlitem_name(apps, schema_editor):
    """Mevcut ControlItem kayıtlarında name alanını measurement_name'den doldur"""
    ControlItem = apps.get_model('stokapp', 'ControlItem')
    db_alias = schema_editor.connection.alias
    for item in ControlItem.objects.using(db_alias).all():
        if not item.name and item.measurement_name:
            item.name = item.measurement_name
            item.save(update_fields=['name'], using=db_alias)
        elif not item.name:
            # measurement_name de yoksa plan ve step bilgisini kullan
            item.name = f"Kontrol {item.id}"
            item.save(update_fields=['name'], using=db_alias)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('stokapp', '0045_alertrule_complaint_capaaction_complaintattachment_and_more'),
    ]

    operations = [
        # ControlPlan: status ve description alanları ekle
        migrations.AddField(
            model_name='controlplan',
            name='status',
            field=models.CharField(choices=[('ACTIVE', 'Aktif'), ('INACTIVE', 'Pasif')], default='ACTIVE', max_length=20, verbose_name='Durum'),
        ),
        migrations.AddField(
            model_name='controlplan',
            name='description',
            field=models.TextField(blank=True, verbose_name='Açıklama'),
        ),
        
        # ControlItem: Yeni alanlar ekle (önce nullable ekle, sonra eski alanları nullable yap)
        migrations.AddField(
            model_name='controlitem',
            name='operation_step',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='control_items', to='stokapp.receteoperasyon', verbose_name='Operasyon Adımı'),
        ),
        # name alanını önce boş olarak ekle, sonra RunPython ile doldur
        migrations.AddField(
            model_name='controlitem',
            name='name',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='Kontrol Adı'),
        ),
        migrations.AddField(
            model_name='controlitem',
            name='inspection_type',
            field=models.CharField(choices=[('NUMERIC', 'Sayısal (Numeric)'), ('VISUAL', 'Görsel (Visual)'), ('FUNCTIONAL', 'Fonksiyonel (Functional)'), ('DOCUMENT', 'Dokümantasyon (Document)')], default='NUMERIC', max_length=20, verbose_name='Kontrol Tipi'),
        ),
        migrations.AddField(
            model_name='controlitem',
            name='unit',
            field=models.CharField(blank=True, max_length=50, verbose_name='Birim'),
        ),
        migrations.AddField(
            model_name='controlitem',
            name='nominal',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True, verbose_name='Nominal Değer'),
        ),
        migrations.AddField(
            model_name='controlitem',
            name='min_value',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True, verbose_name='Min. Değer'),
        ),
        migrations.AddField(
            model_name='controlitem',
            name='max_value',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True, verbose_name='Max. Değer'),
        ),
        migrations.AddField(
            model_name='controlitem',
            name='text_criteria',
            field=models.TextField(blank=True, verbose_name='Metin Kriterleri'),
        ),
        migrations.AddField(
            model_name='controlitem',
            name='frequency_type',
            field=models.CharField(choices=[('100_PERCENT', '100% (Her birim)'), ('FIRST_PIECE', 'İlk parça (First Piece)'), ('EVERY_N', 'Her N parça'), ('PER_LOT', 'Lot başına'), ('PER_SHIFT', 'Vardiya başına')], default='100_PERCENT', max_length=20, verbose_name='Frekans Tipi'),
        ),
        migrations.AddField(
            model_name='controlitem',
            name='frequency_n',
            field=models.IntegerField(blank=True, help_text='Her N parça için kullanılır', null=True, verbose_name='Frekans N Değeri'),
        ),
        migrations.AddField(
            model_name='controlitem',
            name='sample_size',
            field=models.IntegerField(blank=True, null=True, verbose_name='Örnek Boyutu'),
        ),
        migrations.AddField(
            model_name='controlitem',
            name='criticality',
            field=models.CharField(choices=[('CRITICAL', 'Kritik'), ('MAJOR', 'Önemli'), ('MINOR', 'Az Önemli')], default='MAJOR', max_length=20, verbose_name='Kritiklik'),
        ),
        migrations.AddField(
            model_name='controlitem',
            name='requires_instrument',
            field=models.BooleanField(default=False, verbose_name='Ölçü Aleti Gerekli'),
        ),
        migrations.AddField(
            model_name='controlitem',
            name='requires_attachment',
            field=models.BooleanField(default=False, verbose_name='Ek Dosya Gerekli'),
        ),
        migrations.AddField(
            model_name='controlitem',
            name='requires_ack',
            field=models.BooleanField(default=False, verbose_name='Onay Gerekli'),
        ),
        migrations.AddField(
            model_name='controlitem',
            name='display_order',
            field=models.IntegerField(default=0, verbose_name='Görüntüleme Sırası'),
        ),
        # created_at ve updated_at için önce default ile ekle (callable olarak)
        migrations.AddField(
            model_name='controlitem',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name='Oluşturulma Tarihi'),
        ),
        migrations.AddField(
            model_name='controlitem',
            name='updated_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        # Sonra auto_now ve auto_now_add ekle
        migrations.AlterField(
            model_name='controlitem',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name='Oluşturulma Tarihi'),
        ),
        migrations.AlterField(
            model_name='controlitem',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        
        # Eski alanları nullable yap (geriye dönük uyumluluk için)
        migrations.AlterField(
            model_name='controlitem',
            name='step',
            field=models.IntegerField(blank=True, null=True, verbose_name='Adım (Eski)'),
        ),
        migrations.AlterField(
            model_name='controlitem',
            name='measurement_name',
            field=models.CharField(blank=True, max_length=200, verbose_name='Ölçüm Adı (Eski)'),
        ),
        migrations.AlterField(
            model_name='controlitem',
            name='spec_min',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True, verbose_name='Min. Spec (Eski)'),
        ),
        migrations.AlterField(
            model_name='controlitem',
            name='spec_max',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True, verbose_name='Max. Spec (Eski)'),
        ),
        migrations.AlterField(
            model_name='controlitem',
            name='frequency',
            field=models.CharField(blank=True, max_length=100, verbose_name='Frekans (Eski)'),
        ),
        
        # WorkOrderInspection modeli
        migrations.CreateModel(
            name='WorkOrderInspection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sample_no', models.IntegerField(blank=True, help_text='Örnek numarası (ilk parça için 1, her N için N, 2N, vb.)', null=True, verbose_name='Örnek No')),
                ('measured_value', models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True, verbose_name='Ölçülen Değer')),
                ('pass_fail', models.CharField(choices=[('PASS', 'Geçti'), ('FAIL', 'Başarısız'), ('REWORK', 'Yeniden İşleme'), ('SCRAP', 'Hurda'), ('HOLD', 'Beklet'), ('DEVIATION', 'Sapma (Onaylı)')], max_length=20, verbose_name='Sonuç')),
                ('disposition', models.CharField(blank=True, choices=[('PASS', 'Geçti'), ('FAIL', 'Başarısız'), ('REWORK', 'Yeniden İşleme'), ('SCRAP', 'Hurda'), ('HOLD', 'Beklet'), ('DEVIATION', 'Sapma (Onaylı)')], max_length=20, null=True, verbose_name='Disposition')),
                ('disposition_reason', models.TextField(blank=True, verbose_name='Disposition Nedeni')),
                ('disposition_approved_at', models.DateTimeField(blank=True, null=True, verbose_name='Disposition Onay Tarihi')),
                ('attachment', models.FileField(blank=True, null=True, upload_to='inspection_attachments/%Y/%m/%d/', verbose_name='Ek Dosya')),
                ('notes', models.TextField(blank=True, verbose_name='Notlar')),
                ('measured_at', models.DateTimeField(verbose_name='Ölçüm Zamanı')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Oluşturulma Tarihi')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Güncellenme Tarihi')),
                ('control_item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='inspections', to='stokapp.controlitem', verbose_name='Kontrol Maddesi')),
                ('disposition_approver', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_dispositions', to=settings.AUTH_USER_MODEL, verbose_name='Disposition Onaylayan')),
                ('instrument', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='inspections', to='stokapp.olcualeti', verbose_name='Kullanılan Ölçü Aleti')),
                ('measured_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='performed_inspections', to=settings.AUTH_USER_MODEL, verbose_name='Ölçüm Yapan')),
                ('operation_step', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='inspections', to='stokapp.receteoperasyon', verbose_name='Operasyon Adımı')),
                ('work_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inspections', to='stokapp.uretimemri', verbose_name='İş Emri')),
            ],
            options={
                'verbose_name': 'İş Emri Kontrol Kaydı',
                'verbose_name_plural': 'İş Emri Kontrol Kayıtları',
                'ordering': ['-measured_at'],
            },
        ),
        migrations.AddIndex(
            model_name='workorderinspection',
            index=models.Index(fields=['work_order', 'operation_step'], name='stokapp_wor_work_or_6f8a2a_idx'),
        ),
        migrations.AddIndex(
            model_name='workorderinspection',
            index=models.Index(fields=['control_item', 'pass_fail'], name='stokapp_wor_control_c8b3e1_idx'),
        ),
        
        # QualityGate modeli
        migrations.CreateModel(
            name='QualityGate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('gate_type', models.CharField(choices=[('BLOCK_ON_INCOMPLETE', 'Eksik Kontrolleri Engelle'), ('BLOCK_ON_FAIL', 'Başarısız Kontrolleri Engelle'), ('BLOCK_ON_CRITICAL_FAIL', 'Kritik Başarısızları Engelle')], default='BLOCK_ON_INCOMPLETE', max_length=30, verbose_name='Geçit Tipi')),
                ('applies_to_critical_only', models.BooleanField(default=False, verbose_name='Sadece Kritik Kontrollere Uygula')),
                ('active', models.BooleanField(default=True, verbose_name='Aktif')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Oluşturulma Tarihi')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Güncellenme Tarihi')),
                ('operation_step', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quality_gates', to='stokapp.receteoperasyon', verbose_name='Operasyon Adımı')),
            ],
            options={
                'verbose_name': 'Kalite Geçidi',
                'verbose_name_plural': 'Kalite Geçitleri',
                'ordering': ['operation_step__sira'],
                'unique_together': {('operation_step', 'gate_type')},
            },
        ),
        
        # NonconformanceAutoRule modeli
        migrations.CreateModel(
            name='NonconformanceAutoRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Kural Adı')),
                ('description', models.TextField(blank=True, verbose_name='Açıklama')),
                ('trigger_type', models.CharField(choices=[('CRITICAL_FAIL', 'Kritik Başarısız'), ('MAJOR_FAIL', 'Önemli Başarısız'), ('ANY_FAIL', 'Herhangi Bir Başarısız'), ('MULTIPLE_FAIL', 'Birden Fazla Başarısız')], default='CRITICAL_FAIL', max_length=20, verbose_name='Tetikleme Tipi')),
                ('trigger_count', models.IntegerField(default=1, help_text='Kaç adet başarısız kontrol sonrası tetiklensin?', verbose_name='Tetikleme Sayısı')),
                ('action_type', models.CharField(choices=[('CREATE_NCR', 'NCR (Uygunsuzluk) Oluştur'), ('CREATE_COMPLAINT', 'Şikayet Oluştur'), ('HOLD_WORK_ORDER', 'İş Emrini Beklet'), ('NOTIFY_QUALITY', 'Kalite Yönetimini Bildir')], max_length=20, verbose_name='Aksiyon Tipi')),
                ('default_severity', models.IntegerField(choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5')], default=3, verbose_name='Varsayılan Şiddet')),
                ('default_category', models.CharField(blank=True, max_length=200, verbose_name='Varsayılan Kategori')),
                ('active', models.BooleanField(default=True, verbose_name='Aktif')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Oluşturulma Tarihi')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Güncellenme Tarihi')),
                ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='ncr_auto_rules', to='stokapp.kategori', verbose_name='Belirli Kategori')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL, verbose_name='Oluşturan')),
                ('product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='ncr_auto_rules', to='stokapp.stokitem', verbose_name='Belirli Ürün')),
            ],
            options={
                'verbose_name': 'Uygunsuzluk Otomatik Kuralı',
                'verbose_name_plural': 'Uygunsuzluk Otomatik Kuralları',
                'ordering': ['-created_at'],
            },
        ),
        
        # ControlItem ordering güncellemesi
        migrations.AlterModelOptions(
            name='controlitem',
            options={'ordering': ['plan', 'operation_step__sira', 'display_order', 'id'], 'verbose_name': 'Kontrol Planı Maddesi', 'verbose_name_plural': 'Kontrol Planı Maddeleri'},
        ),
        
        # Mevcut kayıtlar için name alanını doldur (measurement_name'den kopyala)
        migrations.RunPython(
            code=migrate_controlitem_name,
            reverse_code=migrations.RunPython.noop,
        ),
        # name alanını zorunlu yap
        migrations.AlterField(
            model_name='controlitem',
            name='name',
            field=models.CharField(max_length=200, verbose_name='Kontrol Adı'),
        ),
    ]

