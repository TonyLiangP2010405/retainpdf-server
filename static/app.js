const API_BASE = "";

const $ = (id) => document.getElementById(id);

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
  const btn = $("saveConfig");
  const orig = btn.textContent;
  btn.textContent = "✅ 已保存";
  btn.style.background = "#d4edda";
  btn.style.color = "#155724";
  setTimeout(() => {
    btn.textContent = orig;
    btn.style.background = "";
    btn.style.color = "";
  }, 1500);
}

// ===== Upload =====
const uploadZone = $("uploadZone");
const fileInput = $("fileInput");

uploadZone.addEventListener("click", () => fileInput.click());
uploadZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  uploadZone.classList.add("dragover");
});
uploadZone.addEventListener("dragleave", () => uploadZone.classList.remove("dragover"));
uploadZone.addEventListener("drop", (e) => {
  e.preventDefault();
  uploadZone.classList.remove("dragover");
  const files = e.dataTransfer.files;
  if (files.length) handleUpload(files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) handleUpload(fileInput.files[0]);
});

async function handleUpload(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showUploadStatus("请选择 PDF 文件", "error");
    return;
  }
  const apiKey = $("apiKey").value.trim();
  if (!apiKey) {
    showUploadStatus("请先填写翻译 API Key", "error");
    return;
  }

  showUploadStatus(`正在上传 ${file.name} ...`, "info");

  const form = new FormData();
  form.append("file", file);
  form.append("target_lang", $("targetLang").value);
  form.append("ocr_enabled", $("ocrEnabled").checked ? "true" : "false");
  form.append("output_format", $("outputFormat").value);

  // Pass config as JSON string
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
      throw new Error(err.error?.message || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    showUploadStatus(`任务已创建: ${data.job_id}`, "success");
    fileInput.value = "";
    loadJobs();
  } catch (e) {
    showUploadStatus(`上传失败: ${e.message}`, "error");
  }
}

function showUploadStatus(msg, type) {
  const el = $("uploadStatus");
  el.textContent = msg;
  el.className = type === "success" ? "upload-success" : type === "error" ? "upload-error" : "upload-info";
}

// ===== Jobs =====
let pollTimer = null;

async function loadJobs() {
  try {
    const resp = await fetch(`${API_BASE}/api/v1/jobs?limit=50`);
    const data = await resp.json();
    renderJobs(data.jobs || []);
  } catch (e) {
    $("jobsList").innerHTML = `<p class="empty">加载失败: ${e.message}</p>`;
  }
}

function renderJobs(jobs) {
  const container = $("jobsList");
  if (!jobs.length) {
    container.innerHTML = `<p class="empty">暂无任务</p>`;
    return;
  }

  container.innerHTML = jobs.map((job) => {
    const statusClass = `status-${job.status}`;
    const canDownload = job.status === "succeeded";
    const stageText = job.stage ? `阶段: ${job.stage}` : "";
    return `
      <div class="job-item" data-id="${job.job_id}">
        <div class="job-info">
          <div>
            <span class="job-id">${job.job_id.slice(0, 8)}...</span>
            <span class="job-status ${statusClass}">${job.status}</span>
          </div>
          <div class="job-progress">
            <div class="job-progress-bar" style="width:${job.progress || 0}%"></div>
          </div>
          <div class="job-stage">${stageText} ${job.progress || 0}%</div>
          ${job.error ? `<div style="color:#dc3545;font-size:12px;margin-top:4px">${job.error.message || JSON.stringify(job.error)}</div>` : ""}
        </div>
        <div class="job-actions">
          <button class="download" ${!canDownload ? "disabled" : ""} onclick="downloadJob('${job.job_id}', '${job.output_format}')">下载</button>
          <button class="delete" onclick="deleteJob('${job.job_id}')">删除</button>
        </div>
      </div>
    `;
  }).join("");
}

window.downloadJob = async (jobId, format) => {
  const fmt = format === "all" ? "zip" : format;
  window.open(`${API_BASE}/api/v1/jobs/${jobId}/download?format=${fmt}`, "_blank");
};

window.deleteJob = async (jobId) => {
  if (!confirm(`确定删除任务 ${jobId.slice(0, 8)}...?`)) return;
  try {
    const resp = await fetch(`${API_BASE}/api/v1/jobs/${jobId}`, { method: "DELETE" });
    if (resp.ok) {
      loadJobs();
    } else {
      alert("删除失败");
    }
  } catch (e) {
    alert(`删除失败: ${e.message}`);
  }
};

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(loadJobs, 3000);
}

// ===== Service Status =====
async function checkService() {
  try {
    const resp = await fetch(`${API_BASE}/health`);
    const data = await resp.json();
    $("serviceStatus").innerHTML = `<span class="status-ok">✅ 服务正常 (${data.service} v${data.version})</span>`;
  } catch (e) {
    $("serviceStatus").innerHTML = `<span class="status-error">❌ 服务不可用: ${e.message}</span>`;
  }
}

// ===== Init =====
$("saveConfig").addEventListener("click", saveConfig);
$("refreshJobs").addEventListener("click", loadJobs);

loadConfig();
checkService();
loadJobs();
startPolling();
