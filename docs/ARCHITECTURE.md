# Sentinel 架构与开发方向

本文回答两个问题：**现在是什么形态**，以及**接下来往哪里长**。

它只描述仓库中真实存在的实现；未实现的能力一律标注为“缺口”或“规划”，不做能力包装。

当前版本：`0.10.0`（2026-10-21）

## 1. 目标与定位

**目标**：把 Sentinel 做成**自托管的综合运维监控内核**——在同一套证据模型下覆盖
主机、网络、数据库、中间件、容器 / K8s、AIoT 与安全基线，对标 Uptime Kuma 的
“一屏看清 + 状态迁移即告警”闭环体验，并把它从“网站存活探测”推进到“多域运维监控”。

**定位不变的部分**（这是它与 Uptime Kuma / Prometheus / Zabbix 的差异所在，也是所有约束的来源）：

- 单机自托管，默认只听 `127.0.0.1`，不需要数据库服务、不需要外部依赖；
- 运行时零第三方 Python 依赖，只用标准库；
- 只展示测到的事实，证据可回溯；
- 一切行为有界：上限、超时、体积、条数都在配置校验阶段钉死。

**因此必须承认的取舍**：零依赖 + 有界，意味着 Sentinel 不会拥有 Agent 分发、
任意 SQL、K8s 写操作、寄存器下发、漏洞库匹配这类能力。多域覆盖靠**统一的探测契约**
实现，而不是靠堆集成。第 5 节逐域给出可行性与不做项。

### 1.1 五条不变式

| 不变式 | 具体含义 | 多域之后如何守住 |
|---|---|---|
| 只展示测到的事实 | 没采样的日期不补造，没握手的证书不显示到期日 | 新域的每个指标都必须来自真实响应，缺数据渲染为 `--` |
| 证据优先 | 每个状态可回溯到延迟、状态码、错误类别 | 断言结果同时保存“实测值 + 判定依据” |
| 本地优先 | 默认只听回环，零第三方运行时依赖 | 新协议一律用标准库自写报文，不引入客户端 SDK |
| 有界行为 | 检查数、超时、体积、条数都有硬上限 | 单实例仍限 200 项；规模靠多实例 + 只读聚合，不放宽上限 |
| 最小可审计 | 不执行任意命令，不读写任意路径 | 凭据只走引用层；reader 型探测只允许只读语义 |

### 1.2 从“看板”到“内核”需要补的三个抽象

当前实现只有 `type`（四类）+ 阈值（延迟 / 状态码 / 证书天数）。要承载七个域，
必须补上三层抽象，否则每加一个域都要改一遍 `checks.py`、`runner.py` 与看板：

```text
Domain（域）      host | network | database | middleware | container | iot | security
                  └─ 决定：默认阈值、分组、凭据作用域、告警语义、页面视图
Probe（探测/采集） prober = 黑盒远程探测，无需凭据   → tcp / tls / http / dns / udp
                  reader = 只读拉取，需凭据引用      → k8s / db / mq / host metrics
                  └─ 决定：怎么拿到结构化指标
Assertion（断言） 对指标做声明式判定，产出 ok / warn / fail
                  └─ 决定：什么算异常（不再只有“延迟超阈值”）
```

`Assertion` 是“存活探测”与“综合监控”的分水岭。没有它，`redis` 探测只能回答
“端口通不通”；有了它，才能回答“`used_memory` 是否超过 `maxmemory` 的 80%”。

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
   └────────────────────┘                            └───────────────────┘
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

## 3. 结构性缺口

G1–G7 是**当前形态下就会出问题**的地方；G8–G12 是**新目标暴露出来的架构缺口**——
不补上它们，多域覆盖无法落地。每条都要能在代码里复核。

