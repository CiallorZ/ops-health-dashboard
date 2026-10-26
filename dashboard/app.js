const REFRESH_MS = 10_000;

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
  monitorInterval: document.querySelector("#monitor-interval"),
  trendSource: document.querySelector("#trend-source"),
  trendDays: document.querySelector("#trend-days"),
  trendDaysWithData: document.querySelector("#trend-days-with-data"),
  trendPercentiles: document.querySelector("#trend-percentiles"),
  longTrendList: document.querySelector("#long-trend-list"),
  certificateWindow: document.querySelector("#certificate-window"),
  certificateTracked: document.querySelector("#certificate-tracked"),
  certificateNearest: document.querySelector("#certificate-nearest"),
  certificateCounts: document.querySelector("#certificate-counts"),
  certificateList: document.querySelector("#certificate-list"),
  maintenanceState: document.querySelector("#maintenance-state"),
  maintenanceList: document.querySelector("#maintenance-list"),
  schedulerState: document.querySelector("#scheduler-state"),
  schedulerInterval: document.querySelector("#scheduler-interval"),
  schedulerLast: document.querySelector("#scheduler-last"),
  schedulerNext: document.querySelector("#scheduler-next"),
  alertConfigState: document.querySelector("#alert-config-state"),
  alertList: document.querySelector("#alert-list"),
  toast: document.querySelector("#toast"),
  thresholdLatencyWarn: document.querySelector("#threshold-latency-warn"),
  thresholdLatencyFail: document.querySelector("#threshold-latency-fail"),
  thresholdTlsWarn: document.querySelector("#threshold-tls-warn"),
  thresholdTlsFail: document.querySelector("#threshold-tls-fail"),
  retentionState: document.querySelector("#retention-state"),
  retentionUsage: document.querySelector("#retention-usage"),
  retentionArchives: document.querySelector("#retention-archives"),
  domainBudgetDefault: document.querySelector("#domain-budget-default"),
  retentionNote: document.querySelector("#retention-note"),
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
  unknown: "部分状态未知",
  loading: "正在采集",
};

const statusLabels = {
  ok: "正常",
  warn: "预警",
  fail: "异常",
  unknown: "未知",
};

const alertStatusLabels = {
  queued: "排队",
  delivering: "投递中",
  retrying: "重试中",
  delivered: "已送达",
  failed: "失败",
  suppressed: "已抑制",
};

const alertEventLabels = {
  down: "故障",
  recovered: "恢复",
  degraded: "降级",
  status_change: "状态变化",
};

function formatNumber(value) {
  return Number.isFinite(value) ? String(Math.round(value)) : "--";
}

function formatPercent(value) {
  if (!Number.isFinite(value)) return "--";
  return `${value.toFixed(Number.isInteger(value) ? 0 : 1)}%`;
}

function formatInterval(value) {
  if (!Number.isFinite(value)) return "--";
  if (value < 60) return `${Math.round(value)} 秒`;
  if (value % 60 === 0) return `${Math.round(value / 60)} 分钟`;
  return `${Math.round(value)} 秒`;
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

function formatDate(value) {
  if (!value) return "未知日期";
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return "未知日期";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    timeZone: "UTC",
  }).format(date);
}

function formatDateTime(value) {
  if (!value) return "时间未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatLatency(value) {
  return Number.isFinite(value) ? `${Math.round(value)} ms` : "--";
}

function formatDays(value) {
  // Number(null) is 0, so missing evidence must be rejected before coercion:
  // "no certificate measured yet" is not the same as "expires today".
  if (value === null || value === undefined || typeof value !== "number") {
    return "--";
  }
  if (!Number.isFinite(value)) return "--";
  const days = value;
  if (days <= 0) return "已过期";
  if (days < 1) return "不足 1 天";
  return `${Math.round(days)} 天`;
}

