// Aba Listen: consome /api/meeting/* e /api/listen/*, sem tocar no microfone do treinador.
const LISTEN_DEFAULT_NOTE = "As mudanças valem a partir da próxima sugestão.";
const listen = {
  source: null,
  running: false,
  finals: new Map(),
  workspace: null,
  editingName: null,
  editorDirty: false,
  promptDirty: false,
  armed: new Map()
};

function setListenError(message) {
  $("listen-error").textContent = message || "";
}

function setListenNote(message, isError = false) {
  $("listen-note").textContent = message || LISTEN_DEFAULT_NOTE;
  $("listen-note").classList.toggle("is-error", isError);
}

function errorText(error) {
  return error.message || String(error);
}

// Ação difícil de desfazer pede um segundo clique, sem caixa de diálogo do navegador.
function armOrRun(button, armedLabel, action) {
  const pending = listen.armed.get(button);
  if (pending) {
    clearTimeout(pending.timer);
    listen.armed.delete(button);
    button.textContent = pending.label;
    button.classList.remove("is-armed");
    action();
    return;
  }
  const label = button.textContent;
  const timer = setTimeout(() => {
    listen.armed.delete(button);
    button.textContent = label;
    button.classList.remove("is-armed");
  }, 4000);
  listen.armed.set(button, {label, timer});
  button.textContent = armedLabel;
  button.classList.add("is-armed");
}

function closeListenSource() {
  if (!listen.source) return;
  listen.source.close();
  listen.source = null;
}

function setListenRunning(running, device) {
  listen.running = running;
  $("listen-toggle").textContent = running ? "Parar" : "Começar a ouvir";
  $("listen-toggle").classList.toggle("is-live", running);
  $("listen-generate").disabled = !running;
  $("listen-status").textContent = running ? `Ouvindo: ${device || "áudio do sistema"}` : "Parado";
  $("listen-status").classList.toggle("is-live", running);
  if (running) return;
  $("listen-partial").textContent = "";
  $("listen-meter-fill").style.transform = "scaleX(0)";
  closeListenSource();
}

function clearListenOutput() {
  listen.finals.clear();
  for (const id of ["listen-finals", "listen-partial", "listen-question", "listen-suggestion", "listen-timing"]) {
    $(id).textContent = "";
  }
}

function renderListenFinal(item) {
  listen.finals.set(item.id, item.text);
  const line = document.createElement("p");
  line.textContent = item.text;
  const box = $("listen-finals");
  box.append(line);
  box.scrollTop = box.scrollHeight;
}

function handleListenEvent(event) {
  if (event.type === "snapshot") {
    listen.finals.clear();
    $("listen-finals").textContent = "";
    event.finals.forEach(renderListenFinal);
    if (event.suggestion) $("listen-suggestion").textContent = event.suggestion.text;
    setListenRunning(event.running, event.device);
    return;
  }
  if (event.type === "state") {
    setListenRunning(event.running, event.device);
    return;
  }
  if (event.type === "cleared") {
    clearListenOutput();
    return;
  }
  if (event.type === "level") {
    $("listen-meter-fill").style.transform = `scaleX(${Math.min(1, event.rms * 4)})`;
    return;
  }
  if (event.type === "partial") {
    $("listen-partial").textContent = event.text;
    return;
  }
  if (event.type === "final") {
    $("listen-partial").textContent = "";
    renderListenFinal(event);
    return;
  }
  if (event.type === "suggestion_start") {
    $("listen-question").textContent = listen.finals.get(event.final_id) || "";
    $("listen-suggestion").textContent = "";
    $("listen-timing").textContent = "Organizando...";
    return;
  }
  if (event.type === "suggestion_chunk") {
    $("listen-suggestion").append(event.text);
    return;
  }
  if (event.type === "suggestion_done") {
    $("listen-timing").textContent = `1ª palavra em ${event.first_token_seconds} s · total ${event.total_seconds} s`;
    return;
  }
  if (event.type === "error") {
    setListenError(event.message);
    $("listen-timing").textContent = "";
  }
}

