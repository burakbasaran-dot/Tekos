(function () {
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
  }

  function renderOperasyonRow(op) {
    const standart = op.standart_kod
      ? `<a href="/stok/uretim/standartlar/${op.standart_id}/" target="_blank">${escapeHtml(op.standart_kod)}</a>`
      : '-';
    const dis = op.akis_dis_operasyon && op.dis_tedarikci_ad
      ? escapeHtml(op.dis_tedarikci_ad.length > 24 ? op.dis_tedarikci_ad.slice(0, 22) + '…' : op.dis_tedarikci_ad)
      : '<span style="color:#9ca3af">—</span>';
    return `
      <tr data-operasyon-id="${op.id}">
        <td style="text-align:center;"><input type="checkbox" class="recete-sira-sec" value="${op.id}"></td>
        <td>${escapeHtml(op.operasyon_ad)}</td>
        <td>${escapeHtml(op.istasyon_ad || '-')}</td>
        <td>${standart}</td>
        <td>${parseFloat(op.maliyet || 0).toFixed(2)} TRY</td>
        <td style="font-family:monospace;">${escapeHtml(op.sure_formatted)}</td>
        <td style="font-weight:600;color:#059669;">${parseFloat(op.toplam_maliyet || 0).toFixed(2)} TRY</td>
        <td>${dis}</td>
        <td>${escapeHtml(op.aciklama || '-')}</td>
        <td style="text-align:center;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="editOperasyon(${op.id})">✏️</button>
          <button type="button" class="btn btn-secondary btn-sm" onclick="deleteOperasyon(${op.id})">🗑️</button>
        </td>
      </tr>`;
  }

  function renderTree(tree, toplam) {
    const wrap = document.getElementById('operasyonAgaciWrap');
    if (!wrap) return;
    if (!tree || !tree.length) {
      wrap.innerHTML = '<div class="operasyon-empty">Henüz operasyon eklenmemiş. Sağ alttaki + ile Genel Operasyon veya bileşen seçip operasyon tanımlayın.</div>';
    } else {
      wrap.innerHTML = '<div id="operasyonAgaci" class="operasyon-agaci">' + tree.map(node => {
        const detayId = node.detay_id;
        const genel = node.genel || detayId === 0;
        const titleHtml = genel
          ? `<strong>${escapeHtml(node.stok_kodu || 'Genel Operasyon')}</strong>`
          : (node.stok_item_id && typeof window.stokDetayHref === 'function'
            ? `<a href="${escapeHtml(window.stokDetayHref(node.stok_item_id))}" class="stok-detay-link"><strong>${escapeHtml(node.stok_kodu)}</strong></a><span>${escapeHtml(node.stok_ad)}</span>`
            : `<strong>${escapeHtml(node.stok_kodu)}</strong><span>${escapeHtml(node.stok_ad)}</span>`);
        const nodeClass = genel ? 'operasyon-bilesen-node operasyon-genel-node' : 'operasyon-bilesen-node';
        return `
        <div class="${nodeClass}" data-detay-id="${detayId}">
          <div class="operasyon-bilesen-header">
            <button type="button" class="operasyon-tree-toggle" onclick="toggleOperasyonBilesen(${detayId})" aria-label="Genişlet">+</button>
            <div class="operasyon-bilesen-title">
              ${titleHtml}
              <span class="operasyon-count-badge">${node.operasyonlar.length} operasyon</span>
            </div>
            <button type="button" class="btn btn-secondary btn-sm" onclick="addOperasyonModal(${detayId})">+ Operasyon</button>
          </div>
          <div id="operasyon-panel-${detayId}" class="operasyon-bilesen-panel" style="display:none;">
            <table class="operasyon-inner-table">
              <thead><tr>
                <th style="width:44px;">Seç</th><th>Operasyon</th><th>İstasyon</th><th>Standart</th>
                <th>Maliyet</th><th>Süre</th><th>Toplam</th><th>Dış op.</th><th>Açıklama</th><th style="width:80px;"></th>
              </tr></thead>
              <tbody class="operasyon-sira-tbody" data-detay-id="${detayId}">
                ${node.operasyonlar.map(renderOperasyonRow).join('')}
              </tbody>
            </table>
          </div>
        </div>`;
      }).join('') + '</div>';
    }
    const bar = document.getElementById('operasyonToplamBar');
    if (bar) {
      bar.textContent = 'Operasyonlar Toplamı: ₺ ' + parseFloat(toplam || 0).toFixed(2);
    }
    if (typeof receteSiraAracCubuguGuncelle === 'function') receteSiraAracCubuguGuncelle();
  }

  window.reloadOperasyonAgaci = function reloadOperasyonAgaci() {
    const url = window.RECETE_OPERASYON_LIST_URL;
    if (!url) return;
    fetch(url)
      .then(r => r.json())
      .then(data => renderTree(data.tree || [], data.toplam_maliyet || 0))
      .catch(err => console.error('Operasyon ağacı yüklenemedi', err));
  };

  window.loadOperasyonlarTable = window.reloadOperasyonAgaci;
})();
