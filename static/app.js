const jobsList = document.getElementById("jobs-list");
const form = document.getElementById("generate-form");
const promptInput = document.getElementById("prompt");
const articleCheckbox = document.getElementById("article-mode");
const submitBtn = document.getElementById("submit-btn");
const formError = document.getElementById("form-error");

const STAGE_LABELS = {
  queued: "В очереди",
  writing_text: "Пишу текст (GigaChat)",
  generating_image: "Генерирую изображение (OpenAI)",
  done: "Готово",
  error: "Ошибка",
};

const TERMINAL_STATUSES = new Set(["done", "error"]);
const activePolls = new Set();
let pollTimer = null;

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

function modeLabel(mode) {
  return mode === "article" ? "Статья + инфографика" : "Только изображение";
}

function formatDate(value) {
  if (!value) return "";
  return value.replace("T", " ");
}

function renderJobCard(job) {
  const isTerminal = TERMINAL_STATUSES.has(job.status);
  const progress = Math.max(0, Math.min(100, job.progress || 0));
  const stageLabel = STAGE_LABELS[job.stage] || job.stage || "";

  let statusHtml = "";
  if (!isTerminal) {
    statusHtml = `
      <div class="progress-wrap">
        <div class="progress-bar"><div class="progress-fill" style="width:${progress}%"></div></div>
        <div class="progress-label">${escapeHtml(stageLabel)} — ${progress}%</div>
      </div>`;
  } else if (job.status === "error") {
    statusHtml = `<p class="error-text">❌ ${escapeHtml(job.error || "Неизвестная ошибка")}</p>`;
  }

  const textHtml = job.text
    ? `<div class="job-text"><h4>Текст</h4><pre>${escapeHtml(job.text)}</pre></div>`
    : "";

  const imagesHtml =
    job.image_files && job.image_files.length
      ? `<div class="job-images">${job.image_files
          .map(
            (name) =>
              `<img src="/media/${encodeURIComponent(name)}" alt="Результат генерации" loading="lazy">`
          )
          .join("")}</div>`
      : "";

  const card = document.createElement("div");
  card.className = `job-card status-${job.status}`;
  card.id = `job-${job.id}`;
  card.innerHTML = `
    <div class="job-header">
      <span class="badge badge-${job.mode}">${modeLabel(job.mode)}</span>
      <span class="job-date">${escapeHtml(formatDate(job.created_at))}</span>
      <button type="button" class="delete-btn" title="Удалить результат" data-id="${job.id}">✕</button>
    </div>
    <p class="job-prompt">${escapeHtml(job.prompt)}</p>
    ${statusHtml}
    ${textHtml}
    ${imagesHtml}
  `;
  return card;
}

function showEmptyStateIfNeeded() {
  if (!jobsList.children.length) {
    jobsList.innerHTML =
      '<p class="empty-state" id="empty-state">Пока нет результатов — отправьте первый запрос выше.</p>';
  }
}

function upsertJobCard(job, { prepend = false } = {}) {
  const emptyState = document.getElementById("empty-state");
  if (emptyState) emptyState.remove();

  const existing = document.getElementById(`job-${job.id}`);
  const newCard = renderJobCard(job);
  if (existing) {
    existing.replaceWith(newCard);
  } else if (prepend) {
    jobsList.prepend(newCard);
  } else {
    jobsList.appendChild(newCard);
  }

  if (TERMINAL_STATUSES.has(job.status)) {
    activePolls.delete(job.id);
  } else {
    activePolls.add(job.id);
    ensurePolling();
  }
}

async function pollJob(id) {
  try {
    const res = await fetch(`/api/jobs/${id}`);
    if (!res.ok) {
      activePolls.delete(id);
      return;
    }
    const job = await res.json();
    upsertJobCard(job);
  } catch (err) {
    // сетевой сбой — попробуем ещё раз на следующем тике
  }
}

function ensurePolling() {
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    if (!activePolls.size) {
      clearInterval(pollTimer);
      pollTimer = null;
      return;
    }
    activePolls.forEach((id) => pollJob(id));
  }, 1000);
}

async function loadJobs() {
  try {
    const res = await fetch("/api/jobs");
    const jobs = await res.json();
    jobsList.innerHTML = "";
    jobs.forEach((job) => {
      jobsList.appendChild(renderJobCard(job));
      if (!TERMINAL_STATUSES.has(job.status)) {
        activePolls.add(job.id);
      }
    });
    showEmptyStateIfNeeded();
    if (activePolls.size) ensurePolling();
  } catch (err) {
    jobsList.innerHTML = '<p class="error-text">Не удалось загрузить историю результатов.</p>';
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.textContent = "";
  const prompt = promptInput.value.trim();
  if (!prompt) return;

  submitBtn.disabled = true;
  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, article: articleCheckbox.checked }),
    });
    const data = await res.json();
    if (!res.ok) {
      formError.textContent = data.error || "Не удалось создать задачу.";
      return;
    }
    upsertJobCard(data, { prepend: true });
    promptInput.value = "";
  } catch (err) {
    formError.textContent = "Ошибка сети. Проверьте, что сервер запущен.";
  } finally {
    submitBtn.disabled = false;
  }
});

jobsList.addEventListener("click", async (event) => {
  const btn = event.target.closest(".delete-btn");
  if (!btn) return;

  const id = btn.dataset.id;
  if (!window.confirm("Удалить этот результат вместе с сохранёнными файлами?")) return;

  btn.disabled = true;
  try {
    const res = await fetch(`/api/jobs/${id}`, { method: "DELETE" });
    if (res.ok || res.status === 404) {
      document.getElementById(`job-${id}`)?.remove();
      activePolls.delete(id);
      showEmptyStateIfNeeded();
    }
  } finally {
    btn.disabled = false;
  }
});

loadJobs();
