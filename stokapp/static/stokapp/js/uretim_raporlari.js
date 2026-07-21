(function () {
  const configEl = document.getElementById("uretim-rapor-config");
  if (!configEl) return;
  const config = JSON.parse(configEl.textContent || "{}");

  const form = document.getElementById("report-filter-form");
  const clearBtn = document.getElementById("report-clear-btn");
  const tbody = document.getElementById("report-table-body");
  const rowCountEl = document.getElementById("report-row-count");
  const exportExcelBtn = document.getElementById("report-export-excel-btn");
  const exportPdfBtn = document.getElementById("report-export-pdf-btn");

  const detailDrawer = document.getElementById("report-detail-drawer");
  const detailBackdrop = document.getElementById("report-detail-backdrop");
  const detailCloseBtn = document.getElementById("report-detail-close");
  const detailLoading = document.getElementById("report-detail-loading");
  const detailContent = document.getElementById("report-detail-content");

  const state = {
    selectedRowId: null,
    rowDetailCache: {},
  };

  function toQueryString(params) {
    const usp = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && String(value).trim() !== "") {
        usp.set(key, String(value).trim());
      }
    });
    return usp.toString();
  }

  function getFilters() {
    return {
      date_start: form.elements.date_start.value,
      date_end: form.elements.date_end.value,
      personel: form.elements.personel.value,
      emir_no: form.elements.emir_no.value,
      urun_kodu: form.elements.urun_kodu.value,
      urun_adi: form.elements.urun_adi.value,
      operasyon: form.elements.operasyon.value,
      durum: form.elements.durum.value,
    };
  }

  function setFiltersFromUrl() {
    const params = new URLSearchParams(window.location.search);
    Array.from(form.elements).forEach((el) => {
      if (!el.name) return;
      if (params.has(el.name)) el.value = params.get(el.name);
    });
  }

  function pushUrl(filters) {
    const qs = toQueryString(filters);
    const nextUrl = qs ? `${window.location.pathname}?${qs}` : window.location.pathname;
    window.history.replaceState({}, "", nextUrl);
  }

  function updateExportLinks(filters) {
    const qs = toQueryString(filters);
    if (exportExcelBtn) {
      exportExcelBtn.href = qs ? `${config.exportExcelUrl}?${qs}` : config.exportExcelUrl;
    }
    if (exportPdfBtn) {
      exportPdfBtn.href = qs ? `${config.exportPdfUrl}?${qs}` : config.exportPdfUrl;
    }
  }

  function formatDateTime(value) {
    if (!value) return "-";
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return "-";
    return dt.toLocaleString("tr-TR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function htmlEscape(value) {
    return String(value || "").replace(/[&<>"']/g, (m) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;",
    }[m]));
  }

  async function fetchJson(url) {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || "İşlem başarısız.");
    return data;
  }

  function renderSummary(summary) {
    document.getElementById("sum-tamamlanan").textContent = summary.toplam_tamamlanan_is ?? 0;
    document.getElementById("sum-gerceklesen").textContent = summary.toplam_gerceklesen_sure_text || "00:00";
    document.getElementById("sum-durus").textContent = summary.toplam_durus_sure_text || "00:00";
    document.getElementById("sum-en-cok-durus-op").textContent = summary.en_cok_durus_operasyon || "-";
    document.getElementById("sum-en-cok-personel").textContent = summary.en_cok_tamamlayan_personel || "-";
    document.getElementById("sum-sapma").textContent = summary.sure_sapmasi_text || "+0 dk";
  }

  function renderRows(rows) {
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="13" class="rapor-empty">Filtreye uygun kayıt bulunamadı.</td></tr>';
      rowCountEl.textContent = "0 kayıt";
      return;
    }

    rowCountEl.textContent = `${rows.length} kayıt`;
    tbody.innerHTML = rows.map((row) => `
      <tr data-asama-id="${row.id}">
        <td>${formatDateTime(row.tarih)}</td>
        <td>${htmlEscape(row.emir_no)}</td>
        <td>${htmlEscape(row.urun_kodu)}</td>
        <td>${htmlEscape(row.urun_adi)}</td>
        <td>${htmlEscape(row.operasyon_adi)}</td>
        <td>${htmlEscape(row.personel)}</td>
        <td>${htmlEscape(row.planlanan_sure_text)}</td>
        <td>${htmlEscape(row.gerceklesen_sure_text)}</td>
        <td>${htmlEscape(row.durus_sure_text)}</td>
        <td>${htmlEscape(row.net_calisma_sure_text)}</td>
        <td><span class="durum-rozet ${htmlEscape(row.durum_class)}">${htmlEscape(row.durum_label)}</span></td>
        <td><span class="flag-dot ${row.not_var ? "true" : ""}"></span></td>
        <td><span class="flag-dot ${row.sorun_var ? "true" : ""}"></span></td>
      </tr>
    `).join("");
  }

  async function loadReportData() {
    const filters = getFilters();
    pushUrl(filters);
    updateExportLinks(filters);
    const qs = toQueryString(filters);
    const listUrl = qs ? `${config.listUrl}?${qs}` : config.listUrl;
    const summaryUrl = qs ? `${config.summaryUrl}?${qs}` : config.summaryUrl;

    tbody.innerHTML = '<tr><td colspan="13" class="rapor-empty">Yükleniyor...</td></tr>';
    const [listData, summaryData] = await Promise.all([fetchJson(listUrl), fetchJson(summaryUrl)]);
    renderRows(listData.rows || []);
    renderSummary(summaryData.summary || {});
  }

  function openDetailDrawer() {
    detailDrawer.classList.add("open");
    detailBackdrop.classList.add("open");
    detailDrawer.setAttribute("aria-hidden", "false");
  }

  function closeDetailDrawer() {
    detailDrawer.classList.remove("open");
    detailBackdrop.classList.remove("open");
    detailDrawer.setAttribute("aria-hidden", "true");
    state.selectedRowId = null;
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value || "-";
  }

  function renderList(id, items, renderer) {
    const el = document.getElementById(id);
    if (!el) return;
    if (!items || !items.length) {
      el.innerHTML = '<div class="rapor-muted">Kayıt yok.</div>';
      return;
    }
    el.innerHTML = items.map(renderer).join("");
  }

  function renderDetail(task) {
    setText("d-emir-no", task.emir_no);
    setText("d-urun-kodu", task.urun_kodu);
    setText("d-urun-adi", task.urun_adi);
    setText("d-operasyon", task.operasyon_adi);
    setText("d-personel", task.atanan_personel);
    setText("d-durum", task.durum_label);
    setText("d-planlanan", task.planlanan_sure_text);
    setText("d-gercek", task.gerceklesen_sure_text);
    setText("d-fark", task.gecikme_text);
    const goCalendarBtn = document.getElementById("report-go-calendar-btn");
    const editTaskBtn = document.getElementById("report-edit-task-btn");
    if (goCalendarBtn) {
      if (task.planlama_url) {
        goCalendarBtn.href = task.planlama_url;
        goCalendarBtn.classList.remove("hidden");
      } else {
        goCalendarBtn.href = "#";
        goCalendarBtn.classList.add("hidden");
      }
    }
    if (editTaskBtn) {
      if (task.duzenle_url) {
        editTaskBtn.href = task.duzenle_url;
        editTaskBtn.classList.remove("hidden");
      } else {
        editTaskBtn.href = "#";
        editTaskBtn.classList.add("hidden");
      }
    }

    renderList("d-duruslar", task.duruslar || [], (item) => `
      <div class="detail-item">
        <div class="detail-item-meta">${formatDateTime(item.baslama)} - ${formatDateTime(item.bitis)}</div>
        <div>${htmlEscape(item.aciklama || "Duruş kaydı")}</div>
        <div class="detail-item-meta">Süre: ${item.sure_dk || 0} dk</div>
      </div>
    `);

    renderList("d-notlar", task.notlar || [], (item) => `
      <div class="detail-item">
        <div class="detail-item-meta">${htmlEscape(item.kullanici)} · ${formatDateTime(item.created_at)}</div>
        <div>${htmlEscape(item.metin)}</div>
      </div>
    `);

    renderList("d-sorunlar", task.sorunlar || [], (item) => `
      <div class="detail-item">
        <div class="detail-item-meta">${htmlEscape(item.tip_label)} · ${htmlEscape(item.kullanici)} · ${formatDateTime(item.created_at)}</div>
        <div>${htmlEscape(item.aciklama)}</div>
        ${item.gorsel_url ? `<a class="drawer-file-link" href="${item.gorsel_url}" target="_blank" rel="noopener">Görseli Aç</a>` : ""}
      </div>
    `);
  }

  async function loadDetail(asamaId) {
    if (state.rowDetailCache[asamaId]) return state.rowDetailCache[asamaId];
    const url = config.detailUrlTemplate.replace("/0/", `/${asamaId}/`);
    const data = await fetchJson(url);
    state.rowDetailCache[asamaId] = data.task;
    return data.task;
  }

  async function openRowDetail(asamaId) {
    state.selectedRowId = asamaId;
    openDetailDrawer();
    detailLoading.classList.remove("hidden");
    detailContent.classList.add("hidden");
    try {
      const task = await loadDetail(asamaId);
      renderDetail(task);
      detailLoading.classList.add("hidden");
      detailContent.classList.remove("hidden");
    } catch (err) {
      detailLoading.textContent = err.message;
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await loadReportData();
  });

  clearBtn.addEventListener("click", async () => {
    form.reset();
    state.rowDetailCache = {};
    await loadReportData();
  });

  tbody.addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-asama-id]");
    if (!row) return;
    openRowDetail(row.dataset.asamaId);
  });

  detailCloseBtn.addEventListener("click", closeDetailDrawer);
  detailBackdrop.addEventListener("click", closeDetailDrawer);

  (async function init() {
    setFiltersFromUrl();
    await loadReportData();
  })();
})();
