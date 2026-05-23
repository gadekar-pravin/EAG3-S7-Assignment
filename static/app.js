const statusEl = document.querySelector("#status");
const samplesEl = document.querySelector("#samples");
const queryEl = document.querySelector("#query");
const indexedState = document.querySelector("#indexedState");
const plainState = document.querySelector("#plainState");
const indexedAnswer = document.querySelector("#indexedAnswer");
const plainAnswer = document.querySelector("#plainAnswer");
const sourceCount = document.querySelector("#sourceCount");
const sourcesEl = document.querySelector("#sources");
const chunksEl = document.querySelector("#chunks");
const buttons = [...document.querySelectorAll("button")];

function setBusy(isBusy) {
  buttons.forEach((button) => {
    button.disabled = isBusy;
  });
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function api(path, payload) {
  const response = await fetch(path, {
    method: payload ? "POST" : "GET",
    headers: payload ? { "Content-Type": "application/json" } : {},
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || response.statusText);
  }
  return data;
}

function renderEvidence(result) {
  const sources = result.sources || [];
  const chunks = result.chunks || [];
  sourceCount.textContent = `${sources.length} cited`;
  sourcesEl.innerHTML = sources
    .map(
      (source) => `
        <article class="source">
          <strong>${escapeHtml(source.case)}</strong>
          <span>${escapeHtml(source.court)} | ${escapeHtml(source.date_filed)}</span>
          <span>${escapeHtml(source.source_path)}</span>
        </article>
      `,
    )
    .join("");
  chunksEl.innerHTML = chunks
    .map(
      (chunk) => `
        <article class="chunk">
          <span>${escapeHtml(chunk.case)} | score ${Number(chunk.score).toFixed(3)}</span>
          <p>${escapeHtml(chunk.preview)}</p>
        </article>
      `,
    )
    .join("");
}

function renderSamples(samples) {
  samplesEl.innerHTML = samples
    .map(
      (sample) => `
        <button class="sample" type="button" data-query="${escapeHtml(sample.query)}">
          <strong>${sample.semantic_recall ? "Semantic" : "Direct"}</strong>
          ${escapeHtml(sample.query)}
        </button>
      `,
    )
    .join("");
  samplesEl.querySelectorAll(".sample").forEach((button) => {
    button.addEventListener("click", () => {
      queryEl.value = button.dataset.query || "";
      queryEl.focus();
    });
  });
}

async function refreshStatus() {
  const data = await api("/api/status");
  const state = data.indexed ? "ready" : "not built";
  statusEl.textContent = `${data.document_count} opinions | ${data.chunk_count} chunks | ${state}`;
  renderSamples(data.sample_queries || []);
  if (!queryEl.value && data.sample_queries?.length) {
    queryEl.value = data.sample_queries[0].query;
  }
}

async function buildIndex() {
  setBusy(true);
  statusEl.textContent = "Building index...";
  try {
    const data = await api("/api/index", {});
    statusEl.textContent = `${data.index.document_count} opinions | ${data.index.chunk_count} chunks | ready`;
  } catch (error) {
    statusEl.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function ask(useIndex) {
  const targetState = useIndex ? indexedState : plainState;
  const targetAnswer = useIndex ? indexedAnswer : plainAnswer;
  targetState.textContent = "Running";
  targetAnswer.textContent = "";
  const result = await api("/api/query", {
    query: queryEl.value,
    use_index: useIndex,
    top_k: 5,
  });
  targetState.textContent = result.status;
  targetAnswer.textContent = result.answer;
  if (useIndex) {
    renderEvidence(result);
  }
}

async function runSingle(useIndex) {
  setBusy(true);
  try {
    await ask(useIndex);
  } catch (error) {
    const targetState = useIndex ? indexedState : plainState;
    const targetAnswer = useIndex ? indexedAnswer : plainAnswer;
    targetState.textContent = "Error";
    targetAnswer.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function compare() {
  setBusy(true);
  try {
    await ask(true);
    await ask(false);
  } catch (error) {
    indexedState.textContent = "Error";
    indexedAnswer.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

document.querySelector("#buildIndex").addEventListener("click", buildIndex);
document.querySelector("#askWithIndex").addEventListener("click", () => runSingle(true));
document.querySelector("#askWithoutIndex").addEventListener("click", () => runSingle(false));
document.querySelector("#compare").addEventListener("click", compare);

refreshStatus().catch((error) => {
  statusEl.textContent = error.message;
});
