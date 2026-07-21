(function () {
  const configEl = document.getElementById("planlama-config");
  if (!configEl) return;

  const config = JSON.parse(configEl.textContent || "{}");
  const assignmentUrl = config.assignmentUrl || "";
  const detailUrlTemplate = config.detailUrlTemplate || "";
  const planUpdateUrlTemplate = config.planUpdateUrlTemplate || "";
  const actionUrlTemplate = config.actionUrlTemplate || "";
  const noteUrlTemplate = config.noteUrlTemplate || "";
  const issueUrlTemplate = config.issueUrlTemplate || "";
  const instructionUrlTemplate = config.instructionUrlTemplate || "";
  const currentScale = config.scale || "hour";
  const startDateText = config.startDate || "";
  const slotMinutes = Number(config.slotMinutes || 15);
  const maxParallelTasksPerUser = Number(config.maxParallelTasksPerUser || 2);
  const assignmentsData = JSON.parse(document.getElementById("assignments-data").textContent || "[]");

  const state = {
    selectedTaskId: null,
    drawerOpen: false,
    taskDetail: null,
    instructionExpanded: false,
    instructionLoaded: false,
    actionLoading: false,
    lastDraggedAt: 0,
    events: {},
  };

  const drawer = document.getElementById("task-drawer");
  const drawerBackdrop = document.getElementById("task-drawer-backdrop");
  const drawerLoading = document.getElementById("drawer-loading");
  const drawerContent = document.getElementById("drawer-content");
  const instructionPanel = document.getElementById("instruction-panel");
  const instructionLoading = document.getElementById("instruction-loading");
  const instructionEmpty = document.getElementById("instruction-empty");
  const instructionList = document.getElementById("instruction-list");
  const instructionStateText = document.getElementById("instruction-state-text");
  const planPersonelInput = document.getElementById("plan-personel-id");
  const planDateInput = document.getElementById("plan-start-date");
  const planStartInput = document.getElementById("plan-start-time");
  const planDurationInput = document.getElementById("plan-duration-minutes");
  const planEndInput = document.getElementById("plan-end-time");
  const planSaveBtn = document.getElementById("btn-plan-save");

  function getCsrfToken() {
    const name = "csrftoken=";
    const decoded = decodeURIComponent(document.cookie || "");
    const cookies = decoded.split(";");
    for (let i = 0; i < cookies.length; i += 1) {
      const c = cookies[i].trim();
      if (c.startsWith(name)) return c.substring(name.length, c.length);
    }
    return "";
  }

  function buildTaskUrl(template, asamaId) {
    return template.replace("/0/", `/${asamaId}/`);
  }

  function safeText(value) {
    return String(value || "").replace(/[&<>"']/g, (m) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;",
    }[m]));
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

  function formatTimeHHmm(value) {
    if (!value) return "";
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return "";
    return `${String(dt.getHours()).padStart(2, "0")}:${String(dt.getMinutes()).padStart(2, "0")}`;
  }

  function formatDateYYYYMMDD(value) {
    if (!value) return "";
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return "";
    return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
  }

  function parseBaseDate() {
    const now = new Date();
    if (!startDateText) return now;
    const parsed = new Date(`${startDateText}T00:00:00`);
    return Number.isNaN(parsed.getTime()) ? now : parsed;
  }

  function setElementText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value || "-";
  }

  function roundToNearestSlot(date, minutesStep) {
    const dt = new Date(date);
    dt.setSeconds(0, 0);
    const mins = dt.getMinutes();
    const rounded = Math.round(mins / minutesStep) * minutesStep;
    dt.setMinutes(rounded, 0, 0);
    return dt;
  }

  function floorToSlot(date, minutesStep) {
    const dt = new Date(date);
    dt.setSeconds(0, 0);
    const mins = dt.getMinutes();
    const floored = Math.floor(mins / minutesStep) * minutesStep;
    dt.setMinutes(floored, 0, 0);
    return dt;
  }

  function ceilToSlot(date, minutesStep) {
    const dt = new Date(date);
    dt.setSeconds(0, 0);
    const mins = dt.getMinutes();
    const ceiled = Math.ceil(mins / minutesStep) * minutesStep;
    dt.setMinutes(ceiled, 0, 0);
    return dt;
  }

  function addMinutes(date, minutes) {
    return new Date(new Date(date).getTime() + (minutes * 60000));
  }

  function diffMinutes(start, end) {
    return Math.max(0, Math.round((new Date(end) - new Date(start)) / 60000));
  }

  function getOverlapCount(events, resourceId, start, end, excludeEventId) {
    const startDate = new Date(start);
    const endDate = new Date(end);
    return events.filter((event) => {
      if (!event || String(event.personel_id || "") !== String(resourceId || "")) return false;
      if (excludeEventId && String(event.id) === String(excludeEventId)) return false;
      if (!event.start || !event.end) return false;
      const eventStart = new Date(event.start);
      const eventEnd = new Date(event.end);
      return eventStart < endDate && eventEnd > startDate;
    }).length;
  }

  function hasTimeConflict(events, resourceId, start, end, excludeEventId) {
    return getOverlapCount(events, resourceId, start, end, excludeEventId) >= maxParallelTasksPerUser;
  }

  function areIntervalsOverlapping(aStart, aEnd, bStart, bEnd) {
    return new Date(aStart) < new Date(bEnd) && new Date(aEnd) > new Date(bStart);
  }

  function toEvent(item) {
    return {
      id: item.id,
      personel_id: item.personel_id,
      start: item.start,
      end: item.end,
      total_minutes: Number(item.total_minutes || diffMinutes(item.start, item.end)),
      asama_ad: item.asama_ad,
      urun: item.urun,
      urun_kod: item.urun_kod,
      status_label: item.status_label,
      status_class: item.status_class,
      sure: item.sure,
      emir_no: item.emir_no,
      emir_id: item.emir_id,
      detay_id: item.detay_id,
    };
  }

  function updateActionButtons(durum) {
    const buttonMap = {
      btnBaslat: document.getElementById("btn-baslat"),
      btnDuraklat: document.getElementById("btn-duraklat"),
      btnDevam: document.getElementById("btn-devam"),
      btnTamamla: document.getElementById("btn-tamamla"),
    };
    Object.values(buttonMap).forEach((btn) => { if (btn) btn.disabled = true; });
    const enabledActions = {
      BEKLIYOR: ["btnBaslat"],
      DEVAM_EDIYOR: ["btnDuraklat", "btnTamamla"],
      BEKLEMEDE: ["btnDevam"],
      SORUNLU: ["btnDevam"],
      TAMAMLANDI: [],
    }[durum] || [];
    enabledActions.forEach((key) => {
      if (buttonMap[key]) buttonMap[key].disabled = false;
    });
  }

  function renderNotes(notes) {
    const list = document.getElementById("note-list");
    if (!list) return;
    if (!notes || !notes.length) {
      list.innerHTML = '<div class="empty-hint">Henüz not yok.</div>';
      return;
    }
    list.innerHTML = notes.map((note) => (
      `<div class="drawer-list-item"><div class="drawer-list-meta">${safeText(note.kullanici)} · ${formatDateTime(note.created_at)}</div><div>${safeText(note.metin)}</div></div>`
    )).join("");
  }

  function renderIssues(issues) {
    const list = document.getElementById("issue-list");
    if (!list) return;
    if (!issues || !issues.length) {
      list.innerHTML = '<div class="empty-hint">Henüz sorun kaydı yok.</div>';
      return;
    }
    list.innerHTML = issues.map((issue) => {
      const imagePart = issue.gorsel_url ? `<a class="drawer-file-link" href="${issue.gorsel_url}" target="_blank" rel="noopener">Görseli Aç</a>` : "";
      return `<div class="drawer-list-item"><div class="drawer-list-meta">${safeText(issue.tip_label)} · ${safeText(issue.kullanici)} · ${formatDateTime(issue.created_at)}</div><div>${safeText(issue.aciklama)}</div><div class="drawer-issue-state">${safeText(issue.durum_label)}</div>${imagePart}</div>`;
    }).join("");
  }

  function syncPlanInputs(task) {
    const startIso = task.planlanan_baslangic;
    let duration = Number(task.planlanan_sure_dk || 0);
    if (startIso && task.planlanan_bitis) {
      duration = diffMinutes(startIso, task.planlanan_bitis);
    }
    if (duration <= 0) duration = slotMinutes;
    if (planPersonelInput) planPersonelInput.value = task.personel_id ? String(task.personel_id) : "";
    if (planDateInput) planDateInput.value = formatDateYYYYMMDD(startIso) || formatDateYYYYMMDD(parseBaseDate());
    if (planStartInput) planStartInput.value = formatTimeHHmm(startIso);
    if (planDurationInput) planDurationInput.value = String(duration);
    updatePlanEndPreview();
  }

  function updatePlanEndPreview() {
    if (!planDateInput || !planStartInput || !planDurationInput || !planEndInput) return;
    const dateText = (planDateInput.value || "").trim();
    const startText = planStartInput.value;
    const duration = Math.max(slotMinutes, Number(planDurationInput.value || slotMinutes));
    if (!dateText || !startText) {
      planEndInput.value = "";
      return;
    }
    const base = new Date(`${dateText}T00:00:00`);
    if (Number.isNaN(base.getTime())) {
      planEndInput.value = "";
      return;
    }
    const [h, m] = startText.split(":");
    base.setHours(Number(h), Number(m), 0, 0);
    const snappedStart = roundToNearestSlot(base, slotMinutes);
    const snappedDuration = Math.max(slotMinutes, Math.round(duration / slotMinutes) * slotMinutes);
    const end = addMinutes(snappedStart, snappedDuration);
    planDateInput.value = formatDateYYYYMMDD(snappedStart.toISOString());
    planStartInput.value = formatTimeHHmm(snappedStart.toISOString());
    planDurationInput.value = String(snappedDuration);
    planEndInput.value = formatTimeHHmm(end.toISOString());
  }

  function buildAssignedCardHtml(item) {
    return `
      <div class="task-title">${safeText(item.asama_ad || "-")}</div>
      <div class="task-meta task-product-code">Ürün: ${safeText(item.urun_kod || "-")}</div>
      <div class="task-meta task-duration">Plan: ${safeText(item.total_minutes || item.sure || "-")} dk</div>
      <div class="task-status-badge ${safeText(item.status_class || "status-waiting")}">${safeText(item.status_label || "-")}</div>
    `;
  }

  function buildTooltipText(item) {
    const lines = [];
    if (item.urun) lines.push(item.urun);
    if (item.urun_kod) lines.push(`Kod: ${item.urun_kod}`);
    if (item.total_minutes) lines.push(`Planlanan: ${item.total_minutes} dk`);
    if (item.status_label) lines.push(`Durum: ${item.status_label}`);
    return lines.join("\n");
  }

  function ensureAssignedTooltip(card, item) {
    if (!card.classList.contains("assigned")) return;
    const tooltipText = buildTooltipText(item || {});
    if (!tooltipText) return;
    let tooltip = card.querySelector(".task-tooltip");
    if (!tooltip) {
      tooltip = document.createElement("div");
      tooltip.className = "task-tooltip";
      card.appendChild(tooltip);
    }
    tooltip.textContent = tooltipText;
  }

  function calculateSpanByMinutes(totalMinutes, cell) {
    if (currentScale !== "hour") return 1;
    const slotSpan = Math.max(1, Math.ceil(totalMinutes / slotMinutes));
    const row = cell.closest(".timeline-row");
    const totalCells = row ? row.querySelectorAll(".timeline-cell").length : slotSpan;
    const slotIndex = Number(cell.dataset.slotIndex || 0);
    return Math.max(1, Math.min(slotSpan, Math.max(1, totalCells - slotIndex)));
  }

  function applyCardSpan(card, totalMinutes, cell) {
    if (currentScale !== "hour") {
      card.classList.remove("hour-span");
      card.style.removeProperty("--slot-span");
      return;
    }
    card.classList.add("hour-span");
    card.style.setProperty("--slot-span", String(calculateSpanByMinutes(totalMinutes, cell)));
  }

  function buildOverlapGroups(events) {
    const sorted = [...events].sort((a, b) => {
      const aStart = new Date(a.start).getTime();
      const bStart = new Date(b.start).getTime();
      if (aStart !== bStart) return aStart - bStart;
      return Number(a.id) - Number(b.id);
    });
    const groups = [];
    let current = [];
    let currentEnd = null;

    sorted.forEach((eventItem) => {
      const start = new Date(eventItem.start);
      const end = new Date(eventItem.end);
      if (!current.length) {
        current = [eventItem];
        currentEnd = end;
        return;
      }
      if (start < currentEnd) {
        current.push(eventItem);
        if (end > currentEnd) currentEnd = end;
      } else {
        groups.push(current);
        current = [eventItem];
        currentEnd = end;
      }
    });
    if (current.length) groups.push(current);
    return groups;
  }

  function assignLanes(group) {
    const laneEnd = [];
    const laneMap = {};
    group.forEach((eventItem) => {
      const start = new Date(eventItem.start);
      const end = new Date(eventItem.end);
      let laneIndex = 0;
      while (laneIndex < laneEnd.length && laneEnd[laneIndex] > start) laneIndex += 1;
      if (laneIndex >= laneEnd.length) laneEnd.push(end);
      else laneEnd[laneIndex] = end;
      laneMap[String(eventItem.id)] = laneIndex;
    });
    return { laneMap, totalLanes: Math.max(1, Math.min(maxParallelTasksPerUser, laneEnd.length)) };
  }

  function calculateEventLayout(eventItem, laneIndex, totalLanes) {
    const widthPercent = 100 / totalLanes;
    const leftPercent = laneIndex * widthPercent;
    return {
      laneIndex,
      totalLanes,
      widthPercent,
      leftPercent,
      zIndex: laneIndex + 1,
      top: 6,
      height: null,
    };
  }

  function buildLaneLayout(events) {
    const layout = {};
    const personMap = {};
    events.forEach((eventItem) => {
      const key = String(eventItem.personel_id || "");
      if (!personMap[key]) personMap[key] = [];
      personMap[key].push(eventItem);
    });

    Object.entries(personMap).forEach(([personelId, personEvents]) => {
      const groups = buildOverlapGroups(personEvents);
      groups.forEach((group) => {
        const lanePack = assignLanes(group);
        group.forEach((eventItem) => {
          const laneIndex = lanePack.laneMap[String(eventItem.id)] ?? 0;
          layout[String(eventItem.id)] = calculateEventLayout(eventItem, laneIndex, lanePack.totalLanes);
        });
      });

      console.debug(`[PlanlamaLane] userId: ${personelId}, events: ${personEvents.length}, groups: ${groups.length}`);
      personEvents.forEach((eventItem) => {
        const laneData = layout[String(eventItem.id)];
        console.debug(
          `[PlanlamaLane] task ${eventItem.id} -> lane ${laneData.laneIndex} / ${laneData.totalLanes} / left ${laneData.leftPercent} / width ${laneData.widthPercent}`
        );
      });
    });

    return layout;
  }

  function applyCardLane(card, laneData) {
    card.style.setProperty("--lane-count", String(laneData.totalLanes));
    card.style.setProperty("--lane-index", String(laneData.laneIndex));
    card.style.setProperty("--left-percent", String(laneData.leftPercent));
    card.style.setProperty("--width-percent", String(laneData.widthPercent));
    card.style.zIndex = String(3 + laneData.zIndex);
    card.style.top = `${laneData.top}px`;
  }

  function getCellByStart(personelId, startIso) {
    if (!startIso) return null;
    const target = floorToSlot(new Date(startIso), slotMinutes).getTime();
    if (Number.isNaN(target)) return null;
    const cells = document.querySelectorAll(`.timeline-cell[data-personel-id="${personelId}"]`);
    for (let i = 0; i < cells.length; i += 1) {
      const cellStart = new Date(cells[i].dataset.slotStart).getTime();
      if (!Number.isNaN(cellStart) && cellStart === target) {
        return cells[i];
      }
    }
    return null;
  }

  function attachCardClick(card, asamaId) {
    if (card.dataset.clickBound === "1") return;
    card.dataset.clickBound = "1";
    card.addEventListener("click", () => {
      if (Date.now() - state.lastDraggedAt < 300) return;
      openTaskDrawer(asamaId);
    });
  }

  function renderAssignedCard(item, laneLayout) {
    const cell = getCellByStart(item.personel_id, item.start);
    if (!cell) return;
    const card = document.createElement("div");
    card.className = `task-card assigned ${item.status_class || "status-waiting"}`;
    card.draggable = true;
    card.dataset.asamaId = item.id;
    card.dataset.emirId = item.emir_id || "";
    card.dataset.detayId = item.detay_id || "0";
    card.dataset.emirNo = item.emir_no || card.dataset.emirNo || "";
    card.dataset.asamaAd = item.asama_ad || card.dataset.asamaAd || "";
    card.dataset.urunAd = item.urun || card.dataset.urunAd || "";
    card.dataset.urunKod = item.urun_kod || card.dataset.urunKod || "";
    card.dataset.sure = String(item.sure || card.dataset.sure || "");
    card.innerHTML = buildAssignedCardHtml(item);
    attachDragHandlers(card);
    ensureAssignedTooltip(card, item);
    applyCardSpan(card, item.total_minutes || slotMinutes, cell);
    const laneData = laneLayout[String(item.id)] || {
      laneIndex: 0, totalLanes: 1, widthPercent: 100, leftPercent: 0, zIndex: 1,
    };
    applyCardLane(card, laneData);
    attachCardClick(card, item.id);
    cell.appendChild(card);
  }

  function rerenderAssignedCards() {
    document.querySelectorAll(".timeline-cell .task-card.assigned").forEach((card) => card.remove());
    const allEvents = Object.values(state.events);
    const laneLayout = buildLaneLayout(allEvents);

    allEvents
      .sort((a, b) => {
        const aStart = new Date(a.start).getTime();
        const bStart = new Date(b.start).getTime();
        if (aStart !== bStart) return aStart - bStart;
        return Number(a.id) - Number(b.id);
      })
      .forEach((eventItem) => renderAssignedCard(eventItem, laneLayout));
  }

  function upsertEventFromTask(task) {
    const event = {
      id: task.id,
      personel_id: task.personel_id,
      start: task.planlanan_baslangic,
      end: task.planlanan_bitis,
      total_minutes: task.planlanan_sure_dk || diffMinutes(task.planlanan_baslangic, task.planlanan_bitis),
      asama_ad: task.operasyon_adi,
      urun: task.urun_adi,
      urun_kod: task.urun_kodu,
      status_label: task.durum_label,
      status_class: task.durum_class,
      sure: task.planlanan_sure_dk,
      emir_no: task.emir_no,
    };
    state.events[String(task.id)] = event;
    rerenderAssignedCards();
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    return response.json();
  }

  async function loadTaskDetail(asamaId) {
    const data = await fetchJson(buildTaskUrl(detailUrlTemplate, asamaId), { headers: { Accept: "application/json" } });
    if (!data.success) throw new Error(data.error || "Görev detayı alınamadı");
    return data.task;
  }

  function openDrawer() {
    state.drawerOpen = true;
    drawer.classList.add("open");
    drawerBackdrop.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
  }

  function closeDrawer() {
    state.drawerOpen = false;
    state.selectedTaskId = null;
    state.taskDetail = null;
    state.instructionExpanded = false;
    state.instructionLoaded = false;
    drawer.classList.remove("open");
    drawerBackdrop.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
    drawerLoading.classList.remove("hidden");
    drawerContent.classList.add("hidden");
    instructionPanel.classList.add("hidden");
    instructionList.innerHTML = "";
    instructionEmpty.classList.add("hidden");
    instructionStateText.textContent = "Kapalı";
  }

  function renderTaskDetail(task) {
    state.taskDetail = task;
    setElementText("drawer-emir-no", task.emir_no);
    setElementText("drawer-urun-kodu", task.urun_kodu);
    setElementText("drawer-urun-adi", task.urun_adi);
    setElementText("drawer-operasyon", task.operasyon_adi);
    setElementText("drawer-personel", task.atanan_personel);
    setElementText("drawer-durum", task.durum_label);
    setElementText("drawer-planlanan-sure", task.planlanan_sure_text);
    setElementText("drawer-planlanan-baslangic", formatDateTime(task.planlanan_baslangic));
    setElementText("drawer-planlanan-bitis", formatDateTime(task.planlanan_bitis));
    setElementText("drawer-gerceklesen-sure", task.gerceklesen_sure_text);
    setElementText("drawer-gecikme", task.gecikme_text);
    renderNotes(task.notlar || []);
    renderIssues(task.sorunlar || []);
    syncPlanInputs(task);
    updateActionButtons(task.durum);
  }

  async function openTaskDrawer(asamaId) {
    state.selectedTaskId = asamaId;
    openDrawer();
    drawerLoading.textContent = "Yükleniyor...";
    drawerLoading.classList.remove("hidden");
    drawerContent.classList.add("hidden");
    try {
      const task = await loadTaskDetail(asamaId);
      renderTaskDetail(task);
      drawerLoading.classList.add("hidden");
      drawerContent.classList.remove("hidden");
    } catch (error) {
      drawerLoading.textContent = error.message;
    }
  }

  async function runTaskAction(action) {
    if (!state.selectedTaskId || state.actionLoading) return;
    state.actionLoading = true;
    try {
      const data = await fetchJson(buildTaskUrl(actionUrlTemplate, state.selectedTaskId), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
        body: JSON.stringify({ aksiyon: action }),
      });
      if (!data.success) throw new Error(data.error || "Aksiyon gerçekleştirilemedi.");
      renderTaskDetail(data.task);
      upsertEventFromTask(data.task);
    } catch (error) {
      window.alert(error.message);
    } finally {
      state.actionLoading = false;
    }
  }

  async function saveTaskNote() {
    if (!state.selectedTaskId) return;
    const input = document.getElementById("note-input");
    const note = (input.value || "").trim();
    if (!note) return;
    const data = await fetchJson(buildTaskUrl(noteUrlTemplate, state.selectedTaskId), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify({ not: note }),
    });
    if (!data.success) return window.alert(data.error || "Not eklenemedi.");
    input.value = "";
    renderTaskDetail(data.task);
    upsertEventFromTask(data.task);
  }

  async function saveTaskIssue() {
    if (!state.selectedTaskId) return;
    const formData = new FormData();
    formData.append("sorun_tipi", document.getElementById("issue-type").value);
    formData.append("aciklama", (document.getElementById("issue-description").value || "").trim());
    formData.append("sorunlu_yap", document.getElementById("issue-mark-problem").checked ? "1" : "0");
    const issueImage = document.getElementById("issue-image");
    if (issueImage.files && issueImage.files[0]) formData.append("gorsel", issueImage.files[0]);

    const data = await fetchJson(buildTaskUrl(issueUrlTemplate, state.selectedTaskId), {
      method: "POST",
      headers: { "X-CSRFToken": getCsrfToken() },
      body: formData,
    });
    if (!data.success) return window.alert(data.error || "Sorun kaydı açılamadı.");
    document.getElementById("issue-description").value = "";
    issueImage.value = "";
    renderTaskDetail(data.task);
    upsertEventFromTask(data.task);
  }

  async function loadInstructions() {
    if (!state.selectedTaskId || state.instructionLoaded) return;
    instructionLoading.classList.remove("hidden");
    instructionEmpty.classList.add("hidden");
    instructionList.innerHTML = "";
    const data = await fetchJson(buildTaskUrl(instructionUrlTemplate, state.selectedTaskId), { headers: { Accept: "application/json" } });
    instructionLoading.classList.add("hidden");
    if (!data.success || !data.instructions || !data.instructions.length) {
      instructionEmpty.classList.remove("hidden");
      return;
    }
    instructionList.innerHTML = data.instructions.map((ins) => {
      const adimlar = (ins.islem_adimlari || []).map((a) => `<li>${safeText(a)}</li>`).join("");
      const kontrol = (ins.kontrol_noktalari || []).map((a) => `<li>${safeText(a)}</li>`).join("");
      const ekipmanlar = (ins.ekipmanlar || []).join(", ");
      const files = (ins.dosyalar || []).map((f) => f.is_image
        ? `<a class="drawer-image-thumb" href="${f.url}" target="_blank" rel="noopener"><img src="${f.url}" alt="${safeText(f.ad)}"></a>`
        : `<a class="drawer-file-link" href="${f.url}" target="_blank" rel="noopener">${safeText(f.ad)}</a>`).join("");
      return `<div class="instruction-item"><div class="instruction-title">Talimat #${ins.sira}</div><div class="instruction-text">${safeText(ins.aciklama || "")}</div>${adimlar ? `<div class="instruction-subtitle">İşlem adımları</div><ul>${adimlar}</ul>` : ""}${kontrol ? `<div class="instruction-subtitle">Kontrol noktaları</div><ul>${kontrol}</ul>` : ""}${ekipmanlar ? `<div class="instruction-subtitle">Takım / ekipman</div><div>${safeText(ekipmanlar)}</div>` : ""}${files ? `<div class="instruction-subtitle">Görsel / Döküman</div><div class="instruction-files">${files}</div>` : ""}</div>`;
    }).join("");
    state.instructionLoaded = true;
  }

  function toggleInstructions() {
    state.instructionExpanded = !state.instructionExpanded;
    instructionPanel.classList.toggle("hidden", !state.instructionExpanded);
    instructionStateText.textContent = state.instructionExpanded ? "Açık" : "Kapalı";
    if (state.instructionExpanded) loadInstructions();
  }

  async function saveManualPlanUpdate() {
    if (!state.selectedTaskId || !state.taskDetail) return;
    updatePlanEndPreview();

    const personelId = planPersonelInput ? String(planPersonelInput.value || "").trim() : "";
    if (!personelId) return window.alert("Atanan personel seçilmeli.");
    const startDateText = planDateInput ? String(planDateInput.value || "").trim() : "";
    if (!startDateText) return window.alert("Planlanan başlangıç tarihi gerekli.");
    const startText = planStartInput.value;
    if (!startText) return window.alert("Planlanan başlangıç zamanı gerekli.");
    const duration = Math.max(slotMinutes, Number(planDurationInput.value || slotMinutes));
    const snappedDuration = Math.max(slotMinutes, Math.round(duration / slotMinutes) * slotMinutes);

    const base = new Date(`${startDateText}T00:00:00`);
    if (Number.isNaN(base.getTime())) return window.alert("Geçerli bir başlangıç tarihi seçin.");
    const [h, m] = startText.split(":");
    base.setHours(Number(h), Number(m), 0, 0);
    const snappedStart = roundToNearestSlot(base, slotMinutes);
    const snappedEnd = addMinutes(snappedStart, snappedDuration);

    const allEvents = Object.values(state.events);
    if (hasTimeConflict(allEvents, personelId, snappedStart, snappedEnd, state.selectedTaskId)) {
      return window.alert(`Bu personel için aynı anda en fazla ${maxParallelTasksPerUser} görev planlanabilir.`);
    }

    const data = await fetchJson(buildTaskUrl(planUpdateUrlTemplate, state.selectedTaskId), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify({
        personel_id: Number(personelId),
        planlanan_baslangic: snappedStart.toISOString(),
        planlanan_sure_dk: snappedDuration,
      }),
    });
    if (!data.success) return window.alert(data.error || "Plan güncellenemedi.");
    renderTaskDetail(data.task);
    upsertEventFromTask(data.task);
    const unassignedCard = document.querySelector(`#unassigned-drop .task-card[data-asama-id="${state.selectedTaskId}"]`);
    if (unassignedCard) unassignedCard.remove();
  }

  function attachDragHandlers(card) {
    if (!card.dataset.asamaId) return;
    card.draggable = true;
    card.addEventListener("dragstart", (event) => {
      state.lastDraggedAt = Date.now();
      event.dataTransfer.setData("text/plain", card.dataset.asamaId);
    });
  }

  function expandPlanTreeParents(emirId, detayId) {
    const emirPanel = document.getElementById(`plan-tree-emir-${emirId}`);
    const bilesenPanel = document.getElementById(`plan-tree-bilesen-${emirId}-${detayId}`);
    if (emirPanel) {
      emirPanel.style.display = "block";
      const emirBtn = document.querySelector(`[onclick="togglePlanTree('emir-${emirId}')"]`);
      if (emirBtn) { emirBtn.textContent = "−"; emirBtn.classList.add("expanded"); }
    }
    if (bilesenPanel) {
      bilesenPanel.style.display = "block";
      const bilesenBtn = document.querySelector(`[onclick="togglePlanTree('bilesen-${emirId}-${detayId}')"]`);
      if (bilesenBtn) { bilesenBtn.textContent = "−"; bilesenBtn.classList.add("expanded"); }
    }
  }

  function insertTaskBackToTree(card) {
    const emirId = card.dataset.emirId;
    const detayId = card.dataset.detayId || "0";
    let container = document.getElementById(`plan-tree-bilesen-${emirId}-${detayId}`);
    if (!container) {
      let agaci = document.getElementById("planlama-gorev-agaci");
      if (!agaci) {
        const zone = document.getElementById("unassigned-drop");
        agaci = document.createElement("div");
        agaci.id = "planlama-gorev-agaci";
        agaci.className = "planlama-gorev-agaci";
        zone.innerHTML = "";
        zone.appendChild(agaci);
      }
      let emirNode = agaci.querySelector(`.plan-tree-emir[data-emir-id="${emirId}"]`);
      if (!emirNode) {
        emirNode = document.createElement("div");
        emirNode.className = "plan-tree-emir";
        emirNode.dataset.emirId = emirId;
        emirNode.innerHTML = `
          <div class="plan-tree-row plan-tree-emir-header">
            <button type="button" class="plan-tree-toggle expanded" onclick="togglePlanTree('emir-${emirId}')">−</button>
            <div class="plan-tree-label">
              <strong>${safeText(card.dataset.emirNo || "-")}</strong>
              <span>${safeText(card.dataset.urunKod || "")} — ${safeText(card.dataset.urunAd || "")}</span>
            </div>
          </div>
          <div id="plan-tree-emir-${emirId}" class="plan-tree-children"></div>`;
        agaci.appendChild(emirNode);
      }
      const emirChildren = document.getElementById(`plan-tree-emir-${emirId}`);
      let bilesenNode = emirChildren.querySelector(`.plan-tree-bilesen[data-detay-id="${detayId}"]`);
      if (!bilesenNode) {
        bilesenNode = document.createElement("div");
        bilesenNode.className = "plan-tree-bilesen";
        bilesenNode.dataset.detayId = detayId;
        bilesenNode.innerHTML = `
          <div class="plan-tree-row plan-tree-bilesen-header">
            <button type="button" class="plan-tree-toggle expanded" onclick="togglePlanTree('bilesen-${emirId}-${detayId}')">−</button>
            <span class="plan-tree-label">${safeText(card.dataset.bilesenLabel || "Genel")}</span>
          </div>
          <div id="plan-tree-bilesen-${emirId}-${detayId}" class="plan-tree-children"></div>`;
        emirChildren.appendChild(bilesenNode);
      }
      container = document.getElementById(`plan-tree-bilesen-${emirId}-${detayId}`);
    }
    card.classList.add("task-card", "task-leaf");
    card.classList.remove("assigned", "hour-span", "status-waiting", "status-active", "status-paused", "status-done", "status-problem");
    card.style.removeProperty("--slot-span");
    card.style.removeProperty("--lane-count");
    card.style.removeProperty("--lane-index");
    const tooltip = card.querySelector(".task-tooltip");
    if (tooltip) tooltip.remove();
    card.innerHTML = `<div class="task-title">${safeText(card.dataset.asamaAd || "-")}</div><div class="task-meta">Süre: ${safeText(card.dataset.sure || "-")} dk</div>`;
    container.appendChild(card);
    expandPlanTreeParents(emirId, detayId);
    attachDragHandlers(card);
  }

  async function cancelTaskPlan(asamaId, sourceCard) {
    const data = await updateAssignment({ asama_id: asamaId, personel_id: null, slot_start: null, slot_end: null });
    if (!data.success) {
      window.alert(data.error || "Plan iptal edilemedi.");
      return false;
    }
    delete state.events[String(asamaId)];
    rerenderAssignedCards();
    const card = sourceCard || document.createElement("div");
    card.dataset.asamaId = asamaId;
    insertTaskBackToTree(card);
    return true;
  }

  async function updateAssignment(payload) {
    return fetchJson(assignmentUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify(payload),
    });
  }

  function setupDropTargets() {
    document.querySelectorAll(".drop-target").forEach((cell) => {
      cell.addEventListener("dragover", (event) => {
        event.preventDefault();
        cell.classList.add("drag-over");
      });
      cell.addEventListener("dragleave", () => cell.classList.remove("drag-over"));
      cell.addEventListener("drop", async (event) => {
        event.preventDefault();
        cell.classList.remove("drag-over");
        const asamaId = event.dataTransfer.getData("text/plain");
        if (!asamaId) return;

        const slotStartRaw = new Date(cell.dataset.slotStart);
        const snappedStart = roundToNearestSlot(slotStartRaw, slotMinutes);
        const eventData = state.events[String(asamaId)] || {};
        const domCard = document.querySelector(`.task-card[data-asama-id="${asamaId}"]`);
        const durationMinutes = Number(eventData.total_minutes || domCard?.dataset?.sure || slotMinutes) || slotMinutes;
        const snappedDuration = Math.max(slotMinutes, Math.ceil(durationMinutes / slotMinutes) * slotMinutes);
        const snappedEnd = addMinutes(snappedStart, snappedDuration);
        const personelId = cell.dataset.personelId;

        if (hasTimeConflict(Object.values(state.events), personelId, snappedStart, snappedEnd, asamaId)) {
          window.alert(`Bu personel için aynı anda en fazla ${maxParallelTasksPerUser} görev planlanabilir.`);
          return;
        }

        const data = await updateAssignment({
          asama_id: asamaId,
          personel_id: personelId,
          slot_start: snappedStart.toISOString(),
          slot_end: snappedEnd.toISOString(),
        });
        if (!data.success) {
          window.alert(data.error || "Atama yapılamadı.");
          return;
        }

        const sourceCard = document.querySelector(`.task-card[data-asama-id="${asamaId}"]`);
        const wasUnassigned = sourceCard ? !sourceCard.classList.contains("assigned") : false;
        const current = state.events[String(asamaId)] || {};
        const merged = {
          ...current,
          id: Number(asamaId),
          personel_id: data.personel_id || Number(personelId),
          start: data.planlanan_baslama,
          end: data.planlanan_bitis,
          total_minutes: Number(data.total_minutes || current.total_minutes || slotMinutes),
          status_class: data.status_class || current.status_class || "status-waiting",
          status_label: data.status_label || current.status_label || "Bekliyor",
          asama_ad: domCard?.dataset?.asamaAd || current.asama_ad || "",
          urun: domCard?.dataset?.urunAd || current.urun || "",
          urun_kod: domCard?.dataset?.urunKod || current.urun_kod || "",
          sure: domCard?.dataset?.sure || current.sure || "",
          emir_no: domCard?.dataset?.emirNo || current.emir_no || "",
          emir_id: domCard?.dataset?.emirId || current.emir_id || "",
          detay_id: domCard?.dataset?.detayId || current.detay_id || "",
        };
        if (domCard) {
          merged.emir_id = domCard.dataset.emirId || merged.emir_id;
          merged.detay_id = domCard.dataset.detayId || merged.detay_id;
        }
        state.events[String(asamaId)] = merged;
        rerenderAssignedCards();
        if (wasUnassigned && sourceCard) {
          sourceCard.remove();
        }
      });
    });

    const unassignedZone = document.getElementById("unassigned-drop");
    if (!unassignedZone) return;
    unassignedZone.addEventListener("dragover", (event) => {
      event.preventDefault();
      unassignedZone.classList.add("drag-over");
    });
    unassignedZone.addEventListener("dragleave", () => unassignedZone.classList.remove("drag-over"));
    unassignedZone.addEventListener("drop", async (event) => {
      event.preventDefault();
      unassignedZone.classList.remove("drag-over");
      const asamaId = event.dataTransfer.getData("text/plain");
      if (!asamaId) return;

      const data = await updateAssignment({ asama_id: asamaId, personel_id: null, slot_start: null, slot_end: null });
      if (!data.success) return window.alert(data.error || "Görev kaldırılamadı.");

      const sourceCard = document.querySelector(`.task-card[data-asama-id="${asamaId}"]`);
      if (sourceCard) {
        if (!sourceCard.dataset.emirId) {
          const ev = state.events[String(asamaId)] || {};
          sourceCard.dataset.emirId = ev.emir_id || "";
          sourceCard.dataset.detayId = ev.detay_id || "0";
          sourceCard.dataset.emirNo = ev.emir_no || sourceCard.dataset.emirNo || "";
          sourceCard.dataset.asamaAd = ev.asama_ad || sourceCard.dataset.asamaAd || "";
          sourceCard.dataset.urunAd = ev.urun || sourceCard.dataset.urunAd || "";
          sourceCard.dataset.urunKod = ev.urun_kod || sourceCard.dataset.urunKod || "";
          sourceCard.dataset.sure = ev.sure || sourceCard.dataset.sure || "";
        }
        delete state.events[String(asamaId)];
        rerenderAssignedCards();
        insertTaskBackToTree(sourceCard);
      }
    });
  }

  function setupPlanContextMenu() {
    const menu = document.getElementById("plan-context-menu");
    const cancelBtn = document.getElementById("plan-context-cancel");
    if (!menu || !cancelBtn) return;
    let targetAsamaId = null;
    let targetCard = null;

    document.addEventListener("contextmenu", (event) => {
      const card = event.target.closest(".task-card.assigned");
      if (!card) return;
      event.preventDefault();
      targetAsamaId = card.dataset.asamaId;
      targetCard = card;
      menu.style.display = "block";
      menu.style.left = `${event.clientX}px`;
      menu.style.top = `${event.clientY}px`;
    });

    document.addEventListener("click", () => { menu.style.display = "none"; });
    cancelBtn.addEventListener("click", async (event) => {
      event.stopPropagation();
      menu.style.display = "none";
      if (!targetAsamaId) return;
      const card = targetCard || document.querySelector(`.task-card.assigned[data-asama-id="${targetAsamaId}"]`);
      if (card && !card.dataset.emirId) {
        const ev = state.events[String(targetAsamaId)] || {};
        card.dataset.emirId = ev.emir_id || "";
        card.dataset.detayId = ev.detay_id || "0";
        card.dataset.emirNo = ev.emir_no || "";
        card.dataset.asamaAd = ev.asama_ad || "";
        card.dataset.urunAd = ev.urun || "";
        card.dataset.urunKod = ev.urun_kod || "";
        card.dataset.sure = ev.sure || "";
      }
      await cancelTaskPlan(targetAsamaId, card);
      targetAsamaId = null;
      targetCard = null;
    });
  }

  function bindDrawerActions() {
    const closeBtn = document.getElementById("drawer-close-btn");
    const instructionBtn = document.getElementById("btn-talimat-toggle");
    const noteBtn = document.getElementById("btn-note-save");
    const issueBtn = document.getElementById("btn-issue-save");
    if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
    if (drawerBackdrop) drawerBackdrop.addEventListener("click", closeDrawer);
    if (instructionBtn) instructionBtn.addEventListener("click", toggleInstructions);
    if (noteBtn) noteBtn.addEventListener("click", saveTaskNote);
    if (issueBtn) issueBtn.addEventListener("click", saveTaskIssue);
    if (planPersonelInput) planPersonelInput.addEventListener("change", updatePlanEndPreview);
    if (planDateInput) planDateInput.addEventListener("change", updatePlanEndPreview);
    if (planStartInput) planStartInput.addEventListener("change", updatePlanEndPreview);
    if (planDurationInput) planDurationInput.addEventListener("input", updatePlanEndPreview);
    if (planSaveBtn) planSaveBtn.addEventListener("click", saveManualPlanUpdate);
    document.querySelectorAll(".drawer-actions [data-action]").forEach((btn) => {
      btn.addEventListener("click", () => runTaskAction(btn.dataset.action));
    });
  }

  function focusTaskFromQuery() {
    const params = new URLSearchParams(window.location.search || "");
    const focusTaskId = params.get("focus_task");
    const openEdit = params.get("open_edit") === "1";
    if (!focusTaskId) return;
    const card = document.querySelector(`.task-card[data-asama-id="${focusTaskId}"]`);
    if (card) {
      card.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
      card.classList.add("drag-over");
      window.setTimeout(() => card.classList.remove("drag-over"), 1200);
    }
    openTaskDrawer(focusTaskId);
    if (openEdit) {
      window.setTimeout(() => {
        if (planStartInput) {
          planStartInput.focus();
          planStartInput.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
        }
      }, 250);
    }
  }

  Object.values(assignmentsData).forEach((item) => {
    if (!item || !item.id) return;
    state.events[String(item.id)] = toEvent(item);
  });

  document.querySelectorAll(".task-card.task-leaf, .task-card.assigned").forEach((card) => attachDragHandlers(card));
  rerenderAssignedCards();
  setupDropTargets();
  setupPlanContextMenu();
  bindDrawerActions();
  focusTaskFromQuery();
})();
