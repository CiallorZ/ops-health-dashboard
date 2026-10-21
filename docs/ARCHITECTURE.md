# Sentinel 架构与开发方向

本文回答两个问题：**现在是什么形态**，以及**接下来往哪里长**。

它只描述仓库中真实存在的实现；未实现的能力一律标注为“缺口”，不做能力包装。

当前版本：`0.10.0`（2026-10-21）

## 1. 定位与不变式

Sentinel 是**单机、自托管、只展示真实探测事实**的运维健康看板。它不追求成为通用监控 SaaS。

五条不变式，任何演进都不能破坏：

| 不变式 | 具体含义 |
|---|---|
| 只展示测到的事实 | 没有采样的日期不补造，没有握手的证书不显示到期日 |
| 证据优先 | 每个状态可回溯到延迟、状态码、证书天数或错误类别 |
| 本地优先 | 默认只听 `127.0.0.1`，运行时零第三方依赖 |
| 有界行为 | 检查数、超时、重试、历史体积、告警条数、维护窗口都有硬上限 |
| 最小可审计 | 不执行任意命令，不读写配置以外的任意路径 |

## 2. 现状架构

```text
                   ┌─────────────────────────────┐
   checks.json ───▶ │  严格校验 (monitor/config)   │
                   └──────────────┬──────────────┘
                                  ▼
                   ┌─────────────────────────────┐
   BackgroundMonitor ───────────▶ │  CheckRunnerService        │
     (周期采样)                   │  线程池 8 · 独立超时        │
                                  │  受限重试 · 状态迁移        │
                                  └───┬───────────┬──────────┘
                                      │           │
              ┌───────────────────────┘           └──────────────┐
              ▼                                                  ▼
   ┌────────────────────┐                            ┌────────────────────┐
   │ HistoryStore       │                            │ AlertDispatcher    │
   │ history.jsonl      │                            │ 冷却/重试/HMAC     │
   │ 4 MiB · 2 归档     │                            │ alerts.json (80)   │
   └─────────┬──────────┘                            └─────────┬──────────┘
             │                                                  │
             └───────────────┬──────────────────────────────────┘
                             ▼
              ┌──────────────────────────────┐
              │ ThreadingHTTPServer (server) │
              │ /api/* · 静态页面 · 报告     │
              └──────────────┬───────────────┘
                             ▼
                    dashboard/ (原生 JS)
```

模块职责（均为标准库实现）：

| 模块 | 职责 | 关键上限 |
|---|---|---|
| `monitor/config.py` | 配置校验、默认值、公开视图 | 200 项检查，超时 1–60 s |
| `monitor/checks.py` | `ping` / `tcp` / `tls` / `http` 四类探测 | 单项超时 1–60 s，重试 0–2 |
| `monitor/runner.py` | 并发执行、快照缓存、状态迁移 | 8 线程，缓存 8 s |
| `monitor/scheduler.py` | 后台周期采样 | 10–3600 s |
| `monitor/history.py` | JSONL 追加、轮转、趋势聚合 | 4 MiB / 2 归档 / 5000 行 / 240 轮 |
| `monitor/alerts.py` | Webhook 投递、冷却、重试、签名 | 冷却 30–86400 s，重试 0–3，账本 80 条 |
| `monitor/maintenance.py` | 维护窗口解析与判定 | 20 个窗口，单个 ≤ 30 天 |
| `monitor/certificates.py` | 证书剩余天数与分级 | 8 条，90 天窗口 |
| `monitor/report.py` | 自包含离线 HTML | 报告内嵌最多 200 项 |
| `server.py` | 只读 API、静态服务、安全响应头 | 路径限制在 `dashboard/` |

### 2.1 已识别的结构性缺口

这些不是“功能没做”，而是**当前形态下会出问题**的地方，按风险排序：

