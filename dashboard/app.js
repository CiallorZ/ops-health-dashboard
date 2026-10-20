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
  checksCount: document.querySelector("#checks-count"),
  checkSearch: document.querySelector("#check-search"),
  trendBars: document.querySelector("#trend-bars"),
  transitionList: document.querySelector("#transition-list"),
  toast: document.querySelector("#toast"),
  thresholdLatencyWarn: document.querySelector("#threshold-latency-warn"),
  thresholdLatencyFail: document.querySelector("#threshold-latency-fail"),
  thresholdTlsWarn: document.querySelector("#threshold-tls-warn"),
  thresholdTlsFail: document.querySelector("#threshold-tls-fail"),
  footerState: document.querySelector("#footer-state"),
};

let activeFilter = "all";
let searchQuery = "";
let latestStatus = null;
let loading = false;
let toastTimer = null;

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

function formatNumber(value) {
  return Number.isFinite(value) ? String(Math.round(value)) : "--";
}

function formatPercent(value) {
  if (!Number.isFinite(value)) return "--";
  return `${value.toFixed(Number.isInteger(value) ? 0 : 1)}%`;
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

function checkProvidesOwn(object, key) {
  return object !== null && Object.prototype.hasOwnProperty.call(object, key);
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
  elements.footerState.textContent = `${total} 项检查 · 40 轮可追溯 · 不采集凭据`;
}

function renderCheck(check) {
  const status = ["ok", "warn", "fail"].includes(check.status)
    ? check.status
    : "unknown";
  const attempts = Number(check.metrics?.attempts ?? 1);
  const attemptNote = attempts > 1
    ? ` · 第 ${attempts} 次尝试${check.metrics?.recovered_after_retry ? "恢复" : ""}`
    : "";
  const historyById = latestStatus?.check_history?.checks;
  const insight = checkProvidesOwn(historyById, check.id) ? historyById[check.id] : null;
  const heartbeats = Array.isArray(insight?.heartbeats) ? insight.heartbeats : [];
  const samples = Number(insight?.samples ?? heartbeats.length);
  const availability = Number.isFinite(insight?.availability_percent)
    ? insight.availability_percent
    : null;
  const averageLatency = Number.isFinite(insight?.average_latency_ms)
    ? insight.average_latency_ms
    : null;
  const tags = Array.isArray(check.tags) ? check.tags.filter((tag) => typeof tag === "string") : [];
  const tagHtml = tags.length
    ? `<div class="check-tags">${tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}</div>`
    : "";
  const heartbeatHtml = heartbeats.length
    ? `
      <div
        class="heartbeat-strip"
        role="img"
        aria-label="${escapeHtml(`${samples} 轮历史，可用率 ${formatPercent(availability)}`)}"
      >
        ${heartbeats.map((sample) => {
          const sampleStatus = ["ok", "warn", "fail"].includes(sample.status)
            ? sample.status
            : "unknown";
          const latency = Number.isFinite(sample.latency_ms)
            ? ` · ${Math.round(sample.latency_ms)} ms`
            : "";
          const label = `${formatTime(sample.at)} · ${statusLabels[sampleStatus] ?? "未知"}${latency}`;
          return `<span class="heartbeat ${sampleStatus}" title="${escapeHtml(label)}"></span>`;
        }).join("")}
      </div>
    `
    : '<div class="heartbeat-missing">尚无逐项历史，下一轮采样后开始积累</div>';
  const averageNote = Number.isFinite(averageLatency)
    ? `均延迟 ${Math.round(averageLatency)} ms`
    : "均延迟 --";
  return `
    <article class="check-row" data-status="${escapeHtml(status)}">
      <span class="status-line ${escapeHtml(status)}" aria-hidden="true"></span>
      <div class="check-main">
        <div class="check-title">
          <strong>${escapeHtml(check.name)}</strong>
          <span class="check-type">${escapeHtml(check.type)}</span>
        </div>
        ${tagHtml}
        <p class="check-target">${escapeHtml(targetLabel(check))}</p>
        <p class="check-detail">${escapeHtml(check.detail || check.summary)}${escapeHtml(attemptNote)}</p>
        <div class="check-evidence">
          <div class="heartbeat-head">
            <span class="availability">可用率 <strong>${escapeHtml(formatPercent(availability))}</strong></span>
            <span>${escapeHtml(`${samples} / ${Number(insight?.window ?? 40)} 轮 · ${averageNote}`)}</span>
          </div>
          ${heartbeatHtml}
        </div>
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
  const query = searchQuery.trim().toLocaleLowerCase("zh-CN");
  const filtered = checks.filter((check) => {
    if (activeFilter !== "all" && check.status !== activeFilter) return false;
    if (!query) return true;
    const haystack = [
      check.name,
      check.target,
      targetLabel(check),
      check.group,
      ...(Array.isArray(check.tags) ? check.tags : []),
    ].join(" ").toLocaleLowerCase("zh-CN");
    return haystack.includes(query);
  });
  elements.checksCount.textContent = `${filtered.length} / ${checks.length}`;

  if (!filtered.length) {
    elements.checksList.innerHTML = checks.length
      ? '<div class="empty-state">没有匹配的检查，试试清除搜索或切换状态。</div>'
      : '<div class="empty-state">没有可展示的检测结果</div>';
    return;
  }
  const groups = new Map();
  for (const check of filtered) {
    const group = String(check.group || "未分组");
    const items = groups.get(group) ?? [];
    items.push(check);
    groups.set(group, items);
  }
  elements.checksList.innerHTML = Array.from(groups, ([group, items]) => `
    <section class="check-group">
      <h3 class="check-group-title">${escapeHtml(group)} <span>${items.length} 项</span></h3>
      ${items.map(renderCheck).join("")}
    </section>
  `).join("");
}

function renderTransitions() {
  const events = Array.isArray(latestStatus?.check_history?.events)
    ? latestStatus.check_history.events
    : [];
  if (!events.length) {
    elements.transitionList.innerHTML =
      '<div class="transition-empty">历史中尚未记录到状态变化</div>';
    return;
  }
  elements.transitionList.innerHTML = events.map((event) => {
    const from = ["ok", "warn", "fail"].includes(event.from) ? event.from : "unknown";
    const to = ["ok", "warn", "fail"].includes(event.to) ? event.to : "unknown";
    return `
      <article class="transition-row">
        <span class="transition-flow" aria-hidden="true">
          <i class="${escapeHtml(from)}"></i>
          <span>→</span>
          <i class="${escapeHtml(to)}"></i>
        </span>
        <div class="transition-main">
          <strong>${escapeHtml(event.name || event.check_id)}</strong>
          <p>
            ${escapeHtml(statusLabels[from] ?? "未知")} → ${escapeHtml(statusLabels[to] ?? "未知")}
            <span>· ${escapeHtml(event.group || "未分组")}</span>
          </p>
        </div>
        <time datetime="${escapeHtml(event.at)}">${escapeHtml(formatTime(event.at))}</time>
      </article>
    `;
  }).join("");
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
    renderTransitions();
    setConnection("ok", "实时");
    if (force) showToast("已刷新全部检测");
  } catch (error) {
    setConnection("fail", "离线");
    elements.checksCount.textContent = "离线";
    elements.checksList.innerHTML = `<div class="error-state">无法连接本地控制面：${escapeHtml(error.message)}</div>`;
    elements.transitionList.innerHTML =
      `<div class="transition-empty is-error">无法读取状态变化：${escapeHtml(error.message)}</div>`;
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

elements.checkSearch.addEventListener("input", () => {
  searchQuery = elements.checkSearch.value;
  renderChecks();
});

elements.refreshButton.addEventListener("click", () => loadStatus({ force: true }));

loadConfig();
loadStatus();
window.setInterval(() => loadStatus(), REFRESH_MS);

