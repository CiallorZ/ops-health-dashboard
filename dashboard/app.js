const REFRESH_MS = 30_000;

const elements = {
  connection: document.querySelector("#connection"),
  connectionText: document.querySelector("#connection-text"),
  refreshButton: document.querySelector("#refresh-button"),
  lastUpdated: document.querySelector("#last-updated"),
  runDuration: document.querySelector("#run-duration"),
  scoreCard: document.querySelector("#score-card"),
  scoreValue: document.querySelector("#score-value"),
  scoreState: document.querySelector("#score-state"),
  scoreTotal: document.querySelector("#score-total"),
  scoreRisk: document.querySelector("#score-risk"),
  metricOk: document.querySelector("#metric-ok"),
  metricWarn: document.querySelector("#metric-warn"),
  metricFail: document.querySelector("#metric-fail"),
  metricLatency: document.querySelector("#metric-latency"),
  checksList: document.querySelector("#checks-list"),
  trendBars: document.querySelector("#trend-bars"),
  toast: document.querySelector("#toast"),
  thresholdLatencyWarn: document.querySelector("#threshold-latency-warn"),
  thresholdLatencyFail: document.querySelector("#threshold-latency-fail"),
  thresholdTlsWarn: document.querySelector("#threshold-tls-warn"),
  thresholdTlsFail: document.querySelector("#threshold-tls-fail"),
  footerState: document.querySelector("#footer-state"),
  toolForm: document.querySelector("#tool-form"),
  toolFields: document.querySelector("#tool-fields"),
  toolRun: document.querySelector("#tool-run"),
  toolOutput: document.querySelector("#tool-output"),
  toolLocalNote: document.querySelector("#tool-local-note"),
};

let activeFilter = "all";
let latestStatus = null;
let loading = false;
let toastTimer = null;
let activeTool = "json-format";

const healthLabels = {
  healthy: "系统稳定",
  degraded: "存在预警",
  critical: "需要处置",
  empty: "没有启用检查",
  loading: "正在采集",
};

const statusLabels = {
  ok: "正常",
  warn: "预警",
  fail: "异常",
  unknown: "未知",
};

const toolDefinitions = {
  "json-format": {
    label: "JSON 格式化",
    local: true,
    fields: [
      {
        name: "text",
        label: "JSON 文本",
        type: "textarea",
        placeholder: '{"service": "sentinel", "healthy": true}',
      },
    ],
  },
  cidr: {
    label: "CIDR 计算",
    local: false,
    fields: [
      {
        name: "cidr",
        label: "CIDR",
        type: "text",
        placeholder: "192.168.1.0/24",
      },
    ],
  },
  ip: {
    label: "IP 分析",
    local: false,
    fields: [
      {
        name: "address",
        label: "IP 地址",
        type: "text",
        placeholder: "192.168.1.1 或 2001:db8::1",
      },
    ],
  },
  hash: {
    label: "哈希 / HMAC",
    local: false,
    fields: [
      {
        name: "text",
        label: "文本",
        type: "textarea",
        placeholder: "输入需要计算摘要的文本",
      },
      {
        name: "algorithm",
        label: "算法",
        type: "select",
        options: ["sha256", "sha512", "sha384", "sha1", "md5"],
      },
      {
        name: "encoding",
        label: "编码",
        type: "select",
        options: ["utf-8", "gbk", "ascii"],
      },
      {
        name: "key",
        label: "HMAC 密钥（可选）",
        type: "password",
        placeholder: "留空则计算普通摘要",
        required: false,
      },
    ],
  },
};

function formatNumber(value) {
  return Number.isFinite(value) ? String(Math.round(value)) : "--";
}

function formatTime(value) {
  if (!value) return "等待首次采样";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[character]));
}

function targetLabel(check) {
  if (check.type === "http") return check.target;
  if (check.type === "tcp" || check.type === "tls") {
    const port = check.port ?? (check.type === "tls" ? 443 : null);
    return port ? `${check.target}:${port}` : check.target;
  }
  return check.target;
}

function scoreFromSummary(summary) {
  if (!summary || !summary.total) return 0;
  const penalty = summary.warn * 10 + summary.fail * 30;
  return Math.max(0, Math.min(100, 100 - penalty));
}

function setConnection(state, text) {
  elements.connection.dataset.state = state;
  elements.connectionText.textContent = text;
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("is-visible");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    elements.toast.classList.remove("is-visible");
  }, 3000);
}