| # | 缺口 | 现状证据 | 风险 |
|---|---|---|---|
| G1 | 无单实例保护 | 全仓库无 `fcntl` / `msvcrt` / `O_EXCL` 文件锁，只有 `threading.Lock` | 两个进程指向同一 `data/` 会交错追加与轮转，可能丢历史 |
| G2 | 无健康/就绪/指标端点 | `server.py` 只有 `/api/health`，无 `/healthz`、`/readyz`、`/metrics` | 容器与 K8s 无法区分“进程活着”和“采样可用”，也无法被 Prometheus 抓取 |
| G3 | 存储不可查询 | 仅 JSONL + 内存窗口，无 `sqlite3`、无 `schema_version` | 30 天以上留存、按检查/时间段查询都要全量扫描 |
| G4 | 探测类型单一 | `SUPPORTED_TYPES = {"http","tcp","tls","ping"}` | DNS、UDP、gRPC、WebSocket、数据库/Redis/MQ 都覆盖不到 |
| G5 | 无内置认证 | `server.py` 不读取任何 `Authorization` 头 | 只能靠“只听回环”保安全，一旦要分享就得靠反代 |
| G6 | 配置需重启 | 无热加载、无 `SIGHUP` 处理 | 改一个阈值要停服务，采样出现空档 |
| G7 | 告警出口单一 | 只有一种通用 JSON Webhook | Slack / Teams / PagerDuty 需自建转换 |

## 3. 分层演进方向

按“基础设施 → 网络 → 安全 → 云原生 → 中间件 → 数据”分层，每层给出**目标形态**与**可独立交付的有界切片**。

判定标准：一个切片必须能在一轮迭代内完成、能用本地替身测试、失败可回滚。

### 3.1 基础设施与进程模型

**目标形态**：一个 `data/` 目录同时只能被一个采样进程持有；配置变更不需要重启；进程能被 systemd / Windows 服务正确托管。

**切片**

1. 单实例锁：启动时对 `<data-dir>/.sentinel.lock` 取排他锁，失败则打印持有者 PID 并退出码 3。
   - 跨平台：POSIX 用 `fcntl.flock`，Windows 用 `msvcrt.locking`；两者都不可用时退化为 `O_CREAT|O_EXCL` 并记录降级。
   - 验收：同一 `data/` 启动第二个进程必须失败且不写入任何历史行；进程被 kill 后锁可被回收。
2. 配置热加载：`SIGHUP` 或在 `/api/config` 上带 `If-None-Match` 轮询，重新解析 `checks.json`；解析失败保留旧配置并暴露 `config.last_error`。
   - 验收：非法配置不会让运行中的采样停止；成功加载后新阈值在下一轮生效。
3. 服务托管样例：`deploy/systemd/sentinel.service`（`Restart=on-failure`、`NoNewPrivileges`、`ProtectSystem=strict`）与 Windows 计划任务说明。
   - 验收：文档中的 unit 文件可被 `systemd-analyze verify` 通过（无 systemd 环境时标注未验证）。

**不做**：多进程水平扩展、外置任务队列、跨主机采集。

### 3.2 网络探测内核

**目标形态**：探测类型可插拔，每类探测有独立超时与并发预算，任何探测都不能让进程访问未授权网段。

**切片**

1. 探测注册表：把 `run_check` 的 `if/elif` 换成 `PROBES: dict[str, Probe]`，每个 probe 声明 `validate()` 与 `run()`。
   - 验收：新增类型只改一个文件；现有四类的行为与测试完全不变（回归门禁）。
2. `dns` 探测：解析 A/AAAA/CNAME，记录解析耗时、返回条数、首个地址；`NXDOMAIN` 记为 `fail` 而非异常。
3. `udp` 探测：发送固定小载荷并等待响应，只用于明确会回包的协议（如 NTP、DNS over UDP），不做端口扫描。
4. `grpc` / `websocket` 探测：先做**只读健康检查**（gRPC Health Checking Protocol、WS 握手），不做业务调用。
5. 出站策略：`allow_private_targets`（默认 `true`，因为定位是内网）+ `denied_cidrs` 列表；配置校验阶段就拒绝落在 `denied_cidrs` 的目标。
   - 验收：配置里写 `169.254.169.254` 且该网段在 `denied_cidrs` 时，加载直接失败。

