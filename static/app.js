const API_BASE = "";

const $ = (id) => document.getElementById(id);

const statusLabels = {
  queued: "排队中",
  running: "翻译中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const modeLabels = {
  sci: "专业模式",
  precise: "精确模式",
  fast: "快速模式",
};

const targetLangLabels = {
  zh: "简体中文",
  en: "English",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function updateSettingsSummary() {
  const lang = targetLangLabels[$("targetLang").value] || $("targetLang").value;
  const mode = modeLabels[$("mode").value] || $("mode").value;
  const summary = $("settingsSummary");
  if (summary) summary.textContent = `${lang} / ${mode}`;
}

// ===== Config =====
function loadConfig() {
  const cfg = JSON.parse(localStorage.getItem("retainpdf_config") || "{}");
  $("apiKey").value = cfg.apiKey || "";
  $("ocrApiKey").value = cfg.ocrApiKey || "";
  $("model").value = cfg.model || "deepseek-v4-flash";
  $("baseUrl").value = cfg.baseUrl || "https://api.deepseek.com/v1";
  $("ocrProvider").value = cfg.ocrProvider || "mineru";
  $("targetLang").value = cfg.targetLang || "zh";
  $("mode").value = cfg.mode || "sci";
  $("renderMode").value = cfg.renderMode || "typst";
  $("ocrEnabled").checked = cfg.ocrEnabled !== false;
  $("outputFormat").value = cfg.outputFormat || "pdf";
  updateSettingsSummary();
}

function saveConfig() {
  const cfg = {
    apiKey: $("apiKey").value,
    ocrApiKey: $("ocrApiKey").value,
    model: $("model").value,
    baseUrl: $("baseUrl").value,
    ocrProvider: $("ocrProvider").value,
    targetLang: $("targetLang").value,
    mode: $("mode").value,
    renderMode: $("renderMode").value,
    ocrEnabled: $("ocrEnabled").checked,
    outputFormat: $("outputFormat").value,
  };
  localStorage.setItem("retainpdf_config", JSON.stringify(cfg));
  updateSettingsSummary();

  const btn = $("saveConfig");
  const original = btn.innerHTML;
  btn.innerHTML = `
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"></path></svg>
    已保存
  `;
  btn.classList.add("saved");
  setTimeout(() => {
    btn.innerHTML = original;
    btn.classList.remove("saved");
  }, 1500);
}

// ===== Upload =====
const uploadZone = $("uploadZone");
const fileInput = $("fileInput");
const startTranslate = $("startTranslate");

function openFilePicker(event) {
  event?.stopPropagation();
  fileInput.click();
}

uploadZone.addEventListener("click", () => fileInput.click());
uploadZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});
startTranslate.addEventListener("click", openFilePicker);

uploadZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  uploadZone.classList.add("dragover");
});
uploadZone.addEventListener("dragleave", () => uploadZone.classList.remove("dragover"));
uploadZone.addEventListener("drop", (event) => {
  event.preventDefault();
  uploadZone.classList.remove("dragover");
  const [file] = event.dataTransfer.files;
  if (file) handleUpload(file);
});
fileInput.addEventListener("change", () => {
  const [file] = fileInput.files;
  if (file) handleUpload(file);
});

async function handleUpload(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showUploadStatus("请选择 PDF 文件。", "error");
    return;
  }

  const apiKey = $("apiKey").value.trim();
  if (!apiKey) {
    showUploadStatus("请先填写翻译 API Key，再上传 PDF。", "error");
    $("apiKey").focus();
    return;
  }

  showUploadStatus(`正在上传 ${file.name} ...`, "info");

  const form = new FormData();
  form.append("file", file);
  form.append("target_lang", $("targetLang").value);
  form.append("ocr_enabled", $("ocrEnabled").checked ? "true" : "false");
  form.append("output_format", $("outputFormat").value);

  const config = {
    translation: {
      model: $("model").value,
      base_url: $("baseUrl").value,
      api_key: apiKey,
      mode: $("mode").value,
    },
    ocr: {
      provider: $("ocrProvider").value,
      api_key: $("ocrApiKey").value,
    },
    render: {
      mode: $("renderMode").value,
    },
  };
  form.append("config", JSON.stringify(config));

  try {
    const resp = await fetch(`${API_BASE}/api/v1/jobs`, { method: "POST", body: form });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error?.message || err.detail?.error?.message || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    showUploadStatus(`任务已创建：${data.job_id}`, "success");
    fileInput.value = "";
    loadJobs();
  } catch (error) {
    showUploadStatus(`上传失败：${error.message}`, "error");
  }
}

function showUploadStatus(message, type) {
  const el = $("uploadStatus");
  el.textContent = message;
  el.className = `upload-status ${type === "success" ? "upload-success" : type === "error" ? "upload-error" : "upload-info"}`;
}