function formatDuration(seconds) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) {
    return "--";
  }
  if (seconds < 60) return "不足 1 分钟";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} 分钟`;
  if (minutes < 60 * 48) {
    const hours = Math.floor(minutes / 60);
    const rest = minutes % 60;
    return rest ? `${hours} 小时 ${rest} 分钟` : `${hours} 小时`;
  }
  return `${Math.floor(minutes / (60 * 24))} 天`;
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
  elements.scoreValue.textContent = total && !summary.unknown ? String(score) : "--";
  elements.scoreState.textContent = healthLabels[health] ?? "状态未知";
  elements.scoreTotal.textContent = `${total} 项资产`;
  const risk = summary.fail
    ? `${summary.fail} 项需要处置`
    : summary.unknown
      ? `${summary.unknown} 项缺少判定依据`
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
  const status = ["ok", "warn", "fail", "unknown"].includes(check.status)
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
          const sampleStatus = ["ok", "warn", "fail", "unknown"].includes(sample.status)
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
          <span class="check-domain">${escapeHtml(check.domain || "network")}</span>
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
      check.domain,
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
    const health = ["healthy", "degraded", "critical", "unknown"].includes(item.health)
      ? item.health
      : "degraded";
    const label = `${formatTime(item.generated_at)} · ${item.ok}/${item.total} 正常`;
    return `<div class="trend-bar ${health}" style="height:${height}px" title="${escapeHtml(label)}"></div>`;
  }).join("");
}

function renderLongTrend(trends) {
  const daily = trends && typeof trends.daily === "object" && trends.daily !== null
    ? Object.entries(trends.daily)
    : [];
  const days = Number(trends?.days ?? 7);
  elements.trendDays.textContent = Number.isFinite(days) ? `${days} 天` : "--";
  elements.trendDaysWithData.textContent = daily.length
    ? `${daily.length} / ${Number.isFinite(days) ? days : 7} 天`
    : "0 天";
  elements.trendSource.textContent = trends?.generated_from_utc_days
    ? "按 UTC 日切"
    : "读取中";

  const latest = daily[0]?.[1] ?? null;
  elements.trendPercentiles.textContent = latest
    ? `${formatLatency(latest.p50_latency_ms)} / ${formatLatency(latest.p95_latency_ms)}`
    : "--";

  if (!daily.length) {
    elements.longTrendList.innerHTML =
      '<div class="trend-empty">还没有按天聚合；后台采样跨过一个 UTC 日切后会出现</div>';
    return;
  }

  elements.longTrendList.innerHTML = daily.map(([day, item]) => {
    const availability = Number.isFinite(item.availability_percent)
      ? item.availability_percent
      : null;
    const tone = item.fail
      ? "critical"
      : item.warn
        ? "degraded"
        : item.unknown
          ? "unknown"
          : "healthy";
    return `
      <article class="long-trend-row" data-tone="${escapeHtml(tone)}">
        <div class="long-trend-head">
          <strong>${escapeHtml(formatDate(day))}</strong>
          <span>${escapeHtml(`${item.samples} 次采样 · 可用率 ${formatPercent(availability)}`)}</span>
        </div>
        <div class="long-trend-bar" aria-hidden="true">
          <i style="width:${availability === null ? 0 : Math.max(2, Math.round(availability))}%"></i>
        </div>
        <div class="long-trend-meta">
          <span>p50 ${escapeHtml(formatLatency(item.p50_latency_ms))}</span>
          <span>p95 ${escapeHtml(formatLatency(item.p95_latency_ms))}</span>
          <span>异常 ${escapeHtml(String(item.fail ?? 0))}</span>
        </div>
      </article>
    `;
  }).join("");
}

async function loadTrends() {
  try {
    renderLongTrend(await fetchJson("/api/trends?days=7"));
  } catch (error) {
    elements.trendSource.textContent = "不可用";
    elements.longTrendList.innerHTML =
      `<div class="trend-empty is-error">按天聚合读取失败：${escapeHtml(error.message)}</div>`;
  }
}

const certificateGrades = {
  healthy: "有效",
  warning: "预警",
  critical: "紧急",
};

function formatExpiry(value) {
  if (!value) return "时间未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "UTC",
  }).format(date);
}

function renderCertificates(calendar) {
  const counts = calendar?.counts ?? {};
  const tracked = Number(calendar?.tracked ?? 0);
  const window_days = Number(calendar?.upcoming_window_days ?? 90);
  elements.certificateWindow.textContent = `近 ${window_days} 天`;
  elements.certificateTracked.textContent = Number.isFinite(tracked)
    ? `${tracked} 张`
    : "--";
  elements.certificateNearest.textContent = formatDays(
    calendar?.nearest_remaining_days,
  );
  elements.certificateCounts.textContent = `${counts.warning ?? 0} / ${counts.critical ?? 0}`;

  const upcoming = Array.isArray(calendar?.upcoming) ? calendar.upcoming : [];
  if (!tracked) {
    elements.certificateList.innerHTML =
      '<div class="certificate-empty">还没有 TLS 检查返回证书指标</div>';
    return;
  }
  if (!upcoming.length) {
    elements.certificateList.innerHTML =
      `<div class="certificate-empty">跟踪 ${tracked} 张证书，近 ${window_days} 天内没有到期</div>`;
    return;
  }

  elements.certificateList.innerHTML = upcoming.map((entry) => {
    const grade = certificateGrades[entry.grade] ? entry.grade : "healthy";
    const remaining = formatDays(Number(entry.remaining_days));
    const verified = entry.verified ? "已验证链" : "未验证链";
    const commonName = entry.common_name ? ` · CN ${entry.common_name}` : "";
    const port = Number.isFinite(Number(entry.port)) ? `:${Number(entry.port)}` : "";
    return `
      <article class="certificate-row" data-grade="${escapeHtml(grade)}">
        <div class="certificate-head">
          <strong>${escapeHtml(entry.name || entry.check_id)}</strong>
          <span class="certificate-days">${escapeHtml(remaining)}</span>
        </div>
        <p class="certificate-target">
          ${escapeHtml(entry.group || "未分组")} · ${escapeHtml(`${entry.target ?? ""}${port}`)}
        </p>
        <div class="certificate-meta">
          <span>${escapeHtml(certificateGrades[grade])}</span>
          <span>${escapeHtml(verified)}</span>
          <span>${escapeHtml(`到期 ${formatExpiry(entry.expires_at)}${commonName}`)}</span>
        </div>
      </article>
    `;
  }).join("");
}

async function loadCertificates() {
  try {
    renderCertificates(await fetchJson("/api/certificates"));
  } catch (error) {
    elements.certificateWindow.textContent = "不可用";
    elements.certificateList.innerHTML =
      `<div class="certificate-empty is-error">证书日历读取失败：${escapeHtml(error.message)}</div>`;
  }
}

function renderAutomation(data) {
  const automation = data.automation ?? {};
  const scheduler = automation.scheduler ?? {};
  const alerts = automation.alerts ?? {};
  renderRetention(automation.retention);
  const running = Boolean(scheduler.running);
  const failed = Boolean(scheduler.last_error);
  elements.schedulerState.dataset.state = failed ? "fail" : running ? "ok" : "idle";
  elements.schedulerState.textContent = failed
    ? "调度异常"
    : running
      ? "后台运行"
      : "未启动";
  elements.schedulerInterval.textContent = formatInterval(
    Number(scheduler.interval_seconds),
  );
  elements.schedulerLast.textContent = scheduler.last_completed_at
    ? formatTime(scheduler.last_completed_at)
    : "等待首轮";
  elements.schedulerNext.textContent = running && scheduler.next_run_at
    ? formatTime(scheduler.next_run_at)
    : "手动模式";

  const recent = Array.isArray(alerts.recent) ? alerts.recent : [];
  elements.alertConfigState.textContent = alerts.configured
    ? `${alerts.signed ? "签名" : "未签名"}${alerts.pending ? ` · ${alerts.pending} 待投递` : ""}`
    : "未配置";
  elements.alertConfigState.dataset.state = alerts.configured ? "ok" : "idle";

  if (!alerts.configured) {
    elements.alertList.innerHTML =
      '<div class="alert-empty">在 checks.json 中配置 notifications.webhook_url 后启用</div>';
    return;
  }
  if (!recent.length) {
    elements.alertList.innerHTML =
      '<div class="alert-empty">还没有状态变化；下一次失败或恢复会出现在这里</div>';
    return;
  }

  elements.alertList.innerHTML = recent.slice(0, 4).map((event) => {
    const delivery = alertStatusLabels[event.status] ? event.status : "failed";
    const eventType = alertEventLabels[event.event] ? event.event : "status_change";
    const attempts = Number(event.attempts ?? 0);
    const attemptLabel = attempts > 1 ? ` · ${attempts} 次` : "";
    return `
      <article class="alert-row" data-state="${escapeHtml(delivery)}">
        <span class="alert-event">${escapeHtml(alertEventLabels[eventType])}</span>
        <div class="alert-main">
          <strong>${escapeHtml(event.check_name || event.check_id || "未知检查")}</strong>
          <p>
            ${escapeHtml(statusLabels[event.from_status] ?? event.from_status ?? "未知")}
            → ${escapeHtml(statusLabels[event.to_status] ?? event.to_status ?? "未知")}
            <span>${escapeHtml(alertStatusLabels[delivery])}${escapeHtml(attemptLabel)}</span>
          </p>
        </div>
        <time datetime="${escapeHtml(event.completed_at || event.created_at)}">${escapeHtml(formatTime(event.completed_at || event.created_at))}</time>
      </article>
    `;
  }).join("");
}

const maintenanceLabels = {
  active: "进行中",
  upcoming: "即将开始",
};

function renderMaintenance(maintenance) {
  if (!maintenance || typeof maintenance !== "object") {
    elements.maintenanceState.textContent = "未知";
    elements.maintenanceState.dataset.state = "idle";
    elements.maintenanceList.innerHTML =
      '<div class="maintenance-empty">维护计划读取失败</div>';
    return;
  }
  const active = Array.isArray(maintenance.active) ? maintenance.active : [];
  const upcoming = Array.isArray(maintenance.upcoming) ? maintenance.upcoming : [];
  const configured = Boolean(maintenance.configured);
  const covered = Array.isArray(maintenance.active_check_ids)
    ? maintenance.active_check_ids
    : [];

  if (active.length) {
    elements.maintenanceState.textContent = `维护中 · ${covered.length} 项`;
    elements.maintenanceState.dataset.state = "warn";
  } else if (upcoming.length) {
    elements.maintenanceState.textContent = `${upcoming.length} 个待开始`;
    elements.maintenanceState.dataset.state = "ok";
  } else {
    elements.maintenanceState.textContent = configured ? "无进行中" : "未配置";
    elements.maintenanceState.dataset.state = "idle";
  }

  const rows = [
    ...active.map((item) => ({ ...item, state: "active" })),
    ...upcoming.map((item) => ({ ...item, state: "upcoming" })),
  ];
  if (!rows.length) {
    elements.maintenanceList.innerHTML = configured
      ? '<div class="maintenance-empty">已配置维护窗口，但当前没有进行中或即将开始的窗口</div>'
      : '<div class="maintenance-empty">在 checks.json 中配置 maintenance_windows 后启用</div>';
    return;
  }

  elements.maintenanceList.innerHTML = rows.map((item) => {
    const state = maintenanceLabels[item.state] ? item.state : "upcoming";
    const scope = Array.isArray(item.check_ids) && item.check_ids.length
      ? item.check_ids.join(", ")
      : "全部检查";
    const remainingLabel = state === "active" ? "剩余" : "开始于";
    const remaining = state === "active"
      ? formatDuration(Number(item.remaining_seconds))
      : formatDateTime(item.starts_at);
    const suppression = item.suppress_alerts === false ? "仅展示" : "抑制告警";
    return `
      <article class="maintenance-row" data-state="${escapeHtml(state)}">
        <div class="maintenance-head">
          <strong>${escapeHtml(item.name || item.id)}</strong>
          <span class="maintenance-badge">${escapeHtml(maintenanceLabels[state])}</span>
        </div>
        <p class="maintenance-scope">${escapeHtml(scope)} · ${escapeHtml(suppression)}</p>
        <div class="maintenance-meta">
          <span>${escapeHtml(`${remainingLabel} ${remaining}`)}</span>
          <span>${escapeHtml(`结束 ${formatDateTime(item.ends_at)}`)}</span>
        </div>
      </article>
    `;
  }).join("");
}

function renderConfig(config) {
  const thresholds = config?.thresholds ?? {};
  elements.thresholdLatencyWarn.textContent = `${formatNumber(thresholds.latency_warn_ms)} ms`;
  elements.thresholdLatencyFail.textContent = `${formatNumber(thresholds.latency_fail_ms)} ms`;
  elements.thresholdTlsWarn.textContent = `${formatNumber(thresholds.tls_warn_days)} 天`;
  elements.thresholdTlsFail.textContent = `${formatNumber(thresholds.tls_fail_days)} 天`;
  elements.monitorInterval.textContent =
    `后台每 ${formatInterval(Number(config?.monitor_interval_seconds))}采样`;
  const budget = config?.domain_budget ?? {};
  const defaultWorkers = Number(budget.default);
  const overrides = Object.entries(budget).filter(
    ([domain, workers]) => domain !== "default" && Number(workers) !== defaultWorkers,
  );
  elements.domainBudgetDefault.textContent = Number.isFinite(defaultWorkers)
    ? overrides.length
      ? `${defaultWorkers}（${overrides.length} 域自定义）`
      : `${defaultWorkers}`
    : "--";
}

function formatBytes(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--";
  if (value < 1024) return `${Math.round(value)} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(2)} MiB`;
}

function renderRetention(retention) {
  const current = retention?.current_bytes;
  const maxTotal = retention?.max_total_bytes;
  if (typeof current !== "number" || typeof maxTotal !== "number") {
    elements.retentionState.textContent = "未知";
    elements.retentionState.dataset.state = "idle";
    elements.retentionUsage.textContent = "--";
    elements.retentionArchives.textContent = "--";
    return;
  }
  const archives = Array.isArray(retention.archives) ? retention.archives : [];
  const total = Number(retention.total_bytes ?? current);
  const ratio = maxTotal ? Math.min(1, total / maxTotal) : 0;
  const truncated = Boolean(retention.truncated);
  elements.retentionState.textContent = truncated ? "已截断" : "有界";
  elements.retentionState.dataset.state = truncated ? "warn" : "ok";
  elements.retentionUsage.textContent =
    `${formatBytes(total)} / ${formatBytes(maxTotal)}（${Math.round(ratio * 100)}%）`;
  elements.retentionArchives.textContent = archives.length
    ? `${archives.length} / ${Number(retention.max_archive_files ?? 0)} 份`
    : "无";
  elements.retentionNote.innerHTML = truncated
    ? "历史超过保留上限，较早的采样已被截断；趋势只统计仍在磁盘上的真实采样。"
    : "当前历史文件与归档都在上限内；超出时自动轮转，不会无限增长。";
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
    renderAutomation(data);
    renderMaintenance(data.automation?.maintenance);
    await loadTrends();
    await loadCertificates();
    setConnection("ok", "实时");
    if (force) showToast("已刷新全部检测");
  } catch (error) {
    setConnection("fail", "离线");
    elements.checksCount.textContent = "离线";
    elements.checksList.innerHTML = `<div class="error-state">无法连接本地控制面：${escapeHtml(error.message)}</div>`;
    elements.transitionList.innerHTML =
      `<div class="transition-empty is-error">无法读取状态变化：${escapeHtml(error.message)}</div>`;
    elements.schedulerState.dataset.state = "fail";
    elements.schedulerState.textContent = "不可用";
    elements.alertList.innerHTML =
      `<div class="alert-empty is-error">无法读取告警账本：${escapeHtml(error.message)}</div>`;
    elements.maintenanceState.textContent = "不可用";
    elements.maintenanceState.dataset.state = "fail";
    elements.maintenanceList.innerHTML =
      `<div class="maintenance-empty is-error">无法读取维护计划：${escapeHtml(error.message)}</div>`;
    elements.retentionState.textContent = "不可用";
    elements.retentionState.dataset.state = "fail";
    elements.retentionUsage.textContent = "--";
    elements.retentionArchives.textContent = "--";
    elements.trendSource.textContent = "不可用";
    elements.longTrendList.innerHTML =
      `<div class="trend-empty is-error">无法读取按天聚合：${escapeHtml(error.message)}</div>`;
    elements.certificateWindow.textContent = "不可用";
    elements.certificateList.innerHTML =
      `<div class="certificate-empty is-error">无法读取证书日历：${escapeHtml(error.message)}</div>`;
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

