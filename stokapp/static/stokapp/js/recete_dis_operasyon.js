(function () {
  'use strict';

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
  }

  function getCookie(name) {
    if (typeof window.getCookie === 'function') return window.getCookie(name);
    const m = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return m ? decodeURIComponent(m[2]) : null;
  }

  let disTipler = [];
  let currentEditDisId = null;
  let currentDisDetayId = null;

  function renderRow(item) {
    return `
      <tr data-dis-id="${item.id}">
        <td>${escapeHtml(item.dis_operasyon_tipi_ad)}</td>
        <td>${escapeHtml(item.tedarikci_ad || '—')}</td>
        <td>${escapeHtml(String(item.dis_beklenen_donus_gun || 7))} gün</td>
        <td>${escapeHtml(item.aciklama || '—')}</td>
        <td style="text-align:center;white-space:nowrap;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="editReceteDisOperasyon(${item.id})">✏️</button>
          <button type="button" class="btn btn-secondary btn-sm" onclick="deleteReceteDisOperasyon(${item.id})">🗑️</button>
        </td>
      </tr>`;
  }

  function renderTree(tree) {
    const wrap = document.getElementById('disOperasyonAgaciWrap');
    if (!wrap) return;
    if (!tree || !tree.length) {
      wrap.innerHTML = '<div class="dis-op-empty">Henüz dış operasyon atanmamış. Sağ alttaki + ile ürün geneline veya bileşene dış operasyon ekleyin.</div>';
      return;
    }
    wrap.innerHTML = '<div class="dis-op-agaci">' + tree.map(node => {
      const detayId = node.detay_id;
      const genel = node.genel || detayId === 0;
      const titleHtml = genel
        ? `<strong>${escapeHtml(node.label || 'Ürün Geneli')}</strong>`
        : (node.stok_item_id && typeof window.stokDetayHref === 'function'
          ? `<a href="${escapeHtml(window.stokDetayHref(node.stok_item_id))}" class="stok-detay-link"><strong>${escapeHtml(node.stok_kodu)}</strong></a><span>${escapeHtml(node.stok_ad)}</span>`
          : `<strong>${escapeHtml(node.stok_kodu)}</strong><span>${escapeHtml(node.stok_ad)}</span>`);
      const nodeClass = genel ? 'dis-op-node dis-op-genel-node' : 'dis-op-node';
      return `
        <div class="${nodeClass}" data-detay-id="${detayId}">
          <div class="dis-op-header">
            <button type="button" class="dis-op-toggle" onclick="toggleDisOperasyonNode(${detayId})" aria-label="Genişlet">+</button>
            <div class="dis-op-title">${titleHtml}<span class="dis-op-count">${node.atamalar.length} dış op.</span></div>
            <button type="button" class="btn btn-secondary btn-sm" onclick="addReceteDisOperasyonModal(${detayId})">+ Dış Op.</button>
          </div>
          <div id="dis-op-panel-${detayId}" class="dis-op-panel" style="display:none;">
            <table class="dis-op-table">
              <thead><tr>
                <th>Dış Operasyon</th><th>Taşeron</th><th>Dönüş</th><th>Açıklama</th><th style="width:80px;"></th>
              </tr></thead>
              <tbody>${node.atamalar.map(renderRow).join('')}</tbody>
            </table>
          </div>
        </div>`;
    }).join('') + '</div>';
  }

  window.toggleDisOperasyonNode = function toggleDisOperasyonNode(detayId) {
    const panel = document.getElementById('dis-op-panel-' + detayId);
    const btn = document.querySelector('.dis-op-node[data-detay-id="' + detayId + '"] .dis-op-toggle');
    if (!panel || !btn) return;
    const open = panel.style.display !== 'none';
    panel.style.display = open ? 'none' : 'block';
    btn.textContent = open ? '+' : '−';
    btn.classList.toggle('expanded', !open);
  };

  window.reloadDisOperasyonAgaci = function reloadDisOperasyonAgaci() {
    const url = window.RECETE_DIS_OPERASYON_LIST_URL;
    if (!url) return;
    fetch(url)
      .then(r => r.json())
      .then(data => {
        if (data.tipler) disTipler = data.tipler;
        renderTree(data.tree || []);
      })
      .catch(err => console.error('Dış operasyon ağacı yüklenemedi', err));
  };

  function fillDisTipSelect(select, selectedId) {
    if (!select) return;
    const cur = selectedId ? String(selectedId) : select.value;
    select.innerHTML = '<option value="">Dış operasyon seçin...</option>';
    disTipler.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t.id;
      opt.textContent = t.ad;
      select.appendChild(opt);
    });
    if (cur) select.value = cur;
  }

  window.addReceteDisOperasyonModal = function addReceteDisOperasyonModal(detayId) {
    currentEditDisId = null;
    if (detayId === 0 || detayId === '0') currentDisDetayId = 0;
    else currentDisDetayId = detayId || null;
    openReceteDisOperasyonModal();
  };

  window.editReceteDisOperasyon = function editReceteDisOperasyon(itemId) {
    currentEditDisId = itemId;
    fetch(window.RECETE_DIS_OPERASYON_LIST_URL)
      .then(r => r.json())
      .then(data => {
        const item = (data.results || []).find(x => x.id === itemId);
        if (item) openReceteDisOperasyonModal(item);
        else alert('Kayıt bulunamadı.');
      });
  };

  function openReceteDisOperasyonModal(itemData) {
    let modal = document.getElementById('receteDisOperasyonModal');
    if (modal) modal.remove();
    const isEdit = currentEditDisId !== null;
    const cfg = window.RECETE_DIS_OP_CFG || {};
    modal = document.createElement('div');
    modal.id = 'receteDisOperasyonModal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:2100;display:flex;align-items:center;justify-content:center;';
    modal.innerHTML = `
      <div style="background:#fff;border-radius:12px;padding:28px;max-width:620px;width:92%;max-height:90vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.3);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
          <h3 style="margin:0;">${isEdit ? '✏️ Dış Operasyon Düzenle' : '➕ Dış Operasyon Ekle'}</h3>
          <button type="button" onclick="closeReceteDisOperasyonModal()" style="background:none;border:none;font-size:24px;cursor:pointer;color:#6b7280;">&times;</button>
        </div>
        <form id="receteDisOperasyonForm">
          <div style="margin-bottom:16px;">
            <label style="display:block;font-weight:600;margin-bottom:8px;">Atama kapsamı <span style="color:#dc3545;">*</span></label>
            <button type="button" id="receteDisUrunGeneliSec" ${isEdit ? 'disabled' : ''} style="width:100%;padding:12px 14px;margin-bottom:10px;border:2px solid #bbf7d0;border-radius:10px;background:#ecfdf5;color:#14532d;font-weight:700;font-size:14px;text-align:left;cursor:pointer;">Ürün Geneli</button>
            <input type="hidden" id="receteDisUrunGeneliInput" value="0">
            <select id="receteDisBilesenSelect" ${isEdit ? 'disabled' : ''} style="width:100%;padding:10px;border-radius:8px;border:2px solid #e5e7eb;font-size:14px;">
              <option value="">Bileşen seçin...</option>
            </select>
          </div>
          <div style="margin-bottom:16px;">
            <label style="display:block;font-weight:600;margin-bottom:8px;">Dış Operasyon <span style="color:#dc3545;">*</span></label>
            <div style="display:flex;gap:8px;align-items:center;">
              <select id="receteDisTipSelect" required style="flex:1;padding:10px;border-radius:8px;border:2px solid #e5e7eb;font-size:14px;">
                <option value="">Seçin...</option>
              </select>
              <button type="button" id="receteDisTipEkleBtn" title="Yeni dış operasyon tipi" style="width:42px;height:42px;border-radius:8px;border:2px solid #3b82f6;background:#eff6ff;color:#1d4ed8;font-size:22px;font-weight:700;cursor:pointer;flex-shrink:0;">+</button>
            </div>
          </div>
          <div style="margin-bottom:16px;">
            <label style="display:block;font-weight:600;margin-bottom:8px;">Taşeron / Tedarikçi</label>
            <select id="receteDisTedarikciSelect" style="width:100%;padding:10px;border-radius:8px;border:2px solid #e5e7eb;font-size:14px;">
              <option value="">Seçin (isteğe bağlı)...</option>
              ${(cfg.tedarikciler || []).map(t => `<option value="${t.id}">${escapeHtml(t.ad)}</option>`).join('')}
            </select>
          </div>
          <div style="margin-bottom:16px;">
            <label style="display:block;font-weight:600;margin-bottom:8px;">Gönderim Deposu</label>
            <select id="receteDisDepoSelect" style="width:100%;padding:10px;border-radius:8px;border:2px solid #e5e7eb;font-size:14px;">
              <option value="">—</option>
              ${(cfg.depolar || []).map(d => `<option value="${d.id}">${escapeHtml(d.ad)}</option>`).join('')}
            </select>
          </div>
          <div style="margin-bottom:16px;">
            <label style="display:block;font-weight:600;margin-bottom:8px;">Beklenen Dönüş (gün)</label>
            <input type="number" id="receteDisGunInput" min="0" value="${itemData ? itemData.dis_beklenen_donus_gun : '7'}" style="width:100%;max-width:160px;padding:10px;border-radius:8px;border:2px solid #e5e7eb;">
          </div>
          <div style="margin-bottom:16px;">
            <label style="display:block;font-weight:600;margin-bottom:8px;">Açıklama</label>
            <textarea id="receteDisAciklamaInput" rows="2" style="width:100%;padding:10px;border-radius:8px;border:2px solid #e5e7eb;resize:vertical;">${itemData ? escapeHtml(itemData.aciklama || '') : ''}</textarea>
          </div>
          <div style="display:flex;gap:10px;justify-content:flex-end;padding-top:16px;border-top:2px solid #e5e7eb;">
            <button type="button" class="btn btn-secondary" onclick="closeReceteDisOperasyonModal()">İptal</button>
            <button type="submit" class="btn btn-primary">💾 ${isEdit ? 'Güncelle' : 'Kaydet'}</button>
          </div>
        </form>
      </div>`;
    document.body.appendChild(modal);

    const bilesenSelect = document.getElementById('receteDisBilesenSelect');
    const genelBtn = document.getElementById('receteDisUrunGeneliSec');
    const genelInput = document.getElementById('receteDisUrunGeneliInput');
    const tipSelect = document.getElementById('receteDisTipSelect');

    function setUrunGeneli(aktif) {
      if (!genelBtn || !genelInput || !bilesenSelect) return;
      genelInput.value = aktif ? '1' : '0';
      genelBtn.style.borderColor = aktif ? '#16a34a' : '#bbf7d0';
      genelBtn.style.background = aktif ? '#bbf7d0' : '#ecfdf5';
      genelBtn.style.boxShadow = aktif ? 'inset 0 0 0 1px #16a34a' : 'none';
      if (!isEdit) {
        bilesenSelect.disabled = aktif;
        if (aktif) bilesenSelect.value = '';
      }
    }

    (window.RECETE_BILESENLER || []).forEach(b => {
      const opt = document.createElement('option');
      opt.value = b.id;
      opt.textContent = b.kod + ' — ' + b.ad;
      bilesenSelect.appendChild(opt);
    });

    fillDisTipSelect(tipSelect, itemData && itemData.dis_operasyon_tipi_id);

    const isGenelData = itemData && itemData.genel;
    const preGenel = currentDisDetayId === 0 || currentDisDetayId === '0';
    const preDetay = (itemData && itemData.recete_detay_id) || (currentDisDetayId && currentDisDetayId !== 0 ? currentDisDetayId : null);
    if (isGenelData || preGenel) setUrunGeneli(true);
    else if (preDetay) { bilesenSelect.value = String(preDetay); setUrunGeneli(false); }

    if (genelBtn && !isEdit) {
      genelBtn.addEventListener('click', () => setUrunGeneli(genelInput.value !== '1'));
    }
    if (bilesenSelect && !isEdit) {
      bilesenSelect.addEventListener('change', () => { if (bilesenSelect.value) setUrunGeneli(false); });
    }

    if (itemData) {
      if (itemData.tedarikci_id) document.getElementById('receteDisTedarikciSelect').value = String(itemData.tedarikci_id);
      if (itemData.dis_gonderim_deposu_id) document.getElementById('receteDisDepoSelect').value = String(itemData.dis_gonderim_deposu_id);
    }

    document.getElementById('receteDisTipEkleBtn').addEventListener('click', () => {
      const ad = window.prompt('Yeni dış operasyon adı:');
      if (!ad || !ad.trim()) return;
      const fd = new FormData();
      fd.append('ad', ad.trim());
      const csrf = getCookie('csrftoken');
      if (csrf) fd.append('csrfmiddlewaretoken', csrf);
      fetch(window.DIS_OPERASYON_TIPI_EKLE_URL, { method: 'POST', body: fd })
        .then(r => r.json())
        .then(data => {
          if (!data.success) { alert(data.error || 'Eklenemedi.'); return; }
          if (!disTipler.find(t => t.id === data.tip.id)) disTipler.push(data.tip);
          disTipler.sort((a, b) => a.ad.localeCompare(b.ad, 'tr'));
          fillDisTipSelect(tipSelect, data.tip.id);
        })
        .catch(() => alert('Dış operasyon tipi eklenirken hata oluştu.'));
    });

    document.getElementById('receteDisOperasyonForm').addEventListener('submit', saveReceteDisOperasyon);
  }

  window.closeReceteDisOperasyonModal = function closeReceteDisOperasyonModal() {
    const m = document.getElementById('receteDisOperasyonModal');
    if (m) m.remove();
    currentEditDisId = null;
  };

  function saveReceteDisOperasyon(e) {
    e.preventDefault();
    const genel = document.getElementById('receteDisUrunGeneliInput').value === '1';
    const detayId = document.getElementById('receteDisBilesenSelect').value;
    const tipId = document.getElementById('receteDisTipSelect').value;
    if (!tipId) { alert('Dış operasyon seçin.'); return; }
    if (!genel && !detayId) { alert('Ürün geneli veya bileşen seçin.'); return; }

    const fd = new FormData();
    if (genel) fd.append('genel', '1');
    else fd.append('recete_detay_id', detayId);
    fd.append('dis_operasyon_tipi_id', tipId);
    const ted = document.getElementById('receteDisTedarikciSelect').value;
    const depo = document.getElementById('receteDisDepoSelect').value;
    if (ted) fd.append('tedarikci_id', ted);
    if (depo) fd.append('dis_gonderim_deposu_id', depo);
    fd.append('dis_beklenen_donus_gun', document.getElementById('receteDisGunInput').value);
    fd.append('aciklama', document.getElementById('receteDisAciklamaInput').value);
    const csrf = getCookie('csrftoken');
    if (csrf) fd.append('csrfmiddlewaretoken', csrf);

    const url = currentEditDisId
      ? window.RECETE_DIS_OPERASYON_DUZENLE_URL.replace('/0/', '/' + currentEditDisId + '/')
      : window.RECETE_DIS_OPERASYON_EKLE_URL;

    fetch(url, { method: 'POST', body: fd })
      .then(r => r.json())
      .then(data => {
        if (data.success) {
          closeReceteDisOperasyonModal();
          reloadDisOperasyonAgaci();
        } else alert(data.error || 'Kaydedilemedi.');
      })
      .catch(() => alert('Kayıt sırasında hata oluştu.'));
  }

  window.deleteReceteDisOperasyon = function deleteReceteDisOperasyon(itemId) {
    if (!confirm('Bu dış operasyon atamasını silmek istediğinize emin misiniz?')) return;
    const fd = new FormData();
    const csrf = getCookie('csrftoken');
    if (csrf) fd.append('csrfmiddlewaretoken', csrf);
    const url = window.RECETE_DIS_OPERASYON_SIL_URL.replace('/0/', '/' + itemId + '/');
    fetch(url, { method: 'POST', body: fd })
      .then(r => r.json())
      .then(data => {
        if (data.success) reloadDisOperasyonAgaci();
        else alert(data.error || 'Silinemedi.');
      });
  };
})();
