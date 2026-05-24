/* ── DOM References ────────────────────────────────── */
const statusText = document.querySelector("#statusText");
const statusDot = document.querySelector("#statusDot");
const samplesEl = document.querySelector("#samples");
const queryEl = document.querySelector("#query");
const queryCount = document.querySelector("#queryCount");
const indexedBadge = document.querySelector("#indexedBadge");
const plainBadge = document.querySelector("#plainBadge");
const indexedAnswer = document.querySelector("#indexedAnswer");
const plainAnswer = document.querySelector("#plainAnswer");
const indexedFooter = document.querySelector("#indexedFooter");
const plainFooter = document.querySelector("#plainFooter");
const indexedCard = document.querySelector("#indexedCard");
const plainCard = document.querySelector("#plainCard");
const sourceCount = document.querySelector("#sourceCount");
const sourcesEl = document.querySelector("#sources");
const chunksEl = document.querySelector("#chunks");
const chunksHeading = document.querySelector("#chunksHeading");
const evidenceSection = document.querySelector("#evidenceSection");
const toastContainer = document.querySelector("#toasts");
const buttons = [...document.querySelectorAll(".btn")];

/* ── Utilities ────────────────────────────────────── */

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function setBusy(isBusy) {
  buttons.forEach((b) => (b.disabled = isBusy));
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

/* ── Toast Notifications ──────────────────────────── */

function showToast(message, isError = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isError ? " error" : "");
  el.textContent = message;
  toastContainer.appendChild(el);
  setTimeout(() => {
    el.classList.add("leaving");
    el.addEventListener("animationend", () => el.remove());
  }, 3200);
}

/* ── Skeleton Loading ─────────────────────────────── */

function showSkeleton(container) {
  /* Build skeleton DOM nodes instead of innerHTML for safety */
  container.textContent = "";
  container.classList.remove("has-content");
  for (let i = 0; i < 4; i++) {
    const line = document.createElement("div");
    line.className = "skeleton-line";
    container.appendChild(line);
  }
}

/* ── Formatting Helpers ───────────────────────────── */

function formatAnswer(text) {
  /*
   * All user/API content is escaped first via escapeHtml. Then we inject
   * only controlled markup: cite-chip spans wrapping digit-only matches
   * from the narrow regex \[(\d+)\]. No user content enters unescaped.
   */
  const escaped = escapeHtml(text);
  return escaped.replace(
    /\[(\d+)\]/g,
    '<span class="cite-chip">[$1]</span>'
  );
}

function scoreColor(score) {
  if (score >= 0.7) return "var(--green)";
  if (score >= 0.4) return "var(--gold)";
  return "var(--wine)";
}

function formatLatency(ms) {
  if (ms >= 1000) return (ms / 1000).toFixed(2) + "s";
  return Math.round(ms) + "ms";
}

function renderAnswerFooter(el, latencyMs, srcCount) {
  el.style.display = "flex";
  el.textContent = "";
  const latSpan = document.createElement("span");
  const latLabel = document.createElement("strong");
  latLabel.textContent = "Latency";
  const latVal = document.createElement("span");
  latVal.className = "stat-value";
  latVal.textContent = " " + formatLatency(latencyMs);
  latSpan.appendChild(latLabel);
  latSpan.appendChild(latVal);

  const srcSpan = document.createElement("span");
  const srcLabel = document.createElement("strong");
  srcLabel.textContent = "Sources";
  const srcVal = document.createElement("span");
  srcVal.className = "stat-value";
  srcVal.textContent = " " + srcCount;
  srcSpan.appendChild(srcLabel);
  srcSpan.appendChild(srcVal);

  el.appendChild(latSpan);
  el.appendChild(srcSpan);
}

/* ── Badge Helpers ────────────────────────────────── */

function setBadge(badgeEl, type, text) {
  badgeEl.className = "answer-badge answer-badge--" + type;
  badgeEl.textContent = text;
}

/* ── Render Samples ───────────────────────────────── */