**不做**：端口扫描、指纹识别、漏洞探测。这是监控工具，不是扫描器。

### 3.3 安全与访问控制

**目标形态**：默认仍然是“只听回环、无账号”；需要分享时，用**最小机制**满足只读分享，而不是引入用户体系。

**切片**

1. 只读分享令牌：`--share-token-env SENTINEL_SHARE_TOKEN`，仅对 `GET /api/status|/api/history|/api/trends|/api/certificates|/api/maintenance` 与静态页生效；`POST /api/refresh` 与 `/api/config` 始终要求本机。
   - 令牌用 `hmac.compare_digest` 比较，永不写入日志、API 响应或报告。
   - 验收：错令牌返回 `401` + `WWW-Authenticate`；正确令牌可读但不可刷新；未配置令牌时行为与今天完全一致。
2. 反向代理样例：`deploy/nginx/sentinel.conf`（basic auth + TLS + `X-Forwarded-Proto`）与 `deploy/caddy/Caddyfile`（`basic_auth` + 自动 HTTPS）。
   - 样例里只出现占位符，不出现任何真实域名或口令。
3. 审计事件：记录“谁在何时读取了哪个 API”，只记时间、路径、结果码与来源是否回环，不记令牌。
4. 秘密处理收口：所有 `*_env` 字段在 `/api/config` 中只回显“已配置/未配置”。

**不做**：多用户、RBAC、OIDC、会话管理。

### 3.4 云原生

**目标形态**：一个镜像 + 一份 Helm chart，能在 K8s 里被正确探活、限流、抓指标。

**切片**

1. 端点拆分：
   - `/healthz`：进程活着（不触发采样）。
   - `/readyz`：配置已加载 + 历史目录可写 + 调度器在跑；任一不满足返回 `503` 并说明原因。
   - `/metrics`：Prometheus 文本格式，暴露 `sentinel_check_up`、`sentinel_check_latency_ms`、`sentinel_check_status{status}`、`sentinel_history_bytes`、`sentinel_alert_deliveries_total{result}`。
   - 验收：`/metrics` 输出可被 `promtool check metrics` 解析（无该工具时用本地解析器校验格式）。
2. `deploy/k8s/`：Deployment（`readinessProbe: /readyz`、`livenessProbe: /healthz`、`resources`、`securityContext.readOnlyRootFilesystem`）、Service、PVC、ConfigMap（`checks.json`）、Secret（webhook env）。
3. `deploy/helm/sentinel/`：把上述资源模板化，`values.yaml` 只暴露端口、镜像、资源、现有 PVC/Secret 名。
4. 镜像发布：CI 增加 `docker build` 冒烟（不推送），并在文档中给出 `docker pull` 的可选路径。

**不做**：Operator、CRD、多副本共享存储、Service Mesh 集成。

### 3.5 中间件与告警出口

**目标形态**：告警出口可插拔，重试与去重策略统一，抑制语义可叠加。

**切片**

1. Provider 适配器：`monitor/notifiers/`，先做 `generic_webhook`（现有行为，保持兼容）、`slack`、`teams`、`pagerduty`。
   - 每个适配器只负责“把事件映射成该平台的 payload”，重试/冷却/账本仍由 `AlertDispatcher` 统一负责。
   - 验收：每个 provider 都用本地 HTTP 替身测试，断言 payload 结构与重试行为。
2. 消息模板：可选 `template` 字段，支持 `{{check.name}}`、`{{status}}`、`{{detail}}` 等有限变量；渲染失败回退默认模板并记录原因。
3. 抑制叠加：维护窗口（已有）+ 静默规则（`silences`，按 check/标签 + 时间窗），账本统一记录 `suppressed_by`。
4. 去重键：同一 check + 同一状态在冷却期内只投递一次；跨 provider 共享同一冷却状态。

