# Sentinel Roadmap

当前版本：`0.11.0`（2026-10-21）

## 目标

把 Sentinel 做成**自托管的综合运维监控内核**：在同一套证据模型下覆盖
主机、网络、数据库、中间件、容器 / K8s、AIoT 与安全基线，对标 Uptime Kuma 的
“一屏看清 + 状态迁移即告警”闭环体验，并从“网站存活探测”推进到“多域运维监控”。

它同时保持四条自我限制：单机自托管、运行时零第三方依赖、只展示测到的事实、一切行为有界。
多域覆盖靠**统一探测契约（域 + 探测 + 断言）**实现，而不是靠堆集成或放宽上限。

## 产品原则

1. **只展示测到的事实**：不伪造成功率，不把演示数据混入真实结果。
2. **证据优先**：每个状态都能追溯到延迟、状态码、证书天数或错误原因。
3. **本地优先**：默认只监听回环地址，零第三方运行时依赖。
4. **有界行为**：超时、重试、历史条数与报告体积都有上限。
5. **最小可审计**：标准库实现，拒绝任意命令执行与任意文件读写。

多域之后新增一条执行要求：任何新指标必须同时具备真实来源、断言语义、
缺失时渲染 `--`、`/metrics` 标签与页面视图，缺任一项不算完成。

## 已完成

### v0.1 基线

- ICMP / TCP / TLS / HTTP 四类检测
- 实时看板、最近历史、健康评分
- GitHub Actions、Docker、Windows 自启动

### v0.2 可读性

- 业务分组与分组视图
- 自包含离线 HTML 报告，URL 脱敏与证据边界

### v0.3 可信度

- 受限重试（0–2 次），记录尝试次数与恢复标记

### v0.4 可交付性

- 报告中的重试证据与 `0` 值渲染修复
- `?force=1` 真正绕过 8 秒缓存
- 版本化 `User-Agent` / `Server` 头与 `--version`
- 介绍页、README、截图、演示替身与维护文档

### v0.5 观测上下文

- 每轮历史保存有界的逐项 `id / status / latency_ms` 精简证据
- 每项检查展示最近 40 轮 heartbeat、可用率与平均延迟
- 名称、目标、分组与标签搜索，以及 `ok / warn / fail` 筛选
- 仅由真实相邻采样生成 Important Events 状态变化
- 旧 JSONL 缺少逐项记录时安全降级，不推测历史
- 单配置最多 200 项检查，限制快照与历史放大

### v0.6 自动化与告警

- [x] 后台持续采样，不依赖浏览器保持打开
- [x] 通用 JSON Webhook 与可选 HMAC-SHA256 签名
- [x] 按状态迁移触发，带冷却窗口与去重
- [x] 故障、降级、恢复事件与有界重试
- [x] 投递结果持久化、API 与页面展示，并移除 Webhook 秘密
- [x] 本地 HTTP 替身测试，不依赖公网
- [x] 可下载源码包、安装入口、Demo 流程与更新后的介绍页

### v0.7 长期趋势

- [x] 按真实 UTC 日聚合有界可用率
- [x] 使用固定延迟桶计算 p50 / p95
- [x] 缺失日期不补造，只显示有采样的天数
- [x] `/api/trends?days=1..30` 有界读取
- [x] 看板新增 7 天长期趋势面板与数据来源提示
- [x] 新增趋势聚合、服务边界、集成与 UI 契约测试

### v0.8 证书到期日历

- [x] 从真实 TLS 握手返回的 `expires_at` 计算剩余天数
- [x] 按 `tls_warn_days` / `tls_fail_days` 分级，并统计过期 / 紧急 / 预警 / 有效
- [x] `/api/certificates` 有界输出，最多 8 条、窗口 90 天
- [x] 看板新增证书到期日历面板，展示到期日、CN 与是否验证证书链
- [x] 握手失败、非 TLS 检查与畸形指标直接跳过，不推测到期时间

### v0.9 历史归档与体积上限

- [x] `history.jsonl` 单文件 4 MiB 上限与 2 份归档轮转
- [x] 加载时最多读取 5000 行，内存窗口默认 240 轮
- [x] `/api/health` 与 `automation.retention` 暴露真实占用与上限
- [x] 看板展示历史占用、归档数量与“已截断”状态
- [x] 启动时把超限或畸形历史压缩到最新完整行，不整体信任
- [x] 轮转前后都校验路径位于数据目录内