| # | 缺口 | 现状证据 | 风险 / 后果 |
|---|---|---|---|
| G1 | 无单实例保护 | 全仓库无 `fcntl` / `msvcrt` / `O_EXCL`，只有 `threading.Lock` | 两进程指向同一 `data/` 会交错追加与轮转，可能丢历史 |
| G2 | 无健康 / 就绪 / 指标端点 | `server.py` 只有 `/api/health` | 容器与 K8s 无法区分“进程活着”和“采样可用”，无法被 Prometheus 抓取 |
| G3 | 存储不可查询 | 仅 JSONL + 内存窗口，无 `sqlite3`、无 `schema_version` | 多域多指标下全文件扫描不可接受，> 30 天留存做不到 |
| G4 | 探测类型固定四类 | `SUPPORTED_TYPES = {"http","tcp","tls","ping"}`（`monitor/config.py`） | 新域只能改 `run_check` 的 `if/elif`，无法扩展；v0.12 起由 `PROBES` 注册表承担分派 |
| G5 | 无内置认证 | `server.py` 不读取任何 `Authorization` 头 | 一旦要给别人看就得完全依赖反向代理 |
| G6 | 配置变更需重启 | 无热加载、无 `SIGHUP` 处理 | 改阈值要停服务，采样出现空档 |
| G7 | 告警出口单一 | `monitor/alerts.py` 只有一种通用 JSON payload | 每个平台都要自建转换层 |
| G8 | 无凭据作用域模型 | 只有 `webhook_url_env` / `signing_secret_env` 两个硬编码特例 | DB / K8s / MQTT 都要凭据，现无统一、可审计、不泄漏的引用方式 |
| G9 | 无断言层 | 判定只有延迟阈值、HTTP 状态码集合、证书天数 | 新域只能回答“通不通”，回答不了“对不对 / 满不满 / 漂移没漂移” |
| G10 | 无域维度 | 只有自由文本 `group`（默认“未分组”）与 `tags` | 阈值、告警语义、页面视图无法按域差异化；v0.12 起已有独立 `domain` 字段贯通配置/快照/历史/指标 |
| G11 | 无主机资源采集 | `monitor/` 内无 `/proc`、`os.statvfs`、`ctypes`、`getloadavg` 任何调用 | “主机监控”目前只有 ICMP 可达性，没有 CPU / 内存 / 磁盘 |
| G12 | 无授权范围声明 | 目标只有格式校验，无 CIDR 归属判断 | 安全域会诱导越界探测；SSRF 面（如 `169.254.169.254`）无护栏 |

## 4. 内核层演进（Phase A）

Phase A 不新增任何监控域，只做一件事：**让“多域”成为可能**。
判定标准不变：一个切片必须能在一轮迭代内完成、能用本地替身测试、失败可回滚。

### 4.1 进程与运行时（G1 / G2 / G6）

**目标形态**：一个 `data/` 同时只被一个采样进程持有；配置变更不需要重启；
进程能被 systemd / Windows 服务正确托管；外部编排能区分“活着”和“可用”。

**切片**

1. 单实例锁：启动时对 `<data-dir>/.sentinel.lock` 取排他锁，失败则打印持有者 PID 并以退出码 3 退出。
   - 跨平台：POSIX 用 `fcntl.flock`，Windows 用 `msvcrt.locking`；两者都不可用时退化为 `O_CREAT|O_EXCL` 并记录降级。
   - 验收：同一 `data/` 启动第二个进程必须失败且不写入任何历史行；进程被 kill 后锁可回收。
2. 端点拆分：`/healthz`（进程存活，不触发采样）、`/readyz`（配置已加载 + 数据目录可写 + 调度器在跑，
   任一不满足返回 `503` 并说明原因）、`/metrics`（Prometheus 文本格式）。
   - `/metrics` 至少含 `sentinel_check_up`、`sentinel_check_latency_ms`、`sentinel_check_status{status}`、
     `sentinel_history_bytes`、`sentinel_alert_deliveries_total{result}`；标签只允许 `check_id`、`domain`、`status`。
   - 验收：`/metrics` 可被本地解析器逐行校验（不依赖 `promtool` 是否安装）。
3. 配置热加载：`SIGHUP` 或 `/api/config` 带 `ETag` 轮询触发重解析；失败保留旧配置并暴露 `config.last_error`。
   - 验收：非法配置不会让运行中的采样停止；成功加载后新阈值在下一轮生效。