function renderSamples(samples) {
  queryCount.textContent = samples.length;
  samplesEl.textContent = "";
  samples.forEach((sample, i) => {
    const btn = document.createElement("button");
    btn.className = "sample";
    btn.type = "button";
    btn.dataset.query = sample.query;

    const badges = document.createElement("div");
    badges.className = "sample-badges";

    const typeBadge = document.createElement("span");
    typeBadge.className = "sample-type " + (sample.semantic_recall ? "semantic" : "direct");
    typeBadge.textContent = sample.semantic_recall ? "Semantic" : "Direct";
    badges.appendChild(typeBadge);

    const idBadge = document.createElement("span");
    idBadge.className = "sample-id";
    idBadge.textContent = "#" + (i + 1);
    badges.appendChild(idBadge);

    btn.appendChild(badges);
    btn.appendChild(document.createTextNode(sample.query));

    btn.addEventListener("click", () => {
      samplesEl.querySelectorAll(".sample").forEach((s) => s.classList.remove("active"));
      btn.classList.add("active");
      queryEl.value = btn.dataset.query || "";
      queryEl.focus();
    });

    samplesEl.appendChild(btn);
  });
}

/* ── Render Evidence ──────────────────────────────── */

function renderEvidence(result) {
  const sources = result.sources || [];
  const chunks = result.chunks || [];

  sourceCount.textContent = sources.length;

  sourcesEl.textContent = "";
  if (sources.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.innerHTML = '<div class="empty-state-icon">&sect;</div>'
      + '<div class="empty-state-text">No sources cited</div>';
    sourcesEl.appendChild(empty);
  } else {
    sources.forEach((source) => {
      const score = Number(source.score || 0);
      const pct = Math.min(Math.round(score * 100), 100);

      const article = document.createElement("article");
      article.className = "source";

      const caseName = document.createElement("span");
      caseName.className = "source-case";
      caseName.textContent = source.case || "";
      article.appendChild(caseName);

      const detail = document.createElement("span");
      detail.className = "source-detail";
      detail.textContent = (source.court || "") + " \u00b7 " + (source.date_filed || "");
      article.appendChild(detail);

      const barWrap = document.createElement("div");
      barWrap.className = "score-bar-wrap";

      const bar = document.createElement("div");
      bar.className = "score-bar";
      const fill = document.createElement("div");
      fill.className = "score-bar-fill";
      fill.style.width = pct + "%";
      fill.style.background = scoreColor(score);
      bar.appendChild(fill);
      barWrap.appendChild(bar);

      const val = document.createElement("span");
      val.className = "score-value";
      val.style.color = scoreColor(score);
      val.textContent = score.toFixed(3);
      barWrap.appendChild(val);

      article.appendChild(barWrap);
      sourcesEl.appendChild(article);
    });
  }

  chunksEl.textContent = "";
  if (chunks.length === 0) {
    chunksHeading.classList.remove("visible");
  } else {
    chunksHeading.classList.add("visible");
    chunks.forEach((chunk) => {
      const score = Number(chunk.score || 0);

      const article = document.createElement("article");
      article.className = "chunk";

      const header = document.createElement("div");
      header.className = "chunk-header";

      const caseSpan = document.createElement("span");
      caseSpan.className = "chunk-case";
      caseSpan.textContent = chunk.case || "";
      header.appendChild(caseSpan);

      const scoreSpan = document.createElement("span");
      scoreSpan.className = "chunk-score";
      scoreSpan.style.background = scoreColor(score) + "20";
      scoreSpan.style.color = scoreColor(score);
      scoreSpan.textContent = score.toFixed(3);
      header.appendChild(scoreSpan);

      article.appendChild(header);

      const p = document.createElement("p");
      p.textContent = chunk.preview || "";
      article.appendChild(p);

      chunksEl.appendChild(article);
    });
  }
}

/* ── Status ───────────────────────────────────────── */

async function refreshStatus() {
  try {
    const data = await api("/api/status");
    const indexed = data.indexed;
    statusText.textContent = data.document_count + " opinions \u00b7 "
      + data.chunk_count + " chunks \u00b7 "
      + (indexed ? "ready" : "not built");
    statusDot.classList.toggle("ready", indexed);
    renderSamples(data.sample_queries || []);

    if (!queryEl.value && data.sample_queries?.length) {
      queryEl.value = data.sample_queries[0].query;
      const first = samplesEl.querySelector(".sample");
      if (first) first.classList.add("active");
    }
  } catch (error) {
    statusText.textContent = "Offline";
    showToast(error.message, true);
  }
}