function connectListen() {
  closeListenSource();
  listen.source = new EventSource("/api/meeting/events");
  listen.source.onmessage = message => handleListenEvent(JSON.parse(message.data));
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1).replace(".", ",")} KB`;
}

function renderContexts() {
  const contexts = listen.workspace.contexts;
  const selected = contexts.filter(context => context.selected);
  const total = selected.reduce((sum, context) => sum + context.bytes, 0);
  $("listen-context-count").textContent = contexts.length
    ? `${selected.length} de ${contexts.length} em uso · ${formatBytes(total)}`
    : "Sem contexto";
  const list = $("listen-context-list");
  list.textContent = "";
  for (const context of contexts) {
    const row = document.createElement("li");
    row.className = "listen-context-row";
    const label = document.createElement("label");
    const check = document.createElement("input");
    check.type = "checkbox";
    check.checked = context.selected;
    check.addEventListener("change", () => toggleContext(context.name, check.checked));
    const name = document.createElement("span");
    name.className = "listen-context-name";
    name.textContent = context.name;
    const size = document.createElement("span");
    size.className = "listen-context-size";
    size.textContent = formatBytes(context.bytes);
    label.append(check, name, size);
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "listen-link";
    edit.textContent = "Editar";
    edit.setAttribute("aria-label", `Editar ${context.name}`);
    edit.addEventListener("click", () => openContext(context.name));
    row.append(label, edit);
    list.append(row);
  }
}

function renderPrompt() {
  const prompt = listen.workspace.prompt;
  $("listen-prompt-badge").textContent = prompt.is_custom ? "Personalizado" : "Padrão";
  $("listen-prompt-reset").disabled = !prompt.is_custom;
  $("listen-prompt-scope").textContent = prompt.scope_rule;
  if (!listen.promptDirty) $("listen-prompt-text").value = prompt.instructions;
}

function applyWorkspace(workspace) {
  listen.workspace = workspace;
  renderContexts();
  renderPrompt();
}

async function refreshWorkspace() {
  const response = await fetch("/api/listen/workspace");
  if (!response.ok) throw new Error("O espaço de contextos não está disponível neste servidor.");
  applyWorkspace(await response.json());
}

async function saveSelection(names) {
  try {
    applyWorkspace(await postJson("/api/listen/selection", {selected: names}));
    setListenNote();
  } catch (error) {
    setListenNote(`Seleção não salva: ${errorText(error)}`, true);
    renderContexts();
  }
}

function toggleContext(name, checked) {
  const names = listen.workspace.contexts.filter(context => context.selected).map(context => context.name);
  saveSelection(checked ? [...names, name] : names.filter(item => item !== name));
}

function showPrepView(view) {
  const showPrompt = view === "prompt";
  $("listen-show-context").setAttribute("aria-pressed", String(!showPrompt));
  $("listen-show-prompt").setAttribute("aria-pressed", String(showPrompt));
  $("listen-prompt-view").hidden = !showPrompt;
  $("listen-context-view").hidden = view !== "context";
  $("listen-editor").hidden = view !== "editor";
}

function startEditor(name, content) {
  listen.editorOpen = true;
  listen.editingName = name;
  listen.editorDirty = false;
  $("listen-editor-name").value = name || "";
  $("listen-editor-content").value = content;
  $("listen-editor-delete").hidden = name === null;
  showPrepView("editor");
  $(name === null ? "listen-editor-name" : "listen-editor-content").focus();
}

async function openContext(name) {
  try {
    const context = await postJson("/api/listen/context/read", {name});
    startEditor(context.name, context.content);
    setListenNote();
  } catch (error) {
    setListenNote(`Não abriu: ${errorText(error)}`, true);
  }
}

function closeEditor() {
  setListenNote();
  listen.editorOpen = false;
  listen.editingName = null;
  listen.editorDirty = false;
  showPrepView("context");
}

function normalizedFileName(value) {
  const name = value.trim();
  if (!name) return "";
  return /\.(md|txt)$/i.test(name) ? name : `${name}.md`;
}

async function saveEditor(event) {
  event.preventDefault();
  const name = normalizedFileName($("listen-editor-name").value);
  if (!name) {
    setListenNote("Dê um nome ao arquivo antes de salvar.", true);
    $("listen-editor-name").focus();
    return;
  }
  try {
    applyWorkspace(await postJson("/api/listen/context/save", {
      name,
      content: $("listen-editor-content").value,
      previous_name: listen.editingName
    }));
    closeEditor();
    setListenNote(`${name} salvo e em uso na próxima sugestão.`);
  } catch (error) {
    setListenNote(`Não salvou: ${errorText(error)}`, true);
  }
}

async function deleteEditing() {
  const name = listen.editingName;
  try {
    applyWorkspace(await postJson("/api/listen/context/delete", {name}));
    closeEditor();
    setListenNote(`${name} movido para input_data/.listen/trash.`);
  } catch (error) {
    setListenNote(`Não apagou: ${errorText(error)}`, true);
  }
}

async function importContextFile(file) {
  if (!file) return;
  try {
    startEditor(null, await file.text());
    $("listen-editor-name").value = file.name;
    listen.editorDirty = true;
    setListenNote("Revise e clique em Salvar para adicionar o arquivo.");
  } catch (error) {
    setListenNote(`Não importou: ${errorText(error)}`, true);
  }
}

async function savePrompt(event) {
  event.preventDefault();
  try {
    const workspace = await postJson("/api/listen/prompt/save", {instructions: $("listen-prompt-text").value});
    listen.promptDirty = false;
    applyWorkspace(workspace);
    setListenNote("Prompt salvo. Vale a partir da próxima sugestão.");
  } catch (error) {
    setListenNote(`Não salvou: ${errorText(error)}`, true);
  }
}

async function resetPrompt() {
  try {
    const workspace = await postJson("/api/listen/prompt/reset", {});
    listen.promptDirty = false;
    applyWorkspace(workspace);
    setListenNote("Prompt padrão restaurado.");
  } catch (error) {
    setListenNote(`Não restaurou: ${errorText(error)}`, true);
  }
}

async function refreshListenContext() {
  await refreshWorkspace();
}

async function updateListenBackstage() {
  const response = await fetch("/api/meeting/backstage").catch(() => null);
  if (!response || !response.ok || mode !== "listen") return;
  const info = await response.json();
  $("backstage-system-prompt").textContent = info.system_prompt_template;
  $("system-prompt-len").textContent = "Tamanho: " + info.system_prompt_template.length + " caracteres";
  $("backstage-context-note").textContent = "Só os contextos marcados entram no prompt do Listen.";
  $("backstage-context-files").textContent = "Arquivos em uso: " + (info.context_files.map(file => `${file.name} (${file.bytes} bytes)`).join(", ") || "nenhum");
  $("backstage-model-info").textContent = `Provedor: ${info.provider} · Modelo: ${info.model} · Whisper: ${info.whisper_model} · Idioma: ${info.language || "detecção automática"}`;
  const hasRequest = Boolean(info.last_request);
  $("backstage-request-label").textContent = hasRequest ? "Último pedido enviado" : "Nenhum pedido enviado nesta sessão";
  $("backstage-request").textContent = hasRequest ? info.last_request.prompt : "Nenhum pedido enviado nesta sessão";
}

$("listen-toggle").addEventListener("click", async () => {
  setListenError("");
  $("listen-toggle").disabled = true;
  // Em silêncio, a captura do Windows leva até 2 s para soltar o dispositivo.
  $("listen-toggle").textContent = listen.running ? "Parando..." : "Iniciando...";
  try {
    if (listen.running) {
      await postJson("/api/meeting/stop", {});
      setListenRunning(false);
      return;
    }
    const started = await postJson("/api/meeting/start", {});
    setListenRunning(true, started.device);
    connectListen();
  } catch (error) {
    setListenError(errorText(error));
    $("listen-toggle").textContent = listen.running ? "Parar" : "Começar a ouvir";
  } finally {
    $("listen-toggle").disabled = false;
  }
});

$("listen-generate").addEventListener("click", () => {
  setListenError("");
  postJson("/api/meeting/generate", {}).catch(error => setListenError(errorText(error)));
});

$("listen-clear").addEventListener("click", async () => {
  setListenError("");
  try {
    await postJson("/api/meeting/clear", {});
    clearListenOutput();
    setListenNote("Conversa limpa.");
  } catch (error) {
    setListenError(errorText(error));
  }
});

$("listen-show-context").addEventListener("click", () => showPrepView(listen.editorOpen ? "editor" : "context"));
$("listen-show-prompt").addEventListener("click", () => showPrepView("prompt"));
$("listen-select-all").addEventListener("click", () => saveSelection(listen.workspace.contexts.map(context => context.name)));
$("listen-select-none").addEventListener("click", () => saveSelection([]));
$("listen-context-new").addEventListener("click", () => startEditor(null, ""));
$("listen-context-file").addEventListener("change", event => {
  importContextFile(event.target.files[0]);
  event.target.value = "";
});
$("listen-context-import").addEventListener("keydown", event => {
  if (event.key !== "Enter" && event.key !== " ") return;
  event.preventDefault();
  $("listen-context-file").click();
});
$("listen-editor").addEventListener("submit", saveEditor);
$("listen-editor-name").addEventListener("input", () => { listen.editorDirty = true; });
$("listen-editor-content").addEventListener("input", () => { listen.editorDirty = true; });
$("listen-editor-back").addEventListener("click", event => {
  if (!listen.editorDirty) {
    closeEditor();
    return;
  }
  armOrRun(event.currentTarget.querySelector("span"), "Clique de novo para descartar", closeEditor);
});
$("listen-editor-delete").addEventListener("click", event => armOrRun(event.currentTarget, "Confirmar exclusão", deleteEditing));
$("listen-prompt-view").addEventListener("submit", savePrompt);
$("listen-prompt-text").addEventListener("input", () => { listen.promptDirty = true; });
$("listen-prompt-reset").addEventListener("click", event => armOrRun(event.currentTarget, "Confirmar restauração", resetPrompt));

fetch("/api/meeting/state").then(async response => {
  if (!response.ok) {
    $("listen-toggle").disabled = true;
    setListenError("O serviço de reunião não está configurado neste servidor.");
    return;
  }
  const state = await response.json();
  setListenRunning(state.running, state.device);
  if (state.running) connectListen();
  await refreshWorkspace();
}).catch(error => setListenError(errorText(error)));