4. 服务托管样例：`deploy/systemd/sentinel.service`（`Restart=on-failure`、`NoNewPrivileges`、`ProtectSystem=strict`）
   与 Windows 计划任务说明。

**不做**：多进程水平扩展、外置任务队列、跨主机 Agent。

### 4.2 探测契约与域维度（G4 / G10）

**当前形态（v0.12 已落地）**：`PROBES` 注册表 + `domain` 字段，新增一种探测不改 `runner.py`。

**切片**

1. 把 `run_check` 的 `if/elif` 换成 `PROBES: dict[str, Probe]`，每个 probe 声明
   `validate(raw) -> Spec` 与 `run(spec, thresholds) -> Result`；`Result` 必须带结构化 `metrics`。
   - 验收：现有四类行为与全部既有测试零回归（这是本切片的通过门槛）。
2. ✅ 引入 `domain` 枚举（`network` 为默认值以保持向后兼容），写入配置、快照、历史、告警 payload、离线报告与 `/metrics` 标签。
3. ✅ 每域独立并发预算：`domain_budget`（如 `database: 2`），每域一个线程池，防止慢域拖垮快域。
4. ✅ 显式区分 `prober` / `reader`：`reader` 型必须声明 `requires_secret`，
   非法声明在导入期直接报错。缺凭据时的单检查失败语义留待 v0.14 的 `secret_ref`。

**不做**：插件动态加载任意代码、第三方驱动。

### 4.3 断言层（G9）

**目标形态**：判定与采集解耦，任何指标都能声明式判定。

**切片**

1. 配置新增可选 `assertions`（缺省即沿用今天的行为）：

```json
{
  "id": "redis-main",
  "domain": "database",
  "type": "redis",
  "assertions": [
    { "metric": "uptime_seconds", "op": ">=", "warn": 3600 },
    { "metric": "evicted_keys", "op": "==", "fail": 1 }
  ]
}
```

2. `op` 只允许受限集合：`== != > >= < <= in exists missing`；字符串比较只支持字面量与前缀，
   **不接受任意正则**，避免 ReDoS 与配置注入。
3. 判定结果与实测值一起写入历史，页面详情展示“实测 X / 判定依据 Y”。
4. 指标缺失时结果为 `unknown` 并渲染为 `--`，**不推断、不默认为 ok**。

**验收**：断言求值的单元测试覆盖缺失指标、类型不符、边界值；
UI 契约测试要求详情区能显示实测值与判定依据。

**当前形态（v0.13 已落地）**：每项检查可选最多 8 条 `assertions`，
`op` 固定为 `== != > >= < <= in exists missing`，`in` 最多 16 个字面量；
字符串只做字面量或前缀匹配，不接受正则和表达式。断言证据（实测值、判定、
依据）进入快照、逐项 heartbeat 和运行历史；缺失指标或类型不符返回 `unknown`，
可用率只基于有明确结论的采样。探测自身失败仍保留 `fail`，不被断言重判。

**不做**：表达式引擎、脚本、跨检查聚合运算（那是 Phase C 的 SLO 议题）。

### 4.4 凭据作用域（G8）

**目标形态**：任何需要凭据的探测都用同一套引用机制，凭据永不落盘、永不进日志与 API。

**切片**

1. 泛化为 `secret_ref`：`{"env": "NAME"}` 或 `{"file": "relative-name"}`；
   `file` 解析后必须位于 `<data-dir>/secrets/` 内，越界即配置错误。
2. 现有 `webhook_url_env` / `signing_secret_env` 保留为兼容别名，内部归一到 `secret_ref`。
3. `/api/config` 只回显“已配置 / 未配置 / 来源类型”，永不回显值；缺失凭据不回退到明文。
4. 启动时逐个 probe 校验其声明的 `secret_ref` 是否存在，结果进入 `/readyz` 与页面。

**不做**：外部 KMS / Vault 对接（只留 `file` 引用点，不承诺集成）、凭据加密存储。

