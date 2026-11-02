const $ = id => document.getElementById(id);
const STAGES = {
  capture_closed: "Microfone fechado",
  audio_ready: "Áudio preparado",
  first_transcript: "1º trecho transcrito",
  transcript_done: "Transcrição completa",
  analysis_done: "Muletas e velocidade",
  ai_request_sent: "Pedido enviado à CLI",
  ai_first_word: "1ª palavra da IA",
  ai_done: "Resposta completa"
};

let mode = "rehearsal";
let recording = false;
let levelTimer = null;
let parts = [];
let aiText = "";
let cachedPrompts = null;
let lastTranscript = "";
let lastAnalysis = null;
let lastRequestData = {
  rehearsal: null,
  manager: null,
  presentation: null
};

// Visualização de Onda no Canvas
const canvas = $("waveform");
const ctx = canvas.getContext("2d");
let currentLevel = 0;
let wavePhase = 0;
let waveAnimFrame = null;

function resizeWaveform() {
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(300, Math.floor(rect.width * dpr));
  canvas.height = Math.floor(80 * dpr);
  drawWaveform();
}
window.addEventListener("resize", resizeWaveform);

function drawWaveform() {
  if (!ctx) return;
  const w = canvas.width;
  const h = canvas.height;
  const cy = h / 2;
  ctx.clearRect(0, 0, w, h);

  // Linhas guias horizontais sutis da cabine
  ctx.strokeStyle = "rgba(255, 255, 255, 0.04)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, cy - 14); ctx.lineTo(w, cy - 14);
  ctx.moveTo(0, cy + 14); ctx.lineTo(w, cy + 14);
  ctx.stroke();

  if (!recording || currentLevel <= 0.001) {
    // Linha reta limpa e plana em repouso
    ctx.strokeStyle = "#38383e";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(0, cy);
    ctx.lineTo(w, cy);
    ctx.stroke();
    return;
  }

  // Onda acústica ativa respondendo exclusivamente ao level real
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const amplitude = Math.min(h * 0.42, currentLevel * h * 2.5);
  ctx.strokeStyle = "#ef4444";
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(0, cy);
  const steps = 60;
  for (let i = 0; i <= steps; i++) {
    const progress = i / steps;
    const x = progress * w;
    const envelope = Math.sin(progress * Math.PI);
    const freq = 4 * Math.PI;
    const y = cy + Math.sin(progress * freq + (reducedMotion ? 0 : wavePhase)) * amplitude * envelope;
    ctx.lineTo(x, y);
  }
  ctx.stroke();
}

function startWaveAnimation() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    drawWaveform();
    return;
  }
  function loop() {
    if (!recording) {
      drawWaveform();
      return;
    }
    wavePhase += 0.15;
    drawWaveform();
    waveAnimFrame = requestAnimationFrame(loop);
  }
  waveAnimFrame = requestAnimationFrame(loop);
}

async function postJson(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body || {})
  });
  const contentType = response.headers.get("Content-Type") || "";
  if (contentType.startsWith("text/event-stream")) return response;
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Erro no pedido");
  return payload;
}

async function loadPrompts() {
  try {
    const res = await fetch("/api/prompts");
    if (!res.ok) throw new Error("Falha ao buscar prompts");
    cachedPrompts = await res.json();
    updateBackstage();
  } catch (err) {
    showError(err);
  }
}

function updateBackstage() {
  if (!cachedPrompts) return;
  const modeName = mode === "listen" ? "Listen" : mode === "rehearsal" ? "Ensaio" : mode === "manager" ? "Gestor" : "Apresentação";
  $("backstage-mode-label").textContent = "Modo: " + modeName;
  if (mode === "listen") {
    updateListenBackstage();
    return;
  }

  const sysPrompt = cachedPrompts.modes?.[mode]?.system_prompt || "";
  $("backstage-system-prompt").textContent = sysPrompt;
  $("system-prompt-len").textContent = "Tamanho: " + sysPrompt.length + " caracteres";

  $("backstage-context-note").textContent = cachedPrompts.context?.note || "";
  const filesCount = cachedPrompts.context?.files?.length || 0;
  $("backstage-context-files").textContent = "Arquivos em uso: nenhum (" + filesCount + " arquivos)";

  if (cachedPrompts.model && cachedPrompts.model.provider) {
    $("backstage-model-info").textContent = "Provedor: " + cachedPrompts.model.provider + " · Modelo: " + cachedPrompts.model.name;
  } else {
    $("backstage-model-info").textContent = "Informações do modelo: local / não informado";
  }

  updateBackstagePreview();
}