### v0.10 计划维护窗口

- [x] `maintenance_windows` 有界列表：最多 20 个窗口、单个最长 30 天
- [x] 时间必须带显式时区偏移，拒绝无偏移的本地时间
- [x] 按检查范围抑制 Webhook，未覆盖的检查仍正常告警
- [x] 抑制原因（窗口名称）写入告警账本，且不启动冷却窗口
- [x] `GET /api/maintenance` 与 `automation.maintenance` 暴露进行中与即将开始的窗口
- [x] 看板维护面板展示状态、覆盖范围、剩余时间与抑制开关
- [x] `check_ids` 引用不存在的检查时配置加载失败

## 开发计划

完整分层论证、缺口证据与每域可行性见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。
本节只保留可排期的视图。

### 三个阶段的逻辑

```text
Phase A 内核    让“多域”成为可能：进程模型 · 探测契约 · 断言层 · 凭据 · 范围 · 存储 · 出口
      ↓         （不新增任何监控域）
Phase B 域扩展  逐域落地：网络 → 安全 → 主机 → 数据库 → 中间件 → 容器/K8s → AIoT
      ↓         （每域一个版本，只交付有界的首个切片）
Phase C 综合化  多实例只读聚合 · 依赖拓扑 · SLO 与错误预算（按需启动）
```

### 结构性缺口

G1–G7 是当前形态就会出问题的地方；G8–G12 是综合监控目标暴露出的架构缺口。
每条都要能在代码里复核。

| 编号 | 缺口 | 证据 | 关闭版本 |
|---|---|---|---|
| G1 | 无单实例锁，两进程共享 `data/` 会交错写入 | 全仓库无 `fcntl` / `msvcrt` / `O_EXCL` | `v0.11` |
| G2 | 无 `/healthz` `/readyz` `/metrics` | `server.py` 仅有 `/api/health` | `v0.11` |
| G3 | 仅 JSONL，无索引、无 `schema_version` | `monitor/history.py` 全文件扫描 | `v0.15` |
| G4 | 探测类型固定四类 | `SUPPORTED_TYPES` 在 `monitor/config.py:15` | `v0.12` |
| G5 | 无内置认证，分享依赖反代 | `server.py` 不读取 `Authorization` | `v0.16` |
| G6 | 配置变更需重启 | 无热加载、无 `SIGHUP` 处理 | `v0.16` |
| G7 | 告警出口只有通用 Webhook | `monitor/alerts.py` 单一 payload | `v0.16` |
| G8 | 无凭据作用域模型 | 只有 `webhook_url_env` / `signing_secret_env` 两个硬编码特例 | `v0.14` |
| G9 | 无断言层，判定只有延迟/状态码/证书天数 | `monitor/checks.py` 的 `_latency_status` 等 | `v0.13` |
| G10 | 无域维度，只有自由文本 `group` | `monitor/config.py` 的 `group: str = "未分组"` | `v0.12` |
| G11 | 无主机资源采集 | `monitor/` 内无 `/proc` / `ctypes` / `shutil.disk_usage` 调用 | `v0.22` |
| G12 | 无授权范围声明，SSRF 面无护栏 | 目标只有格式校验，无 CIDR 归属判断 | `v0.14` |

### Phase A：内核（v0.11–v0.17）

#### v0.11 单实例与运行时可观测

- [ ] `data/.sentinel.lock` 排他锁：POSIX `flock` / Windows `msvcrt` / `O_EXCL` 降级
- [ ] 第二个进程启动失败并输出持有者 PID，退出码 3，不写入任何历史
- [ ] `GET /healthz`（进程存活，不触发采样）
- [ ] `GET /readyz`（配置已加载 + 数据目录可写 + 调度器在跑），未就绪返回 `503` 与原因
- [ ] `GET /metrics` Prometheus 文本格式，标签只允许 `check_id` / `domain` / `status`
- [ ] `deploy/systemd/sentinel.service` 样例（`Restart=on-failure`、`ProtectSystem=strict`）

#### v0.12 探测契约与域维度

- [ ] `PROBES` 注册表替代 `run_check` 的 `if/elif`，现有四类行为与测试零回归
- [ ] 每个 probe 声明 `validate()` 与 `run()`，`Result` 必须带结构化 `metrics`
- [ ] 引入 `domain` 枚举，默认 `network` 保持向后兼容，写入配置 / 快照 / 历史 / 指标标签
- [ ] 每域独立并发预算 `domain_budget`，慢域不拖垮快域
- [ ] 显式区分 `prober` / `reader`，`reader` 必须声明 `requires_secret`