### 4.5 授权范围（G12）

**目标形态**：所有出站探测都在显式声明的授权范围内，越界在**发包之前**被拒绝。

**切片**

1. 配置顶层新增 `scope`：`allow_private`（默认 `true`，因为定位是内网）、
   `authorized_cidrs`（空表示不额外限制）、`denied_cidrs`（优先于 authorized）。
2. 解析目标 IP 后做归属判断；被拒的目标记为 `fail`，原因写 `out of authorized scope`，不发包。
3. 默认内置拒绝 `169.254.169.254/32`、`fd00:ec2::254/128`（云元数据端点）；
   可由显式 `authorized_cidrs` 覆盖，但覆盖行为要写入 `/api/config` 供审计。

**验收**：配置里写 `169.254.169.254` 且未显式授权时加载失败；单元测试断言未发出任何包。

**不做**：把 `scope` 做成“扫描器开关”。范围声明是**护栏**，不是合法性凭证——
探测是否合规仍由操作者负责。

### 4.6 存储（G3）

**定位变化**：在旧路线里 SQLite 是“按需可选”；多域多指标下它变成**必需**——
断言要按指标查询、`/metrics` 要按域聚合、留存要跨 30 天。

**切片**

1. 低成本先行：`history.jsonl` 增加 `schema_version`，读取端对未知版本只做降级解析。
2. `HistoryStore` 抽象为 `HistoryBackend`，新增 `SqliteBackend`（WAL、`synchronous=NORMAL`、单写连接）。
   - 表：`runs(run_id, started_at, duration_ms, summary_json)`、
     `checks(run_id, check_id, domain, status, latency_ms, metrics_json)`，索引 `(check_id, started_at)`。
3. 迁移：启动时若存在 `history.jsonl` 且库为空，按行导入一次并写 `meta.migrated_at`；**不删除原文件**。
4. 留存：按天数（默认 30 天）删除，与文件模式的体积上限并存，二选一由配置决定。
5. `/api/health` 暴露 `storage.backend` / `rows` / `oldest_sample_at`。

**不做**：分布式数据库、内置时序库、自研压缩格式。

### 4.7 访问控制与告警出口（G5 / G7）

1. 只读分享令牌：`--share-token-env`，仅放行只读 `GET`；`POST /api/refresh`、`/api/config`
   始终要求本机。令牌用 `hmac.compare_digest` 比较，不进日志 / API / 报告。
   未配置令牌时行为与今天完全一致。
2. 反向代理样例：`deploy/nginx/sentinel.conf`（basic auth + TLS + `X-Forwarded-Proto`）与
   `deploy/caddy/Caddyfile`（`basic_auth` + 自动 HTTPS），只含占位符。
3. 读取审计：时间、路径、结果码、是否回环来源，不记令牌。
4. Provider 适配器：`monitor/notifiers/`，`generic_webhook`（兼容现状）、`slack`、`teams`、`pagerduty`；
   重试 / 冷却 / 账本仍由 `AlertDispatcher` 统一负责。
5. 抑制叠加：维护窗口（已有）+ 静默规则（按 check / 标签 / 域 + 时间窗），账本统一记 `suppressed_by`。

**不做**：多用户、RBAC、OIDC、告警升级链、值班表。

### 4.8 云原生交付

1. `deploy/k8s/`：Deployment（`/readyz` readiness、`/healthz` liveness、`resources`、
   `securityContext.readOnlyRootFilesystem`）、Service、PVC、ConfigMap（`checks.json`）、Secret（凭据引用）。
2. `deploy/helm/sentinel/`：模板化上述资源，`values.yaml` 只暴露端口、镜像、资源、既有 PVC/Secret 名。
3. CI 增加 `docker build` 冒烟（不推送镜像）。

**注意**：Sentinel 自己跑在 K8s 里 ≠ 能监控 K8s。后者是 Phase B 的 `container` 域。

## 5. 七个监控域（Phase B）

每个域一个版本，每域只交付**有界的首个切片**。可行性一栏是诚实评估：
标准库能不能做、要自己写多少协议代码、哪些坚决不做。