/* ── Build Index ──────────────────────────────────── */

async function buildIndex() {
  setBusy(true);
  statusText.textContent = "Building index\u2026";
  statusDot.classList.remove("ready");
  const t0 = performance.now();
  try {
    const data = await api("/api/index", {});
    const elapsed = performance.now() - t0;
    statusText.textContent = data.index.document_count + " opinions \u00b7 "
      + data.index.chunk_count + " chunks \u00b7 ready";
    statusDot.classList.add("ready");
    showToast("Index built in " + formatLatency(elapsed));
  } catch (error) {
    statusText.textContent = error.message;
    showToast(error.message, true);
  } finally {
    setBusy(false);
  }
}

/* ── Ask ──────────────────────────────────────────── */

async function ask(useIndex) {
  const badge = useIndex ? indexedBadge : plainBadge;
  const answerEl = useIndex ? indexedAnswer : plainAnswer;
  const footer = useIndex ? indexedFooter : plainFooter;

  setBadge(badge, "running", "Running\u2026");
  showSkeleton(answerEl);
  footer.style.display = "none";

  const t0 = performance.now();
  const result = await api("/api/query", {
    query: queryEl.value,
    use_index: useIndex,
    top_k: 5,
  });
  const elapsed = performance.now() - t0;

  const badgeType = useIndex ? "indexed" : "plain";
  setBadge(badge, badgeType, result.status || "Done");

  /*
   * formatAnswer escapes all content first, then injects controlled
   * cite-chip spans for [N] patterns. Only digit-only regex matches
   * produce markup; all other content remains escaped.
   */
  answerEl.innerHTML = formatAnswer(result.answer);
  if (result.answer && result.answer.length > 20) {
    answerEl.classList.add("has-content");
  } else {
    answerEl.classList.remove("has-content");
  }

  const srcCount = useIndex ? (result.sources || []).length : 0;
  renderAnswerFooter(footer, elapsed, srcCount);

  if (useIndex) {
    renderEvidence(result);
  }
}

/* ── Run Single ───────────────────────────────────── */

async function runSingle(useIndex) {
  setBusy(true);
  try {
    await ask(useIndex);
  } catch (error) {
    const badge = useIndex ? indexedBadge : plainBadge;
    const answerEl = useIndex ? indexedAnswer : plainAnswer;
    const footer = useIndex ? indexedFooter : plainFooter;
    setBadge(badge, useIndex ? "indexed" : "plain", "Error");
    answerEl.classList.remove("has-content");
    answerEl.textContent = error.message;
    footer.style.display = "none";
    showToast(error.message, true);
  } finally {
    setBusy(false);
  }
}

/* ── Compare ──────────────────────────────────────── */

async function compare() {
  setBusy(true);
  try {
    await Promise.all([
      ask(true).catch((err) => {
        setBadge(indexedBadge, "indexed", "Error");
        indexedAnswer.classList.remove("has-content");
        indexedAnswer.textContent = err.message;
        indexedFooter.style.display = "none";
        showToast("Indexed: " + err.message, true);
      }),
      ask(false).catch((err) => {
        setBadge(plainBadge, "plain", "Error");
        plainAnswer.classList.remove("has-content");
        plainAnswer.textContent = err.message;
        plainFooter.style.display = "none";
        showToast("Plain: " + err.message, true);
      }),
    ]);
  } finally {
    setBusy(false);
  }
}

/* ── Keyboard Shortcut ────────────────────────────── */

queryEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    runSingle(true);
  }
});

/* ── Event Listeners ──────────────────────────────── */

document.querySelector("#buildIndex").addEventListener("click", buildIndex);
document.querySelector("#askWithIndex").addEventListener("click", () => runSingle(true));
document.querySelector("#askWithoutIndex").addEventListener("click", () => runSingle(false));
document.querySelector("#compare").addEventListener("click", compare);

/* ── Init ─────────────────────────────────────────── */

refreshStatus();