async function updateBackstagePreview() {
  let reqData = lastRequestData[mode];
  if (!reqData && mode === "manager" && $("idea").value.trim()) {
    reqData = {mode: "manager", idea: $("idea").value.trim(), target_language: $("target").value};
    lastRequestData.manager = reqData;
  }
  if (!reqData) {
    $("backstage-request-label").textContent = "Nenhum pedido enviado nesta sessão";
    $("backstage-request").textContent = "Nenhum pedido enviado nesta sessão";
    return;
  }
  try {
    const res = await postJson("/api/prompt-preview", reqData);
    $("backstage-request-label").textContent = "Reconstruído a partir dos dados desta tela";
    $("backstage-request").textContent = res.request;
  } catch (err) {
    $("backstage-request-label").textContent = "Nenhum pedido enviado nesta sessão";
    $("backstage-request").textContent = "Nenhum pedido enviado nesta sessão";
  }
}

function selectMode(next) {
  mode = next;
  const tabs = document.querySelectorAll("[role=tab]");
  tabs.forEach(tab => {
    const isSelected = tab.dataset.mode === mode;
    tab.setAttribute("aria-selected", String(isSelected));
    tab.tabIndex = isSelected ? 0 : -1;
  });
  $("panel-manager").hidden = mode !== "manager";
  $("panel-presentation").hidden = mode !== "presentation";
  $("panel-listen").hidden = mode !== "listen";
  document.body.classList.toggle("mode-listen", mode === "listen");
  updateBackstage();
  if (mode === "listen") {
    refreshListenContext().catch(() => {});
    return;
  }
  postJson("/api/prewarm", {mode}).catch(showError);
}

function showError(error) {
  $("error").textContent = error.message || String(error);
  setStatus("");
}

function setStatus(text) {
  $("status").textContent = text;
}

function resetOutput() {
  aiText = "";
  $("error").textContent = "";
  for (const id of ["transcript", "metrics", "ai", "latency"]) $(id).textContent = "";
  $("timeline-container").textContent = "";
  $("latency-note").textContent = "";
  for (const id of ["transcript-card", "ai-card", "latency-card"]) $(id).hidden = true;
  document.body.classList.remove("has-results");
}

function renderAnalysis(event) {
  lastAnalysis = event;
  const box = $("transcript");
  box.textContent = "";
  for (const word of event.words) {
    if (!word.filler) {
      box.append(word.text);
      continue;
    }
    const leading = word.text.match(/^\s*/)[0];
    box.append(leading);
    const mark = document.createElement("mark");
    mark.textContent = word.text.slice(leading.length);
    box.append(mark);
  }
  const fillers = Object.entries(event.fillers).map(([term, count]) => `${term} ×${count}`).join(", ") || "nenhuma";
  const items = [
    ["Velocidade", `${event.words_per_minute} palavras/min`],
    ["Muletas", `${event.filler_total} (${event.fillers_per_minute}/min)`],
    ["Quais", fillers],
    ["Pausas de 1 s ou mais", event.long_pauses],
    ["Tempo falando", `${event.speaking_seconds} s`]
  ];
  for (const [name, value] of items) {
    const item = document.createElement("span");
    item.append(`${name}: `);
    const strong = document.createElement("b");
    strong.textContent = value;
    item.append(strong);
    $("metrics").append(item);
  }

  if (mode === "rehearsal") {
    lastRequestData.rehearsal = {mode: "rehearsal", transcript: lastTranscript, analysis: event};
  } else if (mode === "presentation") {
    const currentPart = parts[Number($("part").value)] || {title: "Parte", text: $("script").value};
    lastRequestData.presentation = {mode: "presentation", part: currentPart, transcript: lastTranscript, analysis: event};
  }
  updateBackstagePreview();
}

