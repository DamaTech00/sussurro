/* ══════════ Sussurro · v1 web ══════════
   Demo de gravador + transcrição ao vivo no navegador.
   Usa a Web Speech API (Chrome/Edge). Nada é enviado nem gravado.
*/
"use strict";

const $ = (s) => document.querySelector(s);

const els = {
  micBtn:    $("#mic-btn"),
  micLabel:  $("#mic-label"),
  status:    $("#rec-status"),
  timer:     $("#rec-timer"),
  lang:      $("#lang"),
  transcript:$("#transcript"),
  interim:   $("#interim"),
  wordCount: $("#word-count"),
  clear:     $("#btn-clear"),
  copy:      $("#btn-copy"),
  download:  $("#btn-download"),
  fallback:  $("#rec-fallback"),
};

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let recog = null;
let recording = false;
let timerId = null;
let seconds = 0;

/* ── toast ── */
let toastT = null;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastT);
  toastT = setTimeout(() => t.classList.remove("show"), 2200);
}

/* ── helpers ── */
function fmtTime(s) {
  const m = String(Math.floor(s / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `${m}:${ss}`;
}
function countWords() {
  const txt = els.transcript.innerText.trim();
  const n = txt ? txt.split(/\s+/).length : 0;
  els.wordCount.textContent = n === 1 ? "1 palavra" : `${n} palavras`;
}
function appendFinal(text) {
  text = text.trim();
  if (!text) return;
  const cur = els.transcript.innerText.trim();
  // capitaliza início de frase e adiciona espaço
  let chunk = text.charAt(0).toUpperCase() + text.slice(1);
  els.transcript.innerText = cur ? cur + " " + chunk : chunk;
  // mantém scroll no fim
  els.transcript.scrollTop = els.transcript.scrollHeight;
  countWords();
}

/* ── timer ── */
function startTimer() {
  seconds = 0;
  els.timer.textContent = "00:00";
  els.timer.classList.add("live");
  timerId = setInterval(() => {
    seconds++;
    els.timer.textContent = fmtTime(seconds);
  }, 1000);
}
function stopTimer() {
  clearInterval(timerId);
  els.timer.classList.remove("live");
}

/* ── recognition ── */
function buildRecog() {
  const r = new SR();
  r.lang = els.lang.value;
  r.continuous = true;
  r.interimResults = true;

  r.onresult = (e) => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const res = e.results[i];
      if (res.isFinal) appendFinal(res[0].transcript);
      else interim += res[0].transcript;
    }
    els.interim.textContent = interim ? " " + interim : "";
  };

  r.onerror = (e) => {
    if (e.error === "no-speech") return; // ignora silêncio
    if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      toast("Preciso de permissão pro microfone 🎙️");
      stopRecording();
    }
  };

  // continuous para sozinho em pausas longas; reinicia se ainda gravando
  r.onend = () => {
    if (recording) {
      try { r.start(); } catch (_) {}
    }
  };
  return r;
}

function startRecording() {
  recog = buildRecog();
  try {
    recog.start();
  } catch (_) {
    return;
  }
  recording = true;
  els.micBtn.classList.add("recording");
  els.micBtn.querySelector(".mic-emoji").textContent = "⏹️";
  els.micLabel.textContent = "Gravando… toque para parar";
  els.status.textContent = "Ouvindo você…";
  els.status.classList.add("live");
  startTimer();
}

function stopRecording() {
  recording = false;
  if (recog) { try { recog.stop(); } catch (_) {} }
  els.interim.textContent = "";
  els.micBtn.classList.remove("recording");
  els.micBtn.querySelector(".mic-emoji").textContent = "🎙️";
  els.micLabel.textContent = "Toque para falar";
  els.status.textContent = "Pronto pra ouvir você";
  els.status.classList.remove("live");
  stopTimer();
}

function toggleRecording() {
  if (recording) stopRecording();
  else startRecording();
}

/* ── actions ── */
els.clear.addEventListener("click", () => {
  els.transcript.innerText = "";
  els.interim.textContent = "";
  countWords();
  toast("Limpo ✨");
});

els.copy.addEventListener("click", async () => {
  const txt = els.transcript.innerText.trim();
  if (!txt) return toast("Nada pra copiar ainda");
  try {
    await navigator.clipboard.writeText(txt);
    toast("Copiado! 📋");
  } catch (_) {
    toast("Não consegui copiar :(");
  }
});

els.download.addEventListener("click", () => {
  const txt = els.transcript.innerText.trim();
  if (!txt) return toast("Grave ou escreva algo primeiro");
  const stamp = new Date().toISOString().slice(0, 16).replace("T", "_").replace(":", "-");
  const blob = new Blob([txt], { type: "text/plain;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `sussurro_${stamp}.txt`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  toast("Baixado ↓");
});

els.transcript.addEventListener("input", countWords);

els.lang.addEventListener("change", () => {
  if (recording) {            // reinicia com o novo idioma
    stopRecording();
    setTimeout(startRecording, 200);
  }
});

els.micBtn.addEventListener("click", toggleRecording);

/* ── nav / scroll-to-demo ── */
function scrollToDemo() {
  $("#demo").scrollIntoView({ behavior: "smooth", block: "center" });
}
$("#nav-try").addEventListener("click", scrollToDemo);
$("#hero-try").addEventListener("click", scrollToDemo);

/* ── feature detection ── */
if (!SR) {
  els.fallback.hidden = false;
  els.micBtn.disabled = true;
  els.micBtn.style.opacity = ".5";
  els.micBtn.style.cursor = "not-allowed";
  els.micLabel.textContent = "Transcrição ao vivo indisponível";
  els.status.textContent = "Use Chrome ou Edge";
}

countWords();