| 域 | stdlib 可行性 | 首个切片做法 | 明确不做 |
|---|---|---|---|
| `network` 网络 | 高 | `dns`（自写报文解析 A/AAAA/CNAME，不依赖 `dig`）、`udp`（只对明确回包的协议）、TCP/TLS/HTTP 增强断言 | 端口扫描、traceroute 测绘、流量分析 |
| `security` 安全基线 | 高（仅防御性） | TLS 协议版本与套件姿态、证书链与到期（已有）、HTTP 安全响应头核查、授权端口清单漂移比对 | 漏洞库匹配、PoC / 利用、爆破、资产测绘、外部扫描 |
| `host` 主机 | 中（平台分裂） | Linux 读 `/proc/stat`、`/proc/meminfo`、`/proc/loadavg` + `shutil.disk_usage`；Windows 用 `ctypes` 调 `GetSystemTimes` / `GlobalMemoryStatusEx` | Agent 分发、进程级明细、cgroup 深度指标 |
| `database` 数据库 | 中 | Redis（RESP：`PING` / `INFO`）→ MySQL（握手 + `SELECT 1`）→ PostgreSQL（startup + simple query），只读健康查询 | 任意 SQL、数据读取、DDL、连接池管理 |
| `middleware` 中间件 | 中 | HTTP 型先行（Elasticsearch `_cluster/health`、Nacos、Consul）；再 Kafka（仅 `ApiVersions` + 元数据）、AMQP（仅 `Connection.Start`） | 消费消息、管理写操作、队列深度以外的业务指标 |
| `container` 容器 / K8s | 高 | kubelet `:10250/pods` 只读、API Server 只读 `GET`（`NotReady` 节点数、Pod `restart_count` 增量）、`/stats/summary` | `exec` / `logs` 流、任何写操作、Operator / CRD |
| `iot` AIoT | 中 | MQTT（`CONNECT` / `PINGREQ` + 保留消息读取 + 遗嘱检测）、Modbus TCP（**只读功能码 0x01 / 0x03**）、CoAP（UDP） | 写寄存器、下发指令、固件 OTA、设备控制 |

**排序理由**：`network` 与 `security` 复用现有 prober 能力，成本最低；
`host` 是运维监控最刚需且缺口最大（G11）；`database` / `middleware` 依赖凭据层（G8）；
`container` 依赖凭据 + 断言；`iot` 协议最杂且写操作风险最高，放最后。

每域交付必须同时包含：probe 实现、默认阈值、断言示例、本地可控替身测试、
页面按域分组视图、`/metrics` 标签、CHANGELOG 与文档。缺任一项不算完成。

## 6. 综合化能力（Phase C）

Phase B 之后 Sentinel 能“看全”，但还看不到“关系”。Phase C 处理这个，且**只在有真实需求时启动**：

- **只读多实例聚合**：一个 Sentinel 拉取 N 个远端实例的只读令牌视图，形成全局看板。
  刻意不做中心写控、不做数据回传，保持“每个实例独立自洽”。
- **依赖与拓扑视图**：由 `group` + `tags` + 断言推导，只展示声明过的关系，不自动测绘。
- **SLO 与错误预算**：跨检查的时间窗口计算（可用性目标、燃尽率）。这是唯一允许出现
  跨检查聚合运算的地方，且必须先有 SQLite。
- **变更关联**：把维护窗口、配置热加载事件、状态迁移放在同一条时间线上。

## 7. 版本序列

每个版本只解决一个主要问题，可独立合并与回滚。

### Phase A 内核（让多域成为可能）

