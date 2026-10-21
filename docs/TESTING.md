# 测试与质量门禁

## 依赖

- Python 3.11+
- Node.js（仅用于 `node --check`）
- Git

无第三方 Python 运行时依赖，测试不访问公网。

## 必跑门禁

```powershell
python -m unittest discover -s tests -v
python -W error::ResourceWarning -m unittest discover -s tests -q
python -m compileall -q monitor toolbox server.py tests
node --check dashboard\app.js
node --check scripts\capture-screenshots.mjs
git diff --check
```

全部通过后，才允许提交。

## 覆盖范围

| 文件 | 关注点 |
|---|---|
| `tests/test_checks.py` | HTTP 状态码、跳转、TLS 边界、User-Agent 版本 |
| `tests/test_config.py` | 默认值、分组、重试边界、凭据拒绝、重复 ID |
| `tests/test_history.py` | 逐项可用率、延迟聚合、旧历史兼容、事件数量上限；真实 UTC 日趋势聚合、p50/p95、缺失日期不补造；历史单文件/归档上限、轮转链、超限压缩、零归档删除、畸形行跳过 |
| `tests/test_certificates.py` | 证书分级、按剩余天数排序、上限裁剪、过期与窗口边界、陈旧值重算、缺失与畸形指标跳过、链验证标记 |
| `tests/test_alerts.py` | Webhook 本地替身、HMAC 签名、冷却抑制、重试上限、秘密脱敏 |
| `tests/test_scheduler.py` | 后台循环采样、异常记录、停止与状态快照 |
| `tests/test_runner.py` | 缓存、强制刷新、并发去重、受限重试与恢复证据 |
| `tests/test_server.py` | 健康接口、版本头、404、静态页、报告脱敏 |
| `tests/test_report.py` | `0` 值渲染、重试证据、旧快照缺省值 |
| `tests/test_ui_contract.py` | 前端 API 引用、转义、无障碍钩子、版本一致性 |

网络相关测试全部使用本地可控替身或 `unittest.mock`，不依赖公网可用性。

## 手工验收

API / UI 改动需要在非 `8080` 的临时端口启动真实服务：

1. `GET /api/health` 返回当前版本；
2. 本地成功目标返回 `ok`；
3. 本地超时目标在超时上限内返回 `fail`；
4. 配置受限重试的目标显示实际尝试次数与恢复标记；
5. `/api/report` 可下载且包含证据边界；
6. 每项 heartbeat 数量不超过历史窗口，可用率来自实际采样；
7. 搜索名称 / 目标 / 分组 / 标签与 `ok / warn / fail` 筛选均生效；
8. 状态变化事件只在相邻真实状态不同的时候出现；
9. 桌面与 390 px 移动端无横向溢出，空状态与错误状态可读；
10. 结束后停止全部临时进程。
11. 配置本地 Webhook 替身，确认 `ok → fail` 与恢复事件都能投递，账本和 `/api/alerts` 不暴露 URL 或签名秘密。
12. 确认后台调度在页面关闭后仍持续采样，`/api/health` 与 `/api/status` 的 `automation.scheduler` 状态一致。
13. 请求 `/api/trends?days=7`，确认只出现有真实采样的 UTC 日期；`days=999` 被限制到 30，`days=soon` 回退到 7；看板长期趋势面板、空状态、错误状态与 390px 布局可读。
14. 请求 `/api/certificates`，确认 `tracked` 只统计真实 TLS 握手返回 `expires_at` 的检查；剩余天数随当前 UTC 时间变化而不是缓存中的旧值；`upcoming` 最多 8 条且只覆盖 90 天内到期；看板证书面板、空状态（没有 TLS 检查）与错误状态在 390px 下可读。
15. 请求 `/api/health`，确认 `retention.max_file_bytes`、`max_archive_files`、`max_total_bytes`、`max_load_lines` 与文档一致；`total_bytes <= max_total_bytes`；向 `data/history.jsonl` 连续写入超过上限后，确认出现 `history.1.jsonl`、归档不超过 2 份，且页面“历史占用”与“历史归档”显示真实值。

## 截图复现

```powershell
python examples\demo_targets.py --port 18081
python server.py --port 18080 --config examples\checks.demo.json --data-dir data\demo
```

连续请求 `/api/status?force=1` 四次：前三次旧端口可用，第四次端口关闭后变为异常。逐项 heartbeat 会同时包含两种状态，并生成一条 `ok → fail` 变化事件。

## CI

`.github/workflows/ci.yml` 在 `main` 推送与 Pull Request 上运行 Python 3.11 / 3.13 的单元测试与编译检查。