**不做**：告警升级链、值班表、双向确认。

### 3.6 数据与存储

**目标形态**：短期仍可用 JSONL 跑；当留存或查询需求超出文件能力时，平滑迁到 SQLite，且**不丢历史**。

**切片**

1. 立即做（低成本）：`history.jsonl` 增加 `schema_version` 字段；读取端对未知版本只做降级解析。
2. SQLite 双写：`HistoryStore` 抽象为 `HistoryBackend`，新增 `SqliteBackend`（WAL、`synchronous=NORMAL`、单写连接）。
   - 表：`runs(run_id, started_at, duration_ms, summary_json)`、`checks(run_id, check_id, status, latency_ms, metrics_json)`。
   - 迁移：启动时若存在 `history.jsonl` 且库为空，按行导入一次并写 `meta.migrated_at`；不删除原文件。
3. 查询下推：`/api/trends` 与 `/api/history` 改为走后端接口；SQLite 下用索引 `(check_id, started_at)`。
4. 留存策略：按天数（默认 30 天）删除，与文件模式的体积上限并存，二选一由配置决定。
5. 一致性校验：`/api/health` 暴露 `storage.backend`、`storage.rows`、`storage.oldest_sample_at`。

**触发条件**（满足任一才启动 SQLite 工作）：

- 需要 > 30 天留存；
- 单机检查数 > 200 或采样间隔 < 30 s，导致轮转过于频繁；
- 需要在页面上按任意时间段查询。

**不做**：分布式数据库、时序库（Prometheus/ClickHouse）内置存储。

## 4. 版本序列（建议）

每个版本一个主要问题，可独立合并与回滚。

| 版本 | 主题 | 主要交付 | 为什么排在这里 |
|---|---|---|---|
| `v0.11` | 单实例与运行时可观测 | 文件锁、`/healthz` `/readyz` `/metrics`、systemd 样例 | 先消除数据损坏风险（G1），再谈扩展 |
| `v0.12` | 只读分享与反代鉴权 | 分享令牌、Nginx/Caddy 样例、审计事件 | 解决了“能不能安全地给别人看” |
| `v0.13` | 存储演进 | `schema_version`、`HistoryBackend` 抽象、SQLite 双写与迁移 | 有查询/留存需求时才做，避免过早复杂化 |
| `v0.14` | 探测内核扩展 | 探测注册表、`dns`、`udp`、gRPC/WS 健康检查、出站 CIDR 策略 | 类型扩展依赖注册表，先重构再加类型 |
| `v0.15` | 告警出口矩阵 | Provider 适配器、模板、静默规则、统一去重 | 依赖维护窗口的抑制语义，已具备 |
| `v0.16` | 云原生交付 | K8s manifests、Helm chart、镜像构建冒烟 | 需要 `/readyz` 与指标先就位 |

顺序理由：**数据安全 → 访问边界 → 存储能力 → 能力扩展 → 交付形态**。任何一步都不应让前一步的验收失效。

## 5. 每轮迭代的验收模板

无论做哪一层，提交前必须能回答：

1. 这个改动对应哪个缺口编号（G1–G7）？
2. 新增/修改了哪些上限？超限行为是什么？
3. 失败路径如何被测试覆盖（本地替身，不依赖公网）？
4. `/api/health` 或页面是否如实反映了新状态？
5. 回滚方式是什么（配置开关 / revert 提交 / 保留旧文件）？

缺少任一项，就不进入提交。

## 6. 明确不做

- 不做 SaaS 控制台，不把账号体系作为默认路径；
- 不执行用户提供的 shell 命令，不做任意文件读写；
- 不把探测能力包装成“全量安全扫描”；
- 不自动创建 tag、GitHub Release 或生产部署；
- 不为了“像 Uptime Kuma”而引入 Vue / Socket.IO / 关系库依赖。