| 版本 | 主题 | 主要交付 | 关闭缺口 |
|---|---|---|---|
| `v0.11` | 单实例与运行时观测 | 文件锁、`/healthz` `/readyz` `/metrics`、systemd 样例 | G1 G2 |
| `v0.12` | 探测契约与域维度 | `PROBES` 注册表、`domain` 字段、每域并发预算、prober/reader 二分 | G4 G10 |
| `v0.13` | 断言层 | `assertions` 配置、受限 `op` 集合、实测值入历史与页面 | G9 |
| `v0.14` | 凭据作用域与授权范围 | `secret_ref`、`scope` / `denied_cidrs`、元数据端点默认拒绝 | G8 G12 |
| `v0.15` | 存储演进 | `schema_version`、`HistoryBackend`、SQLite 双写与迁移、按天留存 | G3 |
| `v0.16` | 访问控制与告警出口 | 分享令牌、反代样例、审计、Provider 适配器、静默叠加、配置热加载 | G5 G6 G7 |
| `v0.17` | 云原生交付 | K8s manifests、Helm chart、`docker build` 冒烟 | — |

### Phase B 域扩展

| 版本 | 域 | 首个切片 |
|---|---|---|
| `v0.20` | `network` | `dns` + `udp` 探测，DNS 报文自写解析 |
| `v0.21` | `security` | TLS 姿态 + HTTP 安全响应头核查 + 授权端口清单漂移 |
| `v0.22` | `host` | CPU / 内存 / 磁盘 / 负载，Linux + Windows 双实现，断言驱动告警 |
| `v0.23` | `database` | Redis → MySQL → PostgreSQL 只读健康探测 |
| `v0.24` | `middleware` | ES / Nacos / Consul（HTTP）→ Kafka / AMQP（握手级） |
| `v0.25` | `container` | kubelet / API Server 只读，节点与 Pod 健康断言 |
| `v0.26` | `iot` | MQTT + Modbus TCP 只读 + CoAP |

### Phase C 综合化（按需启动）

`v0.30` 只读多实例聚合 → `v0.31` 依赖与拓扑视图 → `v0.32` SLO 与错误预算。

**顺序理由**：数据安全 → 抽象契约 → 判定能力 → 凭据与边界 → 存储 → 出口 → 交付形态，
然后才轮到域扩展；任何一步都不应让前一步的验收失效。

## 8. 规模与上限的立场

多域会不断有人要求“放宽 200 项上限”。这里明确回答：**不放宽**。

- 单实例 200 项是刻意的设计边界，它保证快照体积、历史轮转、页面可读性都可预测；
- 一台主机 + 若干中间件 + 若干数据库，200 项够用；
- 超出 200 项说明需要的是**多实例分工**（按机房 / 按业务线），而不是一个更大的单实例；
- 多实例的汇总由 Phase C 的只读聚合解决，而不是靠调大上限硬撑。

同理，采样间隔下限保持 10 s。需要秒级 / 亚秒级精度的场景属于指标系统（Prometheus 一类），
不是 Sentinel 的目标形态；它会诚实地告诉你“这一轮不健康”，而不是给你一条高频曲线。

## 9. 每轮迭代的验收模板

无论做哪一层，提交前必须能回答：

1. 这个改动对应哪个缺口编号（G1–G12）？
2. 新增 / 修改了哪些上限？超限行为是什么？
3. 失败路径如何被测试覆盖（本地替身，不依赖公网）？
4. 新指标是否同时具备：真实来源、断言语义、缺失时渲染 `--`、`/metrics` 标签、页面视图？
5. `/api/health` 或页面是否如实反映新状态？
6. 回滚方式是什么（配置开关 / revert 提交 / 保留旧文件）？

缺少任一项，就不进入提交。

## 10. 明确不做

- 不做 SaaS 控制台，不把账号体系作为默认路径；
- 不执行用户提供的 shell 命令，不做任意文件读写，不动态加载任意插件代码；
- 不把探测能力包装成“全量安全扫描”：无漏洞库、无 PoC、无爆破、无端口扫描、无资产测绘；
- 不做 Agent 分发与中心写控，不做数据库任意 SQL 与数据读取，不做 K8s 写操作，不做设备指令下发；
- 不自动创建 tag、GitHub Release 或生产部署；
- 不为了“像 Uptime Kuma”而引入 Vue / Socket.IO / 外部关系库；
- 不为了“覆盖更多”而放宽有界原则（200 项、10 s 间隔、体积上限）。