function renderSummary(data) {
  const summary = data.summary ?? {};
  const score = scoreFromSummary(summary);
  const health = summary.health ?? "empty";
  const total = summary.total ?? 0;
  elements.scoreCard.dataset.health = health;
  elements.scoreValue.textContent = total ? String(score) : "--";
  elements.scoreState.textContent = healthLabels[health] ?? "状态未知";
  elements.scoreTotal.textContent = `${total} 项资产`;
  const risk = summary.fail
    ? `${summary.fail} 项需要处置`
    : summary.warn
      ? `${summary.warn} 项待观察`
      : total
        ? "没有发现异常"
        : "等待配置";
  elements.scoreRisk.textContent = risk;
  elements.metricOk.textContent = formatNumber(summary.ok ?? 0);
  elements.metricWarn.textContent = formatNumber(summary.warn ?? 0);
  elements.metricFail.textContent = formatNumber(summary.fail ?? 0);

  const responsive = (data.checks ?? []).filter(
    (check) => Number.isFinite(check.latency_ms),
  );
  const average = responsive.length
    ? responsive.reduce((sum, check) => sum + check.latency_ms, 0) / responsive.length
    : null;
  elements.metricLatency.textContent = average === null ? "--" : `${Math.round(average)}`;

  elements.lastUpdated.textContent = `最近采样 ${formatTime(data.generated_at)}`;
  elements.runDuration.textContent = `${formatNumber(data.duration_ms)} ms`;
  elements.footerState.textContent = `${total} 项检查 · 本地数据 · 不采集凭据`;
}

function renderCheck(check) {
  const status = ["ok", "warn", "fail"].includes(check.status)
    ? check.status
    : "unknown";
  return `
    <article class="check-row" data-status="${escapeHtml(status)}">
      <span class="status-line ${escapeHtml(status)}" aria-hidden="true"></span>
      <div class="check-main">
        <div class="check-title">
          <strong>${escapeHtml(check.name)}</strong>
          <span class="check-type">${escapeHtml(check.type)}</span>
        </div>
        <p class="check-target">${escapeHtml(targetLabel(check))}</p>
        <p class="check-detail">${escapeHtml(check.detail || check.summary)}</p>
      </div>
      <div class="check-time">
        <strong>${check.latency_ms == null ? "--" : `${Math.round(check.latency_ms)} ms`}</strong>
        <span>${escapeHtml(statusLabels[status] ?? status)}</span>
      </div>
    </article>
  `;
}

function renderChecks() {
  const checks = latestStatus?.checks ?? [];
  const filtered = activeFilter === "all"
    ? checks
    : checks.filter((check) => check.status === activeFilter);

  if (!filtered.length) {
    elements.checksList.innerHTML = checks.length
      ? '<div class="empty-state">当前筛选下没有记录</div>'
      : '<div class="empty-state">没有可展示的检测结果</div>';
    return;
  }
  elements.checksList.innerHTML = filtered.map(renderCheck).join("");
}

function renderTrend(history) {
  const items = (history ?? []).slice(-32);
  if (!items.length) {
    elements.trendBars.innerHTML = '<div class="trend-empty">还没有历史采样</div>';
    return;
  }
  elements.trendBars.innerHTML = items.map((item) => {
    const ratio = item.total ? (item.ok / item.total) : 0;
    const height = Math.max(8, Math.round(ratio * 76));
    const health = ["healthy", "degraded", "critical"].includes(item.health)
      ? item.health
      : "degraded";
    const label = `${formatTime(item.generated_at)} · ${item.ok}/${item.total} 正常`;
    return `<div class="trend-bar ${health}" style="height:${height}px" title="${escapeHtml(label)}"></div>`;
  }).join("");
}

function renderConfig(config) {
  const thresholds = config?.thresholds ?? {};
  elements.thresholdLatencyWarn.textContent = `${formatNumber(thresholds.latency_warn_ms)} ms`;
  elements.thresholdLatencyFail.textContent = `${formatNumber(thresholds.latency_fail_ms)} ms`;
  elements.thresholdTlsWarn.textContent = `${formatNumber(thresholds.tls_warn_days)} 天`;
  elements.thresholdTlsFail.textContent = `${formatNumber(thresholds.tls_fail_days)} 天`;
}

function inputMarkup(field) {
  const placeholder = field.placeholder
    ? ` placeholder="${escapeHtml(field.placeholder)}"`
    : "";
  const required = field.required === false ? "" : " required";
  if (field.type === "textarea") {
    return `<textarea id="tool-${escapeHtml(field.name)}" name="${escapeHtml(field.name)}"${placeholder}${required}></textarea>`;
  }
  if (field.type === "select") {
    const options = field.options
      .map((option) => `<option value="${escapeHtml(option)}">${escapeHtml(option)}</option>`)
      .join("");
    return `<select id="tool-${escapeHtml(field.name)}" name="${escapeHtml(field.name)}">${options}</select>`;
  }
  return `<input id="tool-${escapeHtml(field.name)}" name="${escapeHtml(field.name)}" type="${escapeHtml(field.type)}"${placeholder} autocomplete="off"${required}>`;
}

