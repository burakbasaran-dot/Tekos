/**
 * TEKORA AI sohbet — Django API + CSRF (Ollama sunucu tarafta çağrılır).
 */
(function () {
  "use strict";

  let isListening = false;
  let isSpeaking = false;
  let voiceModeEnabled = true;
  let handsFreeEnabled = false;
  let waitingCommandAfterWakeWord = false;
  let currentUtterance = null;

  function getCsrfToken() {
    var input = document.querySelector('[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    if (typeof getCookie === "function") return getCookie("csrftoken");
    return null;
  }

  function scrollToBottom(container) {
    requestAnimationFrame(function () {
      container.scrollTop = container.scrollHeight;
    });
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function formatAssistantHtml(text) {
    var safe = escapeHtml(text);
    return safe.replace(/\n/g, "<br>");
  }

  function init() {
    var root = document.getElementById("tekora-chat-root");
    if (!root) return;

    var chatUrl = root.getAttribute("data-chat-url");
    if (!chatUrl) return;

    var messagesEl = document.getElementById("tekora-messages");
    var input = document.getElementById("tekora-input");
    var sendBtn = document.getElementById("tekora-send");
    var voiceBtn = document.getElementById("tekora-voice");
    var voiceStatusEl = document.getElementById("tekora-voice-status");
    var ttsEnable = document.getElementById("tekora-tts-enable");
    var ttsIndicator = document.getElementById("tekora-tts-indicator");
    var ttsLabel = document.getElementById("tekora-tts-label");
    var handsFreeEnable = document.getElementById("tekora-handsfree-enable");
    var handsFreeStatus = document.getElementById("tekora-handsfree-status");
    var handsFreeLabel = document.getElementById("tekora-handsfree-label");
    var errorEl = document.getElementById("tekora-error");
    var apEnable = document.getElementById("tekora-ap-enable");
    var apProduct = document.getElementById("tekora-ap-product");
    var apStock = document.getElementById("tekora-ap-stock");
    var apQty = document.getElementById("tekora-ap-qty");

    if (!messagesEl || !input || !sendBtn) return;

    try {
      try {
        handsFreeEnabled =
          localStorage.getItem("tekora_hands_free_enabled") === "true";
      } catch (ignoreLsHf) {
        handsFreeEnabled = false;
      }
      if (handsFreeEnable) {
        handsFreeEnable.checked = handsFreeEnabled;
      }

    var busy = false;

    /* ---- Voice (Web Speech API, tr-TR) — yalnızca istemci; ses sunucuya gitmez ---- */
    var SpeechRecognitionCtor =
      window.SpeechRecognition || window.webkitSpeechRecognition || null;
    var voiceRecognition = null;
    var voiceListening = false;
    var voiceUserStop = false;
    var voiceUnsupported = !SpeechRecognitionCtor;
    var speechCapable =
      !!SpeechRecognitionCtor &&
      !(
        typeof window.isSecureContext === "boolean" &&
        !window.isSecureContext
      );
    try {
      voiceModeEnabled =
        speechCapable &&
        localStorage.getItem("tekora_voice_enabled") !== "false";
    } catch (ignoreLsVoice) {
      voiceModeEnabled = speechCapable;
    }
    var voiceAutoSendTimer = null;
    var voiceSessionHadError = false;
    var lastVoiceAutoSent = "";
    var lastVoiceAutoSentAt = 0;

    /* ---- Hands-free (wake: "tekora") ---- */
    var hfRecognition = null;
    var hfListening = false;
    var hfRestartTimer = null;
    var hfConsecutiveErrors = 0;
    var hfTtsActive = false;
    var manualVoiceSession = false;
    var HF_MAX_ERRORS = 8;
    var HF_BASE_RESTART_MS = 500;
    var HF_WAKE_COMPACT = [
      "dekora",
      "tekrar",
      "tekora",
      "tekoro",
      "tekara",
      "tekor",
      "dekor",
    ];

    /* ---- TTS (speechSynthesis) — yalnızca istemci ---- */
    var ttsVoiceResolved = false;
    var ttsVoiceCache = null;

    function tekoraVoiceLog(line) {
      try {
        console.log("[TEKORA VOICE] " + line);
      } catch (ignoreLog) {}
    }

    function syncHandsFreeToggleUi() {
      if (!handsFreeLabel || !handsFreeEnable) return;
      handsFreeLabel.classList.toggle(
        "tekora-app__handsfree-label--active",
        !!handsFreeEnable.checked
      );
    }

    function setHandsFreeStatusUi(text, isError) {
      if (!handsFreeStatus) return;
      if (!text || !handsFreeEnable || !handsFreeEnable.checked) {
        handsFreeStatus.hidden = true;
        handsFreeStatus.textContent = "";
        handsFreeStatus.classList.remove("is-error");
        return;
      }
      handsFreeStatus.hidden = false;
      handsFreeStatus.textContent = text;
      if (isError) handsFreeStatus.classList.add("is-error");
      else handsFreeStatus.classList.remove("is-error");
    }

    function normalizeWakeText(s) {
      var t = String(s || "").toLowerCase();
      t = t
        .replace(/ğ/g, "g")
        .replace(/ü/g, "u")
        .replace(/ş/g, "s")
        .replace(/ı/g, "i")
        .replace(/i̇/g, "i")
        .replace(/ö/g, "o")
        .replace(/ç/g, "c")
        .replace(/â/g, "a")
        .replace(/î/g, "i")
        .replace(/û/g, "u");
      t = t.replace(/[^a-z0-9\s]/gi, " ");
      t = t.replace(/\s+/g, " ").trim();
      return t;
    }

    function compactWake(s) {
      return normalizeWakeText(s).replace(/\s/g, "");
    }

    function containsWakeNormalized(text) {
      var c = compactWake(text);
      if (!c) return false;
      var i;
      for (i = 0; i < HF_WAKE_COMPACT.length; i++) {
        if (c.indexOf(HF_WAKE_COMPACT[i]) !== -1) return true;
      }
      return false;
    }

    function stripWakeFromRaw(raw) {
      var s = String(raw || "").trim();
      var patterns = [
        /\bdekora\b/gi,
        /\btekrar\b/gi,
        /\btek\s*o\s*r\s*a\b/gi,
        /\btek\s*ora\b/gi,
        /\btek\s*o\s*ra\b/gi,
        /\btek\s*oro\b/gi,
        /\btek\s*or\b/gi,
        /\btek\s*ara\b/gi,
        /\bdekor\b/gi,
        /\btekora\b/gi,
      ];
      var i;
      for (i = 0; i < patterns.length; i++) {
        s = s.replace(patterns[i], " ");
      }
      return s.replace(/\s+/g, " ").trim();
    }

    function remainderAfterWake(raw) {
      var s = stripWakeFromRaw(raw);
      if (!containsWakeNormalized(raw)) return String(raw || "").trim();
      if (s.length > 0 && !containsWakeNormalized(s)) return s;
      var c = compactWake(raw);
      var ti;
      for (ti = 0; ti < HF_WAKE_COMPACT.length; ti++) {
        var w = HF_WAKE_COMPACT[ti];
        var ix = c.indexOf(w);
        if (ix !== -1) {
          return (c.slice(0, ix) + " " + c.slice(ix + w.length))
            .replace(/\s+/g, " ")
            .trim();
        }
      }
      return s;
    }

    function shouldAllowHandsFreeListening() {
      if (!handsFreeEnable || !handsFreeEnable.checked) return false;
      if (!voiceModeEnabled) return false;
      if (busy) return false;
      if (manualVoiceSession) return false;
      if (hfTtsActive || isSpeaking) return false;
      var synth = window.speechSynthesis;
      if (synth && (synth.speaking || synth.pending)) return false;
      if (voiceListening) return false;
      if (hfConsecutiveErrors >= HF_MAX_ERRORS) return false;
      return true;
    }

    function stopHandsFreeRecognition() {
      clearTimeout(hfRestartTimer);
      hfRestartTimer = null;
      if (!hfRecognition) return;
      try {
        hfRecognition.stop();
      } catch (ignoreStop) {}
    }

    function processHandsFreeFinalTranscript(transcript) {
      var raw = String(transcript || "").replace(/\s+/g, " ").trim();
      if (!raw) return;

      if (waitingCommandAfterWakeWord) {
        var cmdWait = raw.trim();
        if (!cmdWait) {
          setHandsFreeStatusUi("Dinliyorum...", false);
          return;
        }
        waitingCommandAfterWakeWord = false;
        tekoraVoiceLog("hands-free command sent: " + cmdWait);
        input.value = cmdWait;
        autoResizeTextarea();
        if (handsFreeEnable.checked) {
          setHandsFreeStatusUi("Tekora kelimesi bekleniyor...", false);
        }
        sendTekoraChat(true);
        return;
      }

      if (!containsWakeNormalized(raw)) return;

      tekoraVoiceLog("wake word detected");
      var afterWake = remainderAfterWake(raw);
      if (afterWake) {
        waitingCommandAfterWakeWord = false;
        tekoraVoiceLog("hands-free command sent: " + afterWake);
        input.value = afterWake;
        autoResizeTextarea();
        if (handsFreeEnable.checked) {
          setHandsFreeStatusUi("Tekora kelimesi bekleniyor...", false);
        }
        sendTekoraChat(true);
        return;
      }

      waitingCommandAfterWakeWord = true;
      tekoraVoiceLog("waiting command after wake word");
      setHandsFreeStatusUi("Dinliyorum...", false);
    }

    function tryResumeHandsFreeListening(fromRestart) {
      clearTimeout(hfRestartTimer);
      hfRestartTimer = null;
      if (!handsFreeEnable || !handsFreeEnable.checked) return;
      if (!shouldAllowHandsFreeListening()) return;
      if (hfRecognition) return;
      var delay = HF_BASE_RESTART_MS;
      if (fromRestart) {
        delay += Math.min(7000, 280 * hfConsecutiveErrors * hfConsecutiveErrors);
      }
      hfRestartTimer = setTimeout(function () {
        hfRestartTimer = null;
        if (!shouldAllowHandsFreeListening()) return;
        beginHandsFreeListening(!!fromRestart, false);
      }, delay);
    }

    function beginHandsFreeListening(logRestarted, logSessionStart) {
      if (!handsFreeEnable || !handsFreeEnable.checked) return;
      if (!SpeechRecognitionCtor) return;
      if (typeof window.isSecureContext === "boolean" && !window.isSecureContext) {
        return;
      }
      if (!shouldAllowHandsFreeListening()) return;
      if (hfRecognition) return;

      hfRecognition = new SpeechRecognitionCtor();
      hfRecognition.lang = "tr-TR";
      hfRecognition.continuous = false;
      hfRecognition.interimResults = true;
      hfRecognition.maxAlternatives = 1;

      hfRecognition.onresult = function (ev) {
        if (!handsFreeEnable.checked || busy) return;
        var i;
        var interim = "";
        var combined = "";
        for (i = ev.resultIndex; i < ev.results.length; i++) {
          var res = ev.results[i];
          var piece = res[0] && res[0].transcript ? res[0].transcript : "";
          combined += piece;
          if (res.isFinal) {
            processHandsFreeFinalTranscript(piece);
          } else {
            interim += piece;
          }
        }
        try {
          console.log(
            "[TEKORA VOICE] hands-free transcript:",
            combined
          );
        } catch (ignoreHfTranscriptLog) {}
        if (
          waitingCommandAfterWakeWord &&
          handsFreeEnable.checked &&
          interim.trim()
        ) {
          setHandsFreeStatusUi("Dinliyorum… " + interim.trim(), false);
        }
      };

      hfRecognition.onerror = function (ev) {
        var code = ev && ev.error ? ev.error : "";
        hfListening = false;
        hfRecognition = null;
        if (code === "aborted") return;
        if (code === "no-speech") {
          tryResumeHandsFreeListening(false);
          return;
        }
        hfConsecutiveErrors++;
        if (
          code === "audio-capture" ||
          code === "not-readable" ||
          code === "invalid-audio-session"
        ) {
          setHandsFreeStatusUi("Mikrofon dinleme başlatılamadı.", true);
        }
        if (code === "not-allowed" || code === "service-not-allowed") {
          hfConsecutiveErrors = HF_MAX_ERRORS;
          setHandsFreeStatusUi("Mikrofon dinleme başlatılamadı.", true);
          if (handsFreeEnable) handsFreeEnable.checked = false;
          syncHandsFreeToggleUi();
          tekoraVoiceLog("hands-free disabled (permission)");
          return;
        }
        if (!handsFreeEnable.checked) return;
        if (hfConsecutiveErrors >= HF_MAX_ERRORS) {
          setHandsFreeStatusUi(
            "Mikrofon dinleme başlatılamadı.",
            true
          );
          return;
        }
        tryResumeHandsFreeListening(true);
      };

      hfRecognition.onend = function () {
        hfListening = false;
        hfRecognition = null;
        if (!handsFreeEnable || !handsFreeEnable.checked) return;
        if (hfTtsActive || isSpeaking) return;
        if (manualVoiceSession || voiceListening || busy) return;
        hfConsecutiveErrors = 0;
        tryResumeHandsFreeListening(false);
      };

      try {
        hfRecognition.start();
        hfListening = true;
        if (logRestarted) tekoraVoiceLog("hands-free restarted");
        else if (logSessionStart) tekoraVoiceLog("hands-free started");
        if (handsFreeEnable.checked && !waitingCommandAfterWakeWord) {
          setHandsFreeStatusUi("Tekora kelimesi bekleniyor...", false);
        }
      } catch (ignoreStart) {
        hfRecognition = null;
        hfListening = false;
        hfConsecutiveErrors++;
        setHandsFreeStatusUi("Mikrofon dinleme başlatılamadı.", true);
        if (handsFreeEnable.checked && hfConsecutiveErrors < HF_MAX_ERRORS) {
          tryResumeHandsFreeListening(true);
        }
      }
    }

    function setTtsIndicator(visible) {
      if (!ttsIndicator) return;
      ttsIndicator.hidden = !visible;
    }

    function syncTtsToggleUi() {
      if (!ttsLabel || !ttsEnable) return;
      ttsLabel.classList.toggle(
        "tekora-app__tts-label--active",
        !!ttsEnable.checked
      );
    }

    function invalidateTtsVoiceCache() {
      ttsVoiceResolved = false;
      ttsVoiceCache = null;
    }

    function pickTurkishVoice() {
      if (!window.speechSynthesis) return null;
      var voices = window.speechSynthesis.getVoices() || [];
      if (!voices.length) return null;
      if (ttsVoiceResolved) return ttsVoiceCache;
      var bestTr = null;
      var i;
      for (i = 0; i < voices.length; i++) {
        var lang = (voices[i].lang || "").toLowerCase();
        if (lang.indexOf("tr") !== -1) {
          if (lang === "tr-tr" || lang.indexOf("tr-tr") === 0) {
            ttsVoiceCache = voices[i];
            ttsVoiceResolved = true;
            return ttsVoiceCache;
          }
          if (!bestTr) bestTr = voices[i];
        }
      }
      ttsVoiceCache = bestTr;
      ttsVoiceResolved = true;
      return ttsVoiceCache;
    }

    if (window.speechSynthesis) {
      try {
        window.speechSynthesis.addEventListener(
          "voiceschanged",
          invalidateTtsVoiceCache
        );
      } catch (ignoreSynth) {}
    }

    if (ttsEnable) {
      ttsEnable.addEventListener("change", function () {
        syncTtsToggleUi();
        if (!ttsEnable.checked && window.speechSynthesis) {
          try {
            window.speechSynthesis.cancel();
          } catch (ignoreCancel) {}
          isSpeaking = false;
          currentUtterance = null;
          setTtsIndicator(false);
        }
      });
      syncTtsToggleUi();
    }

    if (handsFreeEnable) {
      handsFreeEnable.addEventListener("change", function () {
        handsFreeEnabled = !!handsFreeEnable.checked;
        try {
          localStorage.setItem(
            "tekora_hands_free_enabled",
            handsFreeEnabled ? "true" : "false"
          );
        } catch (ignorePersistHf) {}
        syncHandsFreeToggleUi();
        if (handsFreeEnable.checked) {
          tekoraVoiceLog("hands-free enabled");
          waitingCommandAfterWakeWord = false;
          hfConsecutiveErrors = 0;
          setHandsFreeStatusUi("Tekora kelimesi bekleniyor...", false);
          beginHandsFreeListening(false, true);
        } else {
          waitingCommandAfterWakeWord = false;
          stopHandsFreeRecognition();
          setHandsFreeStatusUi("", false);
        }
      });
      syncHandsFreeToggleUi();
    }

    function speakTekoraReply(plainText) {
      if (!window.speechSynthesis) return;
      if (typeof SpeechSynthesisUtterance === "undefined") return;
      if (!ttsEnable || !ttsEnable.checked) return;
      if (voiceListening && voiceRecognition) return;

      var raw = String(plainText || "").replace(/\s+/g, " ").trim();
      if (!raw) return;
      if (raw.length > 32000) raw = raw.slice(0, 32000);

      hfTtsActive = true;
      stopHandsFreeRecognition();

      try {
        window.speechSynthesis.cancel();
      } catch (ignoreCancel2) {}
      isSpeaking = false;
      currentUtterance = null;

      var u = new SpeechSynthesisUtterance(raw);
      u.lang = "tr-TR";
      u.rate = 1;
      u.pitch = 1;
      u.volume = 1;

      var voice = pickTurkishVoice();
      if (voice) u.voice = voice;

      u.onend = function () {
        if (currentUtterance === u) currentUtterance = null;
        isSpeaking = false;
        setTtsIndicator(false);
        tekoraVoiceLog("speaking ended");
        hfTtsActive = false;
        tryResumeHandsFreeListening(false);
      };
      u.onerror = function () {
        if (currentUtterance === u) currentUtterance = null;
        isSpeaking = false;
        setTtsIndicator(false);
        tekoraVoiceLog("speaking ended");
        hfTtsActive = false;
        tryResumeHandsFreeListening(false);
      };

      currentUtterance = u;
      isSpeaking = true;
      setTtsIndicator(true);
      tekoraVoiceLog("speaking started");
      try {
        window.speechSynthesis.speak(u);
      } catch (ignoreSpeak) {
        currentUtterance = null;
        isSpeaking = false;
        setTtsIndicator(false);
        tekoraVoiceLog("speaking ended");
        hfTtsActive = false;
        tryResumeHandsFreeListening(false);
      }
    }

    function setVoiceStatus(text, isError) {
      if (!voiceStatusEl) return;
      if (!text) {
        voiceStatusEl.hidden = true;
        voiceStatusEl.textContent = "";
        voiceStatusEl.classList.remove("is-error");
        return;
      }
      voiceStatusEl.hidden = false;
      voiceStatusEl.textContent = text;
      if (isError) voiceStatusEl.classList.add("is-error");
      else voiceStatusEl.classList.remove("is-error");
    }

    function setVoiceListeningUI(on) {
      voiceListening = on;
      isListening = on;
      if (voiceBtn) {
        voiceBtn.classList.toggle("is-listening", on);
        voiceBtn.setAttribute("aria-pressed", on ? "true" : "false");
      }
      if (on) {
        if (window.speechSynthesis) {
          try {
            window.speechSynthesis.cancel();
          } catch (ignore) {}
        }
        isSpeaking = false;
        currentUtterance = null;
        setTtsIndicator(false);
        setVoiceStatus("Dinleniyor…", false);
        if (voiceModeEnabled) tekoraVoiceLog("listening started");
      } else if (voiceStatusEl && !voiceStatusEl.classList.contains("is-error")) {
        setVoiceStatus("", false);
      }
    }

    function mergeVoiceTextIntoInput(text) {
      var t = (text || "").trim();
      if (!t) return;
      var cur = (input.value || "").trim();
      input.value = cur ? cur + " " + t : t;
      autoResizeTextarea();
    }

    function stopVoiceRecognition() {
      voiceUserStop = true;
      if (voiceRecognition) {
        try {
          voiceRecognition.stop();
        } catch (ignore) {}
      }
    }

    function cancelVoiceAutoSend() {
      if (voiceAutoSendTimer) {
        clearTimeout(voiceAutoSendTimer);
        voiceAutoSendTimer = null;
      }
    }

    function scheduleVoiceAutoSend() {
      cancelVoiceAutoSend();
      var snapshot = (input.value || "").trim();
      if (!snapshot || busy) return;
      if (
        snapshot === lastVoiceAutoSent &&
        Date.now() - lastVoiceAutoSentAt < 2500
      ) {
        return;
      }
      voiceAutoSendTimer = setTimeout(function () {
        voiceAutoSendTimer = null;
        if (busy) return;
        var msg = (input.value || "").trim();
        if (!msg) return;
        if (msg === lastVoiceAutoSent && Date.now() - lastVoiceAutoSentAt < 2500) {
          return;
        }
        if (typeof window.sendMessage === "function") {
          window.sendMessage(true);
        } else {
          sendBtn.click();
        }
      }, 220);
    }

    function startVoiceRecognition() {
      if (!SpeechRecognitionCtor) {
        setVoiceStatus("Tarayıcı ses tanımayı desteklemiyor.", true);
        return;
      }
      if (typeof window.isSecureContext === "boolean" && !window.isSecureContext) {
        setVoiceStatus("Tarayıcı ses tanımayı desteklemiyor.", true);
        return;
      }
      if (busy) return;

      manualVoiceSession = true;
      stopHandsFreeRecognition();

      cancelVoiceAutoSend();
      var synth = window.speechSynthesis;
      var hadOngoingSpeech =
        isSpeaking ||
        (synth &&
          (synth.speaking || synth.pending || !!currentUtterance));
      if (synth) {
        try {
          synth.cancel();
        } catch (ignoreTts) {}
      }
      if (hadOngoingSpeech) tekoraVoiceLog("interrupted speech");
      isSpeaking = false;
      currentUtterance = null;
      setTtsIndicator(false);
      voiceUserStop = false;
      voiceSessionHadError = false;
      voiceRecognition = new SpeechRecognitionCtor();
      voiceRecognition.lang = "tr-TR";
      voiceRecognition.continuous = true;
      voiceRecognition.interimResults = true;
      voiceRecognition.maxAlternatives = 1;

      voiceRecognition.onresult = function (ev) {
        var interim = "";
        for (var i = ev.resultIndex; i < ev.results.length; i++) {
          var res = ev.results[i];
          var piece = res[0] && res[0].transcript ? res[0].transcript : "";
          if (res.isFinal) {
            var chunk = piece.trim();
            if (chunk) mergeVoiceTextIntoInput(chunk);
          } else {
            interim += piece;
          }
        }
        if (voiceListening) {
          var base = (input.value || "").trim();
          var preview = interim.trim()
            ? (base ? base + " " : "") + interim.trim()
            : base;
          setVoiceStatus(
            preview ? "Dinleniyor… " + preview : "Dinleniyor…",
            false
          );
        }
      };

      voiceRecognition.onerror = function (ev) {
        var code = ev && ev.error ? ev.error : "";
        if (code === "aborted" && voiceUserStop) return;
        manualVoiceSession = false;
        var msg = "Ses tanıma hatası.";
        if (code === "not-allowed" || code === "service-not-allowed") {
          msg = "Mikrofon erişimi alınamadı.";
        } else if (code === "no-speech") {
          msg = "Konuşma algılanmadı; tekrar deneyin.";
        } else if (code === "audio-capture") {
          msg = "Mikrofon kullanılamıyor.";
        } else if (code === "network") {
          msg = "Ses tanıma ağı hatası.";
        }
        voiceSessionHadError = true;
        setVoiceListeningUI(false);
        setVoiceStatus(msg, true);
        voiceRecognition = null;
        cancelVoiceAutoSend();
      };

      voiceRecognition.onend = function () {
        manualVoiceSession = false;
        voiceRecognition = null;
        setVoiceListeningUI(false);
        if (!voiceSessionHadError) {
          scheduleVoiceAutoSend();
        }
        voiceSessionHadError = false;
        tryResumeHandsFreeListening(false);
      };

      try {
        voiceRecognition.start();
        setVoiceListeningUI(true);
        setVoiceStatus("Dinleniyor…", false);
      } catch (err) {
        manualVoiceSession = false;
        setVoiceListeningUI(false);
        setVoiceStatus("Ses tanıma başlatılamadı.", true);
        voiceRecognition = null;
        tryResumeHandsFreeListening(false);
      }
    }

    if (handsFreeEnable && (voiceUnsupported || !voiceModeEnabled)) {
      handsFreeEnable.disabled = true;
    }

    if (voiceBtn) {
      if (voiceUnsupported) {
        voiceBtn.disabled = true;
        voiceBtn.title =
          "Ses tanıma bu ortamda kullanılamıyor (HTTPS veya desteklenen tarayıcı gerekir).";
      }
      voiceBtn.addEventListener("click", function () {
        if (voiceUnsupported) return;
        if (voiceListening && voiceRecognition) {
          stopVoiceRecognition();
          return;
        }
        if (busy) return;
        setVoiceStatus("", false);
        startVoiceRecognition();
      });
    }

    function setError(msg) {
      if (!msg) {
        errorEl.hidden = true;
        errorEl.textContent = "";
        return;
      }
      errorEl.hidden = false;
      errorEl.textContent = msg;
    }

    function appendUserMessage(text) {
      var row = document.createElement("div");
      row.className = "tekora-msg tekora-msg--user";
      row.innerHTML =
        '<div class="tekora-msg__avatar" aria-hidden="true">Siz</div>' +
        '<div class="tekora-msg__bubble"><p>' +
        escapeHtml(text).replace(/\n/g, "<br>") +
        "</p></div>";
      messagesEl.appendChild(row);
      scrollToBottom(messagesEl);
    }

    function appendAssistantMessage(html, isError) {
      var row = document.createElement("div");
      row.className =
        "tekora-msg tekora-msg--assistant" + (isError ? " tekora-msg--error" : "");
      row.innerHTML =
        '<div class="tekora-msg__avatar" aria-hidden="true">T</div>' +
        '<div class="tekora-msg__bubble">' +
        (isError ? "<p>" + html + "</p>" : "<p>" + html + "</p>") +
        "</div>";
      messagesEl.appendChild(row);
      scrollToBottom(messagesEl);
    }

    function appendLoading() {
      var row = document.createElement("div");
      row.className =
        "tekora-msg tekora-msg--assistant tekora-msg--loading tekora-loading-row";
      row.innerHTML =
        '<div class="tekora-msg__avatar" aria-hidden="true">T</div>' +
        '<div class="tekora-msg__bubble" aria-busy="true">' +
        '<span class="tekora-typing-dot"></span>' +
        '<span class="tekora-typing-dot"></span>' +
        '<span class="tekora-typing-dot"></span>' +
        "</div>";
      messagesEl.appendChild(row);
      scrollToBottom(messagesEl);
      return row;
    }

    function removeLoading(row) {
      if (row && row.parentNode) row.parentNode.removeChild(row);
    }

    function autoResizeTextarea() {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 160) + "px";
    }

    input.addEventListener("input", autoResizeTextarea);

    function sendTekoraChat(fromVoiceAuto) {
      if (busy) return;
      if (voiceListening && voiceRecognition) {
        stopVoiceRecognition();
      }
      var text = (input.value || "").trim();
      if (!text) return;

      var token = getCsrfToken();
      if (!token) {
        setError("Oturum güvenlik anahtarı bulunamadı. Sayfayı yenileyin.");
        return;
      }

      var requestBody = { message: text };
      if (apEnable && apEnable.checked) {
        var prod =
          apProduct && apProduct.value ? String(apProduct.value).trim() : "";
        var qtyRaw = apQty && apQty.value ? String(apQty.value).trim() : "";
        var qtyNum = parseFloat(qtyRaw.replace(",", "."));
        if (!prod) {
          setError("Onay talebi için ürün / malzeme adı girin.");
          return;
        }
        if (!qtyRaw || isNaN(qtyNum) || qtyNum <= 0) {
          setError("Onay talebi için geçerli önerilen miktar girin.");
          return;
        }
        requestBody.confirm_purchase_request = true;
        requestBody.approval_payload = { product: prod, suggested_quantity: qtyNum };
        var stRaw =
          apStock && apStock.value ? String(apStock.value).trim() : "";
        if (stRaw) {
          var stNum = parseFloat(stRaw.replace(",", "."));
          if (!isNaN(stNum)) {
            requestBody.approval_payload.current_stock = stNum;
          }
        }
      }

      if (fromVoiceAuto) {
        lastVoiceAutoSent = text;
        lastVoiceAutoSentAt = Date.now();
      }

      stopHandsFreeRecognition();

      setError("");
      busy = true;
      sendBtn.disabled = true;
      input.disabled = true;
      if (voiceBtn) {
        voiceBtn.disabled = true;
        if (voiceListening && voiceRecognition) {
          stopVoiceRecognition();
        }
      }

      appendUserMessage(text);
      input.value = "";
      autoResizeTextarea();

      var loadingRow = appendLoading();

      fetch(chatUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": token,
        },
        body: JSON.stringify(requestBody),
      })
        .then(function (res) {
          return res.text().then(function (txt) {
            var data = {};
            try {
              data = txt ? JSON.parse(txt) : {};
            } catch (ignore) {
              data = {
                status: "error",
                error: "Sunucu yanıtı JSON değil: " + txt.slice(0, 180),
              };
            }
            return { ok: res.ok, status: res.status, data: data };
          });
        })
        .then(function (result) {
          removeLoading(loadingRow);
          var data = result.data || {};
          if (!result.ok || data.status !== "ok") {
            var err =
              (data && data.error) ||
              "İstek başarısız (HTTP " + result.status + ").";
            appendAssistantMessage(escapeHtml(err), true);
            return;
          }
          var reply = data.reply || "";
          appendAssistantMessage(formatAssistantHtml(reply), false);
          speakTekoraReply(reply);
        })
        .catch(function () {
          removeLoading(loadingRow);
          appendAssistantMessage(
            escapeHtml("Ağ hatası veya sunucuya ulaşılamadı."),
            true
          );
        })
        .finally(function () {
          busy = false;
          sendBtn.disabled = false;
          input.disabled = false;
          if (voiceBtn) voiceBtn.disabled = voiceUnsupported;
          input.focus();
          scrollToBottom(messagesEl);
          tryResumeHandsFreeListening(false);
        });
    }

    window.sendMessage = function (fromVoiceAuto) {
      sendTekoraChat(!!fromVoiceAuto);
    };

    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendTekoraChat(false);
      }
    });

    sendBtn.addEventListener("click", function () {
      sendTekoraChat(false);
    });

    try {
      console.log("[TEKORA VOICE] state initialized");
    } catch (ignoreStateLog) {}
    } catch (tekoraInitErr) {
      try {
        console.error("[TEKORA VOICE] init failed", tekoraInitErr);
      } catch (ignoreErrLog) {}
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
