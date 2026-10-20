<div align="center">

<img src="docs/assets/dashboard-desktop.png" alt="Sentinel 运维健康看板：总体状态、检测汇总、资产检测与健康轨迹" width="920">

# Sentinel · 运维健康看板

**把异常，提前看见。**

一个零依赖、默认只监听本机的运维健康看板。ICMP、TCP、TLS 与 HTTP 检测汇入同一条可信时间线。

[GitHub Actions](https://github.com/CiallorZ/ops-health-dashboard/actions/workflows/ci.yml)
· [Python 3.11+](https://www.python.org/)
· [MIT License](LICENSE)
· [v0.4.0](VERSION)

[介绍页](docs/index.html) · [安全边界](docs/SECURITY.md) · [测试说明](docs/TESTING.md) · [发布流程](docs/RELEASE.md) · [路线图](ROADMAP.md)

</div>

---

## 这是什么

Sentinel 面向“先自己看见，再等人投诉”的场景：本机或内网里跑一个小服务，按配置持续检查关键资产，并把真实证据放在一屏里。

它**不是**一个演示用的大屏，也不伪造成功率：

- 失败就是失败，重试恢复也会保留“曾经失败过”的证据；
- 每项结果都带延迟、状态码、证书天数或错误原因；
- 离线报告会明确标注已测量、已跳过与未测量能力。

## 效果预览

| 桌面端 | 移动端 |
|---|---|
| <img src="docs/assets/dashboard-desktop.png" alt="桌面端看板" width="720"> | <img src="docs/assets/dashboard-mobile.png" alt="移动端看板" width="240"> |

> 截图使用仓库内的 `examples/checks.demo.json` 与 `examples/demo_targets.py` 在本地真实取样：4 项正常、1 项延迟预警、1 项端口失败，且“对账 API”在第 2 次尝试后恢复。

## 介绍页

[![Sentinel 介绍页](docs/assets/landing-desktop.png)](docs/index.html)

介绍页采用自包含 HTML，可直接本地打开，也可作为 GitHub Pages 的静态入口。发布前请先确认仓库 Pages 设置；本仓库不会自动部署线上站点。

## 核心能力

| 能力 | 说明 |
|---|---|
| 四类检测 | ICMP ping、TCP 端口、TLS 证书剩余天数、HTTP 状态码与延迟 |
| 可解释状态 | `ok` / `warn` / `fail`，保留原始错误、延迟、状态码与证书信息 |
| 受限重试 | 每项可选 `0–2` 次额外尝试；结果记录实际尝试次数与是否重试恢复 |
| 业务分组 | 按核心业务、遗留系统、外部依赖等分组呈现 |
| 历史轨迹 | 每轮快照写入本地 JSONL，页面展示最近 40 次健康走势 |
| 离线报告 | `/api/report` 下载自包含 HTML，URL 凭据、查询参数与片段会被移除 |
| 有界超时 | 每项独立超时，单项故障不会拖垮整个看板 |
| 安全默认值 | 默认仅监听 `127.0.0.1`；CSP、`nosniff`、禁止 iframe；拒绝带凭据的 URL |
| 零构建链 | Python 标准库 + 原生 HTML/CSS/JS，无第三方运行时依赖 |
| 三端运行 | Windows 本机、Docker、任意 Python 3.11+ 环境 |

## 快速开始

要求：**Python 3.11 或更高版本**，不需要 `pip install`。

```powershell
# PowerShell / Windows
python server.py
```

```bash
# bash / macOS / Linux
python3 server.py
```

打开 <http://127.0.0.1:8080>。页面每 30 秒自动刷新，右上角按钮可立即重新采样。

```powershell
# 查看版本
python server.py --version

# 使用自定义配置与端口
python server.py --config checks.json --port 8080 --data-dir data
```

## 配置

所有资产都在 `checks.json` 中声明，修改后重启服务即可生效。

```json
{
  "version": 1,
  "thresholds": {
    "latency_warn_ms": 800,
    "latency_fail_ms": 2500,
    "tls_warn_days": 30,
    "tls_fail_days": 7
  },
  "checks": [
    {
      "id": "api",
      "name": "生产 API",
      "group": "核心服务",
      "type": "http",
      "target": "https://example.com/health",
      "expected_status": [200, 204],
      "timeout_seconds": 5,
      "retry_attempts": 1,
      "tags": ["production", "api"]
    },
    {
      "id": "ssh",
      "name": "跳板机 SSH",
      "group": "基础设施",
      "type": "tcp",
      "target": "10.0.0.10",
      "port": 22,
      "timeout_seconds": 3
    },
    {
      "id": "cert",
      "name": "主站证书",
      "type": "tls",
      "target": "example.com",
      "port": 443,
      "timeout_seconds": 5
    },
    {
      "id": "gateway",
      "name": "网关 ICMP",
      "type": "ping",
      "target": "192.168.1.1",
      "timeout_seconds": 3
    }
  ]
}
```

| 字段 | 说明 |
|---|---|
| `id` | 唯一标识，只能使用字母、数字、`-`、`_` |
| `type` | `http` / `tcp` / `tls` / `ping` |
| `target` | HTTP 为完整 URL；其余为主机名或 IP |
| `port` | `tcp` 必填；`tls` 默认 `443` |
| `expected_status` | HTTP 可接受状态码，默认 `[200]` |
| `verify_tls` | 是否验证证书链，默认 `true`；关闭会显著降低判断可信度 |
| `group` | 业务分组，默认 `未分组`，最多 80 个字符 |
| `timeout_seconds` | 单项超时，范围 `0.2–60` 秒 |
| `retry_attempts` | 失败后的额外尝试次数，范围 `0–2`，默认 `0`；单项最多执行 3 次 |
| `enabled` | 设为 `false` 可暂时停用单项 |

> **安全提醒**：不要在 `target`、名称或描述中写入密码、Token、Cookie 或带凭据的 URL。后端会拒绝 URL 内嵌凭据，但配置本身仍应保持干净。

## API

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/health` | 进程存活与版本，不触发资产检测 |
| `GET` | `/api/status` | 获取缓存快照；`?force=1` 强制重新检测 |
| `GET` | `/api/history?limit=40` | 读取历史摘要 |
| `GET` | `/api/config` | 只读配置，不含秘密 |
| `GET` | `/api/report` | 下载当前快照的离线 HTML 报告 |
| `POST` | `/api/refresh` | 强制刷新并返回最新快照 |

`/api/status` 默认缓存 8 秒，避免多标签页制造重复检测；`force=1` 与 `POST /api/refresh` 会绕过缓存。

## 架构

```text
checks.json
    │  严格校验：类型 / 端口 / 超时 / 阈值 / URL 凭据
    ▼
CheckRunnerService
    │  线程池并发 · 独立超时 · 受限重试 · 结果归一化
    ├── dashboard/       实时页面（原生 JS）
    ├── /api/*           只读 API
    ├── /api/report      自包含离线 HTML
    └── data/history.jsonl
```

目录：

```text
monitor/        检测、配置、运行器、历史与报告
dashboard/      页面、样式与前端逻辑
tests/          unittest（无第三方依赖）
examples/       本地演示配置与可控替身
docs/           介绍页、安全 / 测试 / 发布文档
scripts/        Windows 自启动与更新脚本
server.py       本地 HTTP 服务入口
```

## 安全边界

- 看板**没有登录系统**，默认只监听 `127.0.0.1`；不要直接暴露到公网。
- 配置中的目标会从运行看板的主机发起探测；请把它放在正确的网络位置。
- 不执行用户提供的任意命令；`ping` 参数经格式校验且不经过 shell。
- 离线报告会移除 URL 凭据、查询参数与片段，但**不要**把秘密写进名称或错误描述。
- TLS 检测用于发现证书到期与握手异常，不等同于完整的安全扫描。

完整说明见 [docs/SECURITY.md](docs/SECURITY.md)。

## 测试与质量门禁

```powershell
python -m unittest discover -s tests -v
python -W error::ResourceWarning -m unittest discover -s tests -q
python -m compileall -q monitor toolbox server.py tests
node --check dashboard\app.js
git diff --check
```

CI 在 Python 3.11 与 3.13 上运行同一套单元测试与编译检查。测试覆盖配置拒绝路径、HTTP/TLS 边界、并发刷新去重、强制刷新语义、受限重试、历史持久化、报告脱敏与 HTTP 安全响应头。

详细说明见 [docs/TESTING.md](docs/TESTING.md)。

## Docker

```powershell
docker compose up --build -d
```

容器只映射到本机 `127.0.0.1:8080`，数据保存在 `dashboard-data` volume。

## Windows 常驻

以当前用户身份安装登录启动项，不需要管理员权限：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-autostart.ps1 -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-autostart.ps1
```

卸载：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\uninstall-autostart.ps1
```

启动项会在登录后拉起看板，并检查 `origin/main` 的已验证更新。更新仅在干净工作区执行 fast-forward，且先跑测试。日志位于 `data\logs\`（已忽略，不会提交）。

## 演示与截图复现

```powershell
# 终端 1：启动本地可控替身（含一个会在 3 次握手后关闭的旧端口）
python examples\demo_targets.py --port 18081

# 终端 2：用演示配置启动看板
python server.py --port 18080 --config examples\checks.demo.json --data-dir data\demo
```

打开 <http://127.0.0.1:18080>，连续刷新或访问 `/api/status?force=1` 四次，即可得到“预警 → 异常”的真实历史轨迹。

## Roadmap

- [x] `v0.1` 基线：四类检测、实时看板、历史、CI、Docker 与 Windows 常驻。
- [x] `v0.2` 可读性：业务分组、自包含离线报告与 URL 脱敏。
- [x] `v0.3` 可信度：受限重试、实际尝试次数与恢复证据。
- [x] `v0.4` 可交付性：介绍页、截图、演示替身、维护文档与版本一致性修复。
- [ ] `v0.5` 告警：Webhook / 邮件事件，带去重与冷却。
- [ ] `v0.6` 趋势：按天聚合、可用率与证书到期日历。
- [ ] `v0.7` 多用户：只读分享、反向代理鉴权示例。

详见 [ROADMAP.md](ROADMAP.md)。

## License

MIT。见 [LICENSE](LICENSE)。