function appendInline(parent, text) {
  text.split("**").forEach((piece, index) => {
    if (index % 2 === 0) {
      parent.append(piece);
      return;
    }
    const strong = document.createElement("strong");
    strong.textContent = piece;
    parent.append(strong);
  });
}

async function copyText(btn, text) {
  try {
    let copied = false;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        copied = true;
      } catch (clipErr) {}
    }
    if (!copied) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      copied = true;
    }
    const originalText = btn.innerHTML;
    btn.textContent = "Copiado!";
    btn.classList.add("copied");
    setTimeout(() => {
      btn.innerHTML = originalText;
      btn.classList.remove("copied");
    }, 2000);
  } catch (err) {
    showError("Erro ao copiar para a área de transferência.");
  }
}

function createPhraseCard(label, text) {
  const card = document.createElement("div");
  card.className = "phrase-card";

  const header = document.createElement("div");
  header.className = "phrase-header";

  const tag = document.createElement("span");
  tag.className = "phrase-tag";
  tag.textContent = label;
  header.appendChild(tag);

  const btn = document.createElement("button");
  btn.className = "copy-btn";
  btn.type = "button";
  btn.setAttribute("aria-label", "Copiar frase " + label.toLowerCase());
  btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect width="13" height="13" x="9" y="9" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copiar`;
  btn.addEventListener("click", () => copyText(btn, text));
  header.appendChild(btn);

  card.appendChild(header);

  const p = document.createElement("p");
  p.className = "phrase-text";
  p.textContent = text;
  card.appendChild(p);

  return card;
}

function extractPhrase(line, key) {
  const regex = new RegExp("^(?:[-*•\\d.]+\\s+)?\\*{0,2}" + key + "\\*{0,2}\\s*:\\s*(.*)$", "i");
  const m = line.match(regex);
  return m ? m[1].trim() : null;
}

function renderAnswer() {
  const box = $("ai");
  box.textContent = "";

  if (mode === "manager") {
    const lines = aiText.split("\n");
    let direta = "";
    let formal = "";
    for (const rawLine of lines) {
      const line = rawLine.trim();
      const d = extractPhrase(line, "Direta");
      if (d !== null) direta = d;
      const f = extractPhrase(line, "Formal");
      if (f !== null) formal = f;
    }
    if (direta || formal) {
      const container = document.createElement("div");
      container.className = "phrases-container";
      if (direta) container.appendChild(createPhraseCard("Direta", direta));
      if (formal) container.appendChild(createPhraseCard("Formal", formal));
      box.appendChild(container);
      return;
    }
  }

  for (const line of aiText.split("\n")) {
    if (!line.trim()) continue;
    const heading = line.startsWith("## ");
    const bullet = line.startsWith("- ");
    const block = document.createElement(heading ? "h3" : "p");
    if (bullet) block.className = "bullet";
    appendInline(block, heading ? line.slice(3) : bullet ? line.slice(2) : line);
    box.append(block);
  }
}

function renderLatency(event) {
  $("latency-card").hidden = false;
  const tbody = $("latency");
  tbody.textContent = "";
  const container = $("timeline-container");
  container.textContent = "";

  const stages = event.stages || {};
  let maxTime = 0;
  for (const stage of Object.keys(STAGES)) {
    if (stage in stages && stages[stage] > maxTime) maxTime = stages[stage];
  }

  if (maxTime > 0) {
    const bar = document.createElement("div");
    bar.className = "timeline-bar";
    bar.setAttribute("role", "img");
    bar.setAttribute("aria-label", `Linha do tempo: total ${maxTime.toFixed(2)}s`);

    let prev = 0;
    for (const [stage, label] of Object.entries(STAGES)) {
      if (!(stage in stages)) continue;
      const current = stages[stage];
      const delta = Math.max(0, current - prev);
      prev = current;
      const pct = Math.max(2, (delta / maxTime) * 100);

      const seg = document.createElement("div");
      seg.className = "timeline-segment " + getStageClass(stage);
      seg.style.width = pct + "%";
      seg.title = `${label}: ${current.toFixed(2)}s (+${delta.toFixed(2)}s)`;
      bar.appendChild(seg);
    }
    container.appendChild(bar);
  }

  for (const [stage, label] of Object.entries(STAGES)) {
    if (!(stage in stages)) continue;
    const row = tbody.insertRow();
    row.insertCell().textContent = label;
    const timeCell = row.insertCell();
    timeCell.textContent = stages[stage].toFixed(2) + " s";
    timeCell.className = "mono-num";
  }
  $("latency-note").textContent = event.warm_cli ? "CLI aquecida" : "CLI iniciada na hora";
}

function getStageClass(stage) {
  if (stage.includes("audio") || stage.includes("capture")) return "stage-vad";
  if (stage.includes("transcript")) return "stage-stt";
  if (stage.includes("analysis")) return "stage-analysis";
  if (stage.includes("ai")) return "stage-llm";
  return "stage-default";
}

function handleEvent(event) {
  if (event.event === "status") setStatus(event.message);
  if (event.event === "transcript") {
    $("transcript-card").hidden = false;
    document.body.classList.add("has-results");
    lastTranscript += event.text;
    $("transcript").append(event.text);
  }
  if (event.event === "analysis") {
    document.body.classList.add("has-results");
    renderAnalysis(event);
    setStatus("Gerando retorno...");
  }
  if (event.event === "ai") {
    $("ai-card").hidden = false;
    document.body.classList.add("has-results");
    aiText += event.text;
    renderAnswer();
    setStatus("");
  }
  if (event.event === "latency") renderLatency(event);
  if (event.event === "error") showError(event.message);
}

async function readEvents(response) {
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const {value, done} = await reader.read();
    if (done) return;
    buffer += value;
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop();
    for (const block of blocks) {
      if (block.startsWith("data: ")) {
        handleEvent(JSON.parse(block.slice(6)));
      }
    }
  }
}

async function pollLevel() {
  try {
    const state = await (await fetch("/api/state")).json();
    currentLevel = state.level || 0;
    const scale = Math.min(1, currentLevel * 5);
    const bar = $("meter").firstElementChild;
    if (bar) bar.style.transform = `scaleX(${scale})`;
    if (recording) {
      setStatus(`Gravando: ${state.seconds.toFixed(0)} s`);
      $("record-sub").textContent = `${state.seconds.toFixed(0)} s`;
    }
  } catch (err) {
    showError(err);
  }
}

async function startRecording() {
  resetOutput();
  lastTranscript = "";
  lastAnalysis = null;
  const partIndex = mode === "presentation" ? Number($("part").value) : null;
  const {device} = await postJson("/api/record/start", {
    mode,
    language: $("language").value || null,
    part_index: partIndex,
    target_language: $("target").value
  });
  recording = true;
  $("record").classList.add("recording");
  $("record-text").textContent = "Parar";
  $("record-sub").textContent = "No ar";
  $("record-icon").innerHTML = `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/></svg>`;
  $("record").title = device;
  startWaveAnimation();
  levelTimer = setInterval(() => pollLevel().catch(showError), 250);
}

async function stopRecording() {
  recording = false;
  clearInterval(levelTimer);
  const bar = $("meter").firstElementChild;
  if (bar) bar.style.transform = "scaleX(0)";
  $("record").classList.remove("recording");
  $("record-text").textContent = "Gravar";
  $("record-sub").textContent = "Clique para falar";
  $("record-icon").innerHTML = `<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/></svg>`;
  $("record").disabled = true;
  setStatus("Encerrando gravação...");
  drawWaveform();
  try {
    await readEvents(await postJson("/api/record/stop"));
  } finally {
    $("record").disabled = false;
    setStatus("");
  }
}

$("record").addEventListener("click", () => (recording ? stopRecording() : startRecording()).catch(showError));

// Navegação por Abas com Teclado (WCAG AA)
const tabButtons = Array.from(document.querySelectorAll("[role=tab]"));
tabButtons.forEach((tab, index) => {
  tab.addEventListener("click", () => selectMode(tab.dataset.mode));
  tab.addEventListener("keydown", (e) => {
    let nextIndex = -1;
    if (e.key === "ArrowRight") nextIndex = (index + 1) % tabButtons.length;
    else if (e.key === "ArrowLeft") nextIndex = (index - 1 + tabButtons.length) % tabButtons.length;
    else if (e.key === "Home") nextIndex = 0;
    else if (e.key === "End") nextIndex = tabButtons.length - 1;

    if (nextIndex !== -1) {
      e.preventDefault();
      tabButtons[nextIndex].focus();
      selectMode(tabButtons[nextIndex].dataset.mode);
    }
  });
});

// Controle da Gaveta Lateral de Bastidores
function openBackstage() {
  $("panel-backstage").hidden = false;
  $("backstage-overlay").hidden = false;
  $("toggle-backstage").setAttribute("aria-expanded", "true");
  updateBackstage();
  $("close-backstage").focus();
}

function closeBackstage() {
  $("panel-backstage").hidden = true;
  $("backstage-overlay").hidden = true;
  $("toggle-backstage").setAttribute("aria-expanded", "false");
  $("toggle-backstage").focus();
}

$("toggle-backstage").addEventListener("click", () => {
  if ($("panel-backstage").hidden) {
    openBackstage();
  } else {
    closeBackstage();
  }
});

$("close-backstage").addEventListener("click", closeBackstage);
$("backstage-overlay").addEventListener("click", closeBackstage);

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("panel-backstage").hidden) {
    closeBackstage();
  }
});

// Atualizações de preview no modo Gestor
$("idea").addEventListener("input", () => {
  const val = $("idea").value.trim();
  if (val) {
    lastRequestData.manager = {mode: "manager", idea: val, target_language: $("target").value};
    if (!$("panel-backstage").hidden) {
      updateBackstagePreview();
    }
  }
});

$("target").addEventListener("change", () => {
  if (lastRequestData.manager) {
    lastRequestData.manager.target_language = $("target").value;
    if (!$("panel-backstage").hidden) {
      updateBackstagePreview();
    }
  }
});

$("generate").addEventListener("click", async () => {
  resetOutput();
  $("generate").disabled = true;
  setStatus("Gerando frases...");
  const textVal = $("idea").value;
  lastRequestData.manager = {mode: "manager", idea: textVal, target_language: $("target").value};
  updateBackstagePreview();
  try {
    await readEvents(await postJson("/api/manager", {text: textVal, target_language: $("target").value}));
  } catch (error) {
    showError(error);
  } finally {
    $("generate").disabled = false;
    setStatus("");
  }
});

// Modo Apresentação: Carregar e selecionar partes
$("file").addEventListener("change", async () => {
  const file = $("file").files[0];
  if (file) $("script").value = await file.text();
});

function renderPartChips() {
  const container = $("parts-chips");
  container.textContent = "";
  if (!parts.length) {
    $("parts-container").hidden = true;
    return;
  }
  $("parts-container").hidden = false;
  parts.forEach((p, idx) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "part-chip" + (Number($("part").value) === idx ? " active" : "");
    chip.textContent = p.title || `Parte ${idx + 1}`;
    chip.addEventListener("click", () => {
      $("part").value = idx;
      showPart();
      renderPartChips();
    });
    container.appendChild(chip);
  });
}

$("load").addEventListener("click", async () => {
  try {
    ({parts} = await postJson("/api/script", {text: $("script").value}));
    $("part").textContent = "";
    parts.forEach((part, index) => $("part").add(new Option(part.title, index)));
    $("part").disabled = false;
    showPart();
    renderPartChips();
    setStatus(`${parts.length} parte(s) carregada(s)`);
  } catch (error) {
    showError(error);
  }
});

function showPart() {
  const selectedPart = parts[Number($("part").value)];
  $("part-text").textContent = selectedPart?.text || "";
  renderPartChips();
  if (selectedPart) {
    lastRequestData.presentation = {
      mode: "presentation",
      part: selectedPart,
      transcript: lastTranscript || "",
      analysis: lastAnalysis || {
        word_count: 0,
        speaking_seconds: 0,
        words_per_minute: 0,
        filler_total: 0,
        fillers_per_minute: 0,
        long_pauses: 0,
        longest_pause_seconds: 0,
        fillers: {}
      }
    };
    if (!$("panel-backstage").hidden) updateBackstagePreview();
  }
}
$("part").addEventListener("change", showPart);

resizeWaveform();
drawWaveform();
loadPrompts();
postJson("/api/prewarm", {mode}).catch(showError);
