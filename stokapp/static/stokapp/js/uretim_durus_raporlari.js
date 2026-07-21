(function () {
  const configEl = document.getElementById("durus-rapor-config");
  if (!configEl) return;
  const config = JSON.parse(configEl.textContent || "{}");

  const form = document.getElementById("durus-filter-form");
  const clearBtn = document.getElementById("durus-clear-btn");
  const rowCountEl = document.getElementById("durus-row-count");
  const tbody = document.getElementById("durus-table-body");
  const prevBtn = document.getElementById("durus-prev-page");
  const nextBtn = document.getElementById("durus-next-page");
  const pageText = document.getElementById("durus-page-text");
  const exportExcelBtn = document.getElementById("export-excel-btn");
  const exportPdfBtn = document.getElementById("export-pdf-btn");

  const state = { page: 1, perPage: 50, pagination: { total_pages: 1 } };
  const charts = {};

  function getFilters() {
    const filters = {};
    Array.from(form.elements).forEach((el) => {
      if (!el.name) return;
      const v = String(el.value || "").trim();
      if (v) filters[el.name] = v;
    });
    return filters;
  }

  function toQS(params) {
    const usp = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v).trim() !== "") usp.set(k, String(v).trim());
    });
    return usp.toString();
  }

  async function fetchJson(url) {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || "İşlem başarısız.");
    return data;
  }

  function fmtDateTime(v) {
    if (!v) return "-";
    const dt = new Date(v);
    if (Number.isNaN(dt.getTime())) return "-";
    return dt.toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value || "-";
  }

  function updateExportLinks(filters) {
    const qs = toQS(filters);
    exportExcelBtn.href = qs ? `${config.exportExcelUrl}?${qs}` : config.exportExcelUrl;
    exportPdfBtn.href = qs ? `${config.exportPdfUrl}?${qs}` : config.exportPdfUrl;
  }

  function renderSummary(summary) {
    setText("kpi-toplam-sure", summary.toplam_durus_suresi_text);
    setText("kpi-sayi", String(summary.durus_sayisi ?? 0));
    setText("kpi-ortalama", summary.ortalama_durus_suresi_text);
    setText("kpi-en-uzun", summary.en_uzun_durus_text);
    setText("kpi-makine", summary.en_cok_durus_makine);
    setText("kpi-personel", summary.en_cok_durus_personel);
  }

  function renderRows(rows, pagination) {
    rowCountEl.textContent = `${pagination.total} kayıt`;
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="11" class="muted">Filtreye uygun kayıt bulunamadı.</td></tr>';
    } else {
      tbody.innerHTML = rows.map((r) => `
        <tr>
          <td>${fmtDateTime(r.tarih)}</td>
          <td>${r.is_emri || "-"}</td>
          <td>${r.urun || "-"}</td>
          <td>${r.operasyon || "-"}</td>
          <td>${r.personel || "-"}</td>
          <td>${r.makine || "-"}</td>
          <td>${r.durus_nedeni || "-"}</td>
          <td>${fmtDateTime(r.baslangic)}</td>
          <td>${fmtDateTime(r.bitis)}</td>
          <td>${r.sure_text || "-"}</td>
          <td>${r.aciklama || "-"}</td>
        </tr>
      `).join("");
    }
    state.pagination = pagination;
    pageText.textContent = `Sayfa ${pagination.page}/${pagination.total_pages}`;
    prevBtn.disabled = pagination.page <= 1;
    nextBtn.disabled = pagination.page >= pagination.total_pages;
  }

  function renderChart(canvasId, type, labels, values, color) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    if (charts[canvasId]) charts[canvasId].destroy();
    const baseOptions = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: type === "pie", position: "bottom", labels: { boxWidth: 10, font: { size: 11 } } } },
      layout: { padding: { top: 6, right: 6, bottom: 4, left: 4 } },
    };
    if (type !== "pie") {
      baseOptions.scales = {
        x: {
          ticks: { autoSkip: true, maxTicksLimit: 8, maxRotation: 0, minRotation: 0, font: { size: 10 } },
          grid: { display: false },
        },
        y: {
          beginAtZero: true,
          ticks: { font: { size: 10 } },
          grid: { color: "#eef2f7" },
        },
      };
    }

    charts[canvasId] = new Chart(canvas.getContext("2d"), {
      type,
      data: { labels, datasets: [{ data: values, backgroundColor: color, borderColor: color, fill: type === "line" ? false : true, tension: 0.3 }] },
      options: baseOptions,
    });
  }

  function renderCharts(chartData) {
    renderChart("chart-reason", "pie", chartData.reason_pie.labels || [], chartData.reason_pie.values || [], [
      "#60a5fa", "#34d399", "#f59e0b", "#f87171", "#a78bfa", "#22d3ee", "#f472b6", "#94a3b8",
    ]);
    renderChart("chart-machine", "bar", chartData.machine_bar.labels || [], chartData.machine_bar.values || [], "#60a5fa");
    renderChart("chart-daily", "line", chartData.daily_line.labels || [], chartData.daily_line.values || [], "#34d399");
    renderChart("chart-personnel", "bar", chartData.personnel_bar.labels || [], chartData.personnel_bar.values || [], "#f59e0b");
  }

  async function refreshAll() {
    const filters = getFilters();
    updateExportLinks(filters);
    const listQs = toQS({ ...filters, page: state.page, per_page: state.perPage });
    const listUrl = listQs ? `${config.listUrl}?${listQs}` : config.listUrl;
    const summaryQs = toQS(filters);
    const summaryUrl = summaryQs ? `${config.summaryUrl}?${summaryQs}` : config.summaryUrl;
    const chartsUrl = summaryQs ? `${config.chartsUrl}?${summaryQs}` : config.chartsUrl;

    tbody.innerHTML = '<tr><td colspan="11" class="muted">Yükleniyor...</td></tr>';
    const [listData, summaryData, chartResp] = await Promise.all([
      fetchJson(listUrl),
      fetchJson(summaryUrl),
      fetchJson(chartsUrl),
    ]);
    renderRows(listData.rows || [], listData.pagination || { page: 1, total_pages: 1, total: 0 });
    renderSummary(summaryData.summary || {});
    renderCharts(chartResp.charts || {});
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    state.page = 1;
    await refreshAll();
  });

  Array.from(form.elements).forEach((el) => {
    if (!el.name) return;
    el.addEventListener("change", async () => {
      state.page = 1;
      await refreshAll();
    });
  });

  clearBtn.addEventListener("click", async () => {
    form.reset();
    state.page = 1;
    await refreshAll();
  });

  prevBtn.addEventListener("click", async () => {
    if (state.page <= 1) return;
    state.page -= 1;
    await refreshAll();
  });
  nextBtn.addEventListener("click", async () => {
    if (state.page >= (state.pagination.total_pages || 1)) return;
    state.page += 1;
    await refreshAll();
  });

  refreshAll();
})();