#### v0.13 断言层

- [ ] 配置新增可选 `assertions`：`{ metric, op, warn, fail }`，缺省沿用今天的行为
- [ ] `op` 受限集合：`== != > >= < <= in exists missing`，字符串只支持字面量与前缀，不接受任意正则
- [ ] 判定结果与实测值一起写入历史，页面详情展示“实测 X / 判定依据 Y”
- [ ] 指标缺失时结果为 `unknown` 并渲染 `--`，不推断、不默认为 ok
- [ ] 断言求值单元测试覆盖缺失指标、类型不符、边界值

#### v0.14 凭据作用域与授权范围

- [ ] `secret_ref`：`{"env": "NAME"}` 或 `{"file": "name"}`，`file` 必须解析到 `<data-dir>/secrets/` 内
- [ ] `webhook_url_env` / `signing_secret_env` 保留为兼容别名，内部归一
- [ ] `/api/config` 只回显“已配置 / 未配置 / 来源类型”，缺失凭据不回退明文
- [ ] 配置顶层 `scope`：`allow_private` / `authorized_cidrs` / `denied_cidrs`，越界在发包前拒绝
- [ ] 默认拒绝云元数据端点，覆盖行为写入 `/api/config` 供审计

#### v0.15 存储演进

- [ ] `history.jsonl` 增加 `schema_version`，未知版本降级解析
- [ ] 抽出 `HistoryBackend`，新增 `SqliteBackend`（WAL、`synchronous=NORMAL`、单写连接）
- [ ] 表 `runs` / `checks`（含 `domain` 列）与索引 `(check_id, started_at)`
- [ ] 首次启动从 JSONL 单向导入，保留原文件，写 `meta.migrated_at`
- [ ] 按天留存（默认 30 天）与文件体积上限二选一，由配置决定
- [ ] `/api/health` 暴露 `storage.backend` / `rows` / `oldest_sample_at`

#### v0.16 访问控制、告警出口与热加载

- [ ] 只读分享令牌（`--share-token-env`），仅放行只读 `GET`；刷新与配置读取始终要求本机
- [ ] 令牌使用 `hmac.compare_digest`，不进入日志 / API / 报告
- [ ] 反向代理鉴权样例（Nginx / Caddy），只含占位符
- [ ] 读取审计事件：时间、路径、结果码、是否回环，不记录令牌
- [ ] `monitor/notifiers/` 适配器：`generic_webhook`（兼容现有）、`slack`、`teams`、`pagerduty`
- [ ] 静默规则与维护窗口叠加，账本统一记录 `suppressed_by`
- [ ] 配置热加载：`SIGHUP` 或 `ETag` 轮询，解析失败保留旧配置并暴露 `config.last_error`

#### v0.17 云原生交付

- [ ] `deploy/k8s/`：Deployment（`/readyz` + `/healthz` 探针、resources、只读根文件系统）、Service、PVC、ConfigMap、Secret
- [ ] `deploy/helm/sentinel/`：模板化上述资源，`values.yaml` 只暴露端口、镜像、资源、既有 PVC/Secret 名
- [ ] CI 增加 `docker build` 冒烟（不推送镜像）

### Phase B：域扩展（v0.20–v0.26）

每域一个版本，只交付有界的首个切片。排序依据：复用度 → 刚需程度 → 前置依赖。

#### v0.20 `network` 网络

- [ ] `dns` 探测：标准库自写报文解析 A / AAAA / CNAME，记录解析耗时与返回条数，不依赖 `dig`
- [ ] `NXDOMAIN` 记为 `fail` 而非异常
- [ ] `udp` 探测：只用于明确会回包的协议（NTP、DNS over UDP），不做端口扫描
- [ ] 现有 TCP / TLS / HTTP 接入断言层

#### v0.21 `security` 安全基线（防御性）

- [ ] TLS 协议版本与套件姿态核查，输出实测支持集合
- [ ] HTTP 安全响应头核查（CSP、`Strict-Transport-Security`、`X-Content-Type-Options` 等）
- [ ] 授权端口清单漂移比对：以声明的清单为基线，只报告差异
- [ ] 证书链与到期（复用 v0.8）接入断言层
- [ ] 文档明确标注：无漏洞库、无 PoC、无爆破、无资产测绘