function renderToolForm() {
  const definition = toolDefinitions[activeTool];
  elements.toolFields.innerHTML = definition.fields.map((field) => `
    <div class="tool-field">
      <label for="tool-${escapeHtml(field.name)}">${escapeHtml(field.label)}</label>
      ${inputMarkup(field)}
    </div>
  `).join("");
  elements.toolLocalNote.textContent = definition.local
    ? "浏览器本地处理 · 不发送"
    : "仅在本机服务执行 · 不上传外部";
  elements.toolOutput.innerHTML = `
    <p class="tool-output-label">OUTPUT / 结果</p>
    <p class="tool-output-empty">填写参数后点击“运行工具”。</p>
  `;
}

function formatJsonLocally(text) {
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new Error(`JSON 无效：${error.message}`);
  }
  return {
    valid: true,
    formatted: JSON.stringify(parsed, null, 2),
  };
}

function renderToolResult(result) {
  if (result.formatted) {
    elements.toolOutput.innerHTML = `
      <p class="tool-output-label">OUTPUT / 已格式化</p>
      <pre class="tool-json">${escapeHtml(result.formatted)}</pre>
    `;
    return;
  }
  const rows = Object.entries(result)
    .map(([key, value]) => {
      const isGood = value === true && /^(is_|valid)/.test(key);
      return `<div><dt>${escapeHtml(key)}</dt><dd class="${isGood ? "is-good" : ""}">${escapeHtml(String(value))}</dd></div>`;
    })
    .join("");
  elements.toolOutput.innerHTML = `
    <p class="tool-output-label">OUTPUT / 结果</p>
    <dl class="tool-result">${rows}</dl>
  `;
}

function renderToolError(message) {
  elements.toolOutput.innerHTML = `
    <p class="tool-output-label">OUTPUT / 错误</p>
    <p class="tool-output-error">${escapeHtml(message)}</p>
  `;
}

async function runTool() {
  const data = new FormData(elements.toolForm);
  const inputs = Object.fromEntries(data.entries());
  elements.toolRun.disabled = true;
  try {
    if (!String(inputs.text ?? inputs.cidr ?? inputs.address ?? "").trim()) {
      throw new Error("请先填写输入内容");
    }
    if (activeTool === "json-format") {
      renderToolResult(formatJsonLocally(inputs.text));
      return;
    }
    const response = await fetch("/api/tools/run", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ tool: activeTool, inputs }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error?.message || `工具调用失败：HTTP ${response.status}`);
    }
    renderToolResult(payload.result);
  } catch (error) {
    renderToolError(error.message);
  } finally {
    elements.toolRun.disabled = false;
  }
}

async function fetchJson(path, options) {
  const response = await fetch(path, {
    ...options,
    headers: { Accept: "application/json" },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function loadConfig() {
  try {
    renderConfig(await fetchJson("/api/config"));
  } catch {
    showToast("阈值配置读取失败");
  }
}

async function loadStatus({ force = false } = {}) {
  if (loading) return;
  loading = true;
  elements.refreshButton.disabled = true;
  setConnection("loading", force ? "重新采样" : "连接中");
  try {
    const data = await fetchJson(force ? "/api/status?force=1" : "/api/status");
    latestStatus = data;
    renderSummary(data);
    renderChecks();
    renderTrend(data.history);
    setConnection("ok", "实时");
    if (force) showToast("已刷新全部检测");
  } catch (error) {
    setConnection("fail", "离线");
    elements.checksList.innerHTML = `<div class="error-state">无法连接本地控制面：${escapeHtml(error.message)}</div>`;
  } finally {
    loading = false;
    elements.refreshButton.disabled = false;
  }
}

document.querySelectorAll(".filter").forEach((button) => {
  button.addEventListener("click", () => {
    activeFilter = button.dataset.filter ?? "all";
    document.querySelectorAll(".filter").forEach((item) => {
      item.classList.toggle("is-active", item === button);
    });
    renderChecks();
  });
});

elements.refreshButton.addEventListener("click", () => loadStatus({ force: true }));

document.querySelectorAll(".tool-tab").forEach((button) => {
  button.addEventListener("click", () => {
    activeTool = button.dataset.tool ?? "json-format";
    document.querySelectorAll(".tool-tab").forEach((item) => {
      const selected = item === button;
      item.classList.toggle("is-active", selected);
      item.setAttribute("aria-selected", String(selected));
    });
    renderToolForm();
  });
});

elements.toolForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runTool();
});

loadConfig();
loadStatus();
renderToolForm();
window.setInterval(() => loadStatus(), REFRESH_MS);

