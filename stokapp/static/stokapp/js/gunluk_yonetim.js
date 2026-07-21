/**
 * Günlük Yönetim Paneli — api/gunluk-yonetim-ozet verisini yükler.
 */
(function () {
  function badgeClass(sinif) {
    var m = {
      normal: 'gmp-badge-normal',
      yaklasiyor: 'gmp-badge-yaklasiyor',
      gecikti: 'gmp-badge-gecikti',
      tamamlandi: 'gmp-badge-tamamlandi',
      kritik: 'gmp-badge-kritik',
    };
    return m[sinif] || m.normal;
  }

  function rowTpl(r) {
    var b = badgeClass(r.durum_sinifi);
    return (
      '<tr>' +
      '<td><strong>' +
      escapeHtml(r.kayit_no || '—') +
      '</strong></td>' +
      '<td>' +
      escapeHtml(r.aciklama || '—') +
      '</td>' +
      '<td>' +
      escapeHtml(r.taraf || '—') +
      '</td>' +
      '<td>' +
      escapeHtml([r.tarih, r.termin].filter(Boolean).join(' / ') || '—') +
      '</td>' +
      '<td><span class="gmp-badge ' +
      b +
      '">' +
      escapeHtml(r.durum || '—') +
      '</span></td>' +
      '<td><a class="btn btn-secondary" style="padding:6px 10px;font-size:12px;" href="' +
      escapeAttr(r.detay_url || '#') +
      '">Aç</a></td>' +
      '</tr>'
    );
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, '&#39;');
  }

  function fillTable(tbodyEl, rows) {
    if (!tbodyEl) return;
    if (!rows || !rows.length) {
      tbodyEl.innerHTML =
        '<tr><td colspan="6" class="gmp-empty">Kayıt yok.</td></tr>';
      return;
    }
    tbodyEl.innerHTML = rows.map(rowTpl).join('');
  }

  function setSummary(data) {
    var s = data.summary_counts || {};
    function set(id, val) {
      var el = document.getElementById(id);
      if (el) el.textContent = val == null ? '0' : String(val);
    }
    set('gmp-sum-bugun', s.bugunku_is);
    set('gmp-sum-geciken', s.geciken);
    set('gmp-sum-onay', s.onay_bekleyen);
    set('gmp-sum-kritik', s.kritik_stok);
    set('gmp-sum-odeme', s.yaklasan_odeme);
  }

  function setLinks(urls) {
    if (!urls) return;
    function href(id, key) {
      var a = document.getElementById(id);
      if (a && urls[key]) a.href = urls[key];
    }
    href('gmp-link-bugun', 'siparis_listesi');
    href('gmp-link-geciken', 'uretim_emirleri');
    href('gmp-link-onay', 'teklif_listesi');
    href('gmp-link-kritik', 'stok_listesi');
    href('gmp-link-odeme', 'aylik_odemeler_listesi');
  }

  function render(data) {
    setSummary(data);
    var urls = data.list_urls || {};
    setLinks(urls);
    var sec = data.sections || {};

    fillTable(document.querySelector('#gmp-tbody-teklif'), sec.onay_teklifler);
    fillTable(document.querySelector('#gmp-tbody-siparis'), sec.onay_siparisler);
    fillTable(document.querySelector('#gmp-tbody-talep'), sec.acik_talepler);
    fillTable(document.querySelector('#gmp-tbody-kritik'), sec.kritik_stok);

    var g = sec.geciken || {};
    fillTable(document.querySelector('#gmp-tbody-gec-siparis'), g.siparis);
    fillTable(document.querySelector('#gmp-tbody-gec-sat'), g.satinalma);
    fillTable(document.querySelector('#gmp-tbody-gec-talep'), g.talep);
    fillTable(document.querySelector('#gmp-tbody-gec-emir'), g.uretim_emri);

    var hdr = document.querySelectorAll('.gmp-list-link');
    hdr.forEach(function (a) {
      var k = a.getAttribute('data-list-key');
      if (k && urls[k]) a.href = urls[k];
    });
  }

  window.gmpLoadPanel = function (apiUrl) {
    var params = new URLSearchParams(window.location.search);
    var q = new URLSearchParams();
    if (params.get('period')) q.set('period', params.get('period'));
    if (params.get('departman')) q.set('departman', params.get('departman'));
    if (params.get('sorumlu')) q.set('sorumlu', params.get('sorumlu'));
    var url = apiUrl + (q.toString() ? '?' + q.toString() : '');
    var status = document.getElementById('gmp-load-status');
    if (status) status.textContent = 'Yükleniyor…';

    fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (status) status.textContent = '';
        if (data.error) {
          if (status) status.textContent = 'Uyarı: ' + data.error;
        }
        render(data);
      })
      .catch(function () {
        if (status) status.textContent = 'Veri yüklenemedi.';
      });
  };
})();