#### v0.22 `host` 主机

- [ ] Linux：`/proc/stat`、`/proc/meminfo`、`/proc/loadavg`
- [ ] Windows：`ctypes` 调 `GetSystemTimes` / `GlobalMemoryStatusEx`
- [ ] 跨平台磁盘用量 `shutil.disk_usage`，按挂载点声明式采集
- [ ] 断言驱动告警：CPU 占用、内存可用比、磁盘剩余、负载 / 核数比
- [ ] 平台不支持时该检查单独 `fail` 并说明原因，不影响其它检查

#### v0.23 `database` 数据库

- [ ] Redis：RESP 协议 `PING` / `INFO`，采集 `uptime_seconds`、`used_memory`、`evicted_keys`、`connected_clients`
- [ ] MySQL：握手 + `SELECT 1` 健康查询
- [ ] PostgreSQL：startup message + simple query 健康查询
- [ ] 凭据一律走 `secret_ref`；只允许只读健康语句，拒绝任意 SQL 与数据读取

#### v0.24 `middleware` 中间件

- [ ] HTTP 型先行：Elasticsearch `_cluster/health`、Nacos、Consul
- [ ] Kafka：仅 `ApiVersions` + 元数据请求，采集 broker 数与控制器可用性
- [ ] AMQP：仅 `Connection.Start` 握手级检测
- [ ] 不消费消息、不执行管理写操作

#### v0.25 `container` 容器 / Kubernetes

- [ ] kubelet `:10250/pods` 只读采集（凭据走 `secret_ref`）
- [ ] API Server 只读 `GET`：`NotReady` 节点数、Pod `restart_count` 增量
- [ ] `/stats/summary` 资源用量接入断言层
- [ ] 不做 `exec` / `logs` 流，不做任何写操作，不做 Operator / CRD

#### v0.26 `iot` AIoT

- [ ] MQTT：`CONNECT` / `PINGREQ`、保留消息读取、遗嘱（LWT）检测
- [ ] Modbus TCP：**只读功能码 0x01 / 0x03**，写功能码在配置校验阶段直接拒绝
- [ ] CoAP：UDP 报文级探测
- [ ] 不下发设备指令、不做固件 OTA、不做设备控制

### Phase C：综合化（按需启动，不预先承诺）

- [ ] `v0.30` 只读多实例聚合：拉取远端实例的只读令牌视图形成全局看板，不做中心写控与数据回传
- [ ] `v0.31` 依赖与拓扑视图：由 `group` / `tags` / 断言推导，只展示声明过的关系，不自动测绘
- [ ] `v0.32` SLO 与错误预算：跨检查时间窗口计算，前置条件是 v0.15 已完成

### 规模与上限的立场

多域会不断有人要求放宽上限，这里预先回答：**不放宽**。

- 单实例 200 项检查、采样间隔下限 10 s 是刻意的设计边界，保证快照体积、轮转与页面可读性可预测；
- 超出 200 项说明需要多实例分工（按机房 / 按业务线），而不是一个更大的单实例；
- 需要秒级精度属于指标系统（Prometheus 一类）的目标形态，不是 Sentinel 的；
- 多实例汇总由 Phase C 的只读聚合解决，不靠调大上限硬撑。

## 明确不做

- 不做 SaaS 控制台，不引入账号体系作为默认路径；
- 不执行用户提供的 shell 命令，不做任意文件读写，不动态加载任意插件代码；
- 不把探测能力包装成“全量安全扫描”：无漏洞库、无 PoC、无爆破、无端口扫描、无资产测绘；
- 不做 Agent 分发与中心写控，不做数据库任意 SQL 与数据读取，不做 K8s 写操作，不做设备指令下发；
- 不自动创建 tag、GitHub Release 或生产部署；
- 不为了“像 Uptime Kuma”而引入 Vue / Socket.IO / 外部关系库；
- 不为了“覆盖更多”而放宽有界原则（200 项、10 s 间隔、体积上限）。

## 优先级

`P0` 安全 / 数据丢失 / 核心失效 → `P1` 高价值缺陷与测试缺口 → `P2` 体验与性能 → `P3` 打磨。

每次迭代只解决一个主要问题，并附可复现的测试证据。