// ===== Jobs =====
let pollTimer = null;

async function loadJobs() {
  try {
    const resp = await fetch(`${API_BASE}/api/v1/jobs?limit=50`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    renderJobs(data.jobs || []);
  } catch (error) {
    $("jobsList").innerHTML = `<p class="empty">加载失败：${escapeHtml(error.message)}</p>`;
    const summary = $("jobsSummary");
    if (summary) summary.textContent = "加载失败";
  }
}

function renderJobs(jobs) {
  const container = $("jobsList");
  const summary = $("jobsSummary");
  if (summary) {
    summary.textContent = jobs.length ? `${jobs.length} 个任务` : "等待任务";
  }

  if (!jobs.length) {
    container.innerHTML = `<p class="empty">暂无任务</p>`;
    return;
  }

  container.innerHTML = jobs.map((job) => {
    const status = escapeHtml(job.status || "queued");
    const statusClass = `status-${status}`;
    const statusText = escapeHtml(statusLabels[job.status] || job.status || "未知");
    const canDownload = job.status === "succeeded";
    const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
    const stageText = job.stage ? `阶段：${escapeHtml(job.stage)}` : "等待执行";
    const errorText = job.error ? (job.error.message || JSON.stringify(job.error)) : "";
    const outputFormat = escapeHtml(job.output_format || "pdf");
    const jobId = escapeHtml(job.job_id);
    const shortId = escapeHtml(String(job.job_id || "").slice(0, 8));

    return `
      <article class="job-item" data-id="${jobId}">
        <div class="job-info">
          <div class="job-title-row">
            <span class="job-id">${shortId || "unknown"}...</span>
            <span class="job-status ${statusClass}">${statusText}</span>
          </div>
          <div class="job-progress" aria-label="任务进度 ${progress}%">
            <div class="job-progress-bar" style="width:${progress}%"></div>
          </div>
          <div class="job-stage">${stageText} · ${progress}%</div>
          ${errorText ? `<div class="job-error">${escapeHtml(errorText)}</div>` : ""}
        </div>
        <div class="job-actions">
          <button class="download" ${!canDownload ? "disabled" : ""} data-action="download" data-job-id="${jobId}" data-format="${outputFormat}">下载</button>
          <button class="delete" data-action="delete" data-job-id="${jobId}">删除</button>
        </div>
      </article>
    `;
  }).join("");
}

async function downloadJob(jobId, format) {
  const fmt = format === "all" ? "zip" : format;
  window.open(`${API_BASE}/api/v1/jobs/${encodeURIComponent(jobId)}/download?format=${encodeURIComponent(fmt)}`, "_blank");
}

async function deleteJob(jobId) {
  if (!confirm(`确定删除任务 ${jobId.slice(0, 8)}...?`)) return;
  try {
    const resp = await fetch(`${API_BASE}/api/v1/jobs/${encodeURIComponent(jobId)}`, { method: "DELETE" });
    if (resp.ok) {
      loadJobs();
    } else {
      alert("删除失败");
    }
  } catch (error) {
    alert(`删除失败：${error.message}`);
  }
}

$("jobsList").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const jobId = button.dataset.jobId;
  if (button.dataset.action === "download") {
    downloadJob(jobId, button.dataset.format || "pdf");
  }
  if (button.dataset.action === "delete") {
    deleteJob(jobId);
  }
});

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(loadJobs, 3000);
}

// ===== Service Status =====
async function checkService() {
  const el = $("serviceStatus");
  try {
    const resp = await fetch(`${API_BASE}/health`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    el.className = "status-pill status-ok";
    el.innerHTML = `<i></i>服务正常 · ${escapeHtml(data.version)}`;
  } catch (error) {
    el.className = "status-pill status-error";
    el.innerHTML = `<i></i>服务不可用`;
  }
}

// ===== UI polish =====
function setupThemeToggle() {
  const saved = localStorage.getItem("yoru_scene_light");
  if (saved === "true") document.body.classList.add("light-scene");
  $("themeToggle").addEventListener("click", () => {
    document.body.classList.toggle("light-scene");
    localStorage.setItem("yoru_scene_light", document.body.classList.contains("light-scene"));
  });
}

function setupNavState() {
  document.querySelectorAll(".nav-links a").forEach((link) => {
    link.addEventListener("click", () => {
      document.querySelectorAll(".nav-links a").forEach((item) => item.classList.remove("active"));
      link.classList.add("active");
    });
  });
}

["targetLang", "mode"].forEach((id) => {
  $(id).addEventListener("change", updateSettingsSummary);
});

// ===== Init =====
$("saveConfig").addEventListener("click", saveConfig);
$("refreshJobs").addEventListener("click", loadJobs);

setupThemeToggle();
setupNavState();
loadConfig();
checkService();
loadJobs();
startPolling();
