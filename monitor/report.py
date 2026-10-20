"""Build safe, self-contained HTML snapshots for local diagnostics."""

from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def _text(value: object) -> str:
    """Render a value without treating 0 or False as missing."""
    return "" if value is None else str(value)


def _safe_url(value: object) -> str:
    """Remove URL components that commonly carry credentials from exports."""
    text = _text(value)
    parsed = urlsplit(text)
    if not parsed.scheme or not parsed.netloc:
        return text
    host = parsed.hostname or ""
    try:
        port = parsed.port
    except ValueError:
        return parsed.scheme + "://" + host + parsed.path
    if port:
        host = f"{host}:{port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def _cell(value: object) -> str:
    return escape(_safe_url(value), quote=True)


def _status_label(status: object) -> str:
    labels = {"ok": "正常", "warn": "预警", "fail": "失败或不可用"}
    return labels.get(str(status), "未知")


def _attempt_label(check: dict[str, Any]) -> str:
    """Summarize retry evidence, staying explicit when it was not recorded."""
    metrics = check.get("metrics")
    if not isinstance(metrics, dict) or metrics.get("attempts") is None:
        return "未记录"
    label = _text(metrics.get("attempts"))
    if metrics.get("recovered_after_retry"):
        label += "（重试恢复）"
    return label


def build_report(snapshot: dict[str, Any], *, skipped_check_ids: tuple[str, ...]) -> bytes:
    """Return an offline HTML report without scripts, remote assets, or URL secrets."""
    summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
    checks = snapshot.get("checks") if isinstance(snapshot.get("checks"), list) else []
    rows: list[str] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{_cell(check.get('group', '未分组'))}</td>"
            f"<td>{_cell(check.get('name'))}</td>"
            f"<td>{_cell(check.get('type'))}</td>"
            f"<td>{_cell(check.get('target'))}</td>"
            f"<td>{_cell(_status_label(check.get('status')))}</td>"
            f"<td>{_cell(check.get('summary'))}</td>"
            f"<td>{_cell(check.get('detail'))}</td>"
            f"<td>{_cell(_attempt_label(check))}</td>"
            f"<td>{_cell(check.get('latency_ms'))}</td>"
            "</tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="9">本次没有已执行的检查。</td></tr>')

    skipped = ", ".join(escape(check_id, quote=True) for check_id in skipped_check_ids)
    generated_at = _cell(snapshot.get("generated_at"))
    health = _cell(summary.get("health"))
    totals = " / ".join(
        f"{label}: {_cell(summary.get(key, 0))}"
        for key, label in (("total", "总计"), ("ok", "正常"), ("warn", "预警"), ("fail", "失败"))
    )
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sentinel 本地诊断报告</title>
<style>
body{{font-family:system-ui,sans-serif;color:#17212b;margin:2rem;line-height:1.5}}
table{{border-collapse:collapse;width:100%;margin:1rem 0;table-layout:fixed}}
th,td{{border:1px solid #b9c3cc;padding:.55rem;text-align:left;overflow-wrap:anywhere;vertical-align:top}}
th{{background:#edf2f5}} .notice{{background:#f5f7f8;padding:1rem;border-left:4px solid #496a7a}}
@media print{{body{{margin:1cm}}}} @media(max-width:700px){{body{{margin:1rem}}table{{font-size:.85rem}}}}
</style>
</head>
<body>
<h1>Sentinel 本地诊断报告</h1>
<p>生成时间（UTC）：{generated_at}；总体状态：{health}；{totals}</p>
<section class="notice"><h2>证据边界</h2>
<p>以下是本机在生成时间实际测得的快照，不代表持续可用性或外部安全审计结论。失败或不可用结果并不等同于成功的负面结论。</p>
<p>已跳过（配置为 disabled）的检查 ID：{skipped or '无'}。</p>
<p>未包含独立的系统能力探测；DNS、路由、权限和网络策略等未测量能力须另行验证。</p></section>
<h2>已测量结果</h2>
<table><thead><tr><th>分组</th><th>名称</th><th>类型</th><th>目标</th><th>状态</th><th>摘要</th><th>详情</th><th>尝试</th><th>延迟 (ms)</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<p>导出时会移除 URL 中的用户信息、查询参数与片段。请勿在检查名称、错误描述或配置中存放凭据。</p>
</body></html>"""
    return document.encode("utf-8")
