# Sentinel Roadmap

当前版本：`0.10.0`（2026-10-21）

## 产品原则

1. **只展示测到的事实**：不伪造成功率，不把演示数据混入真实结果。
2. **证据优先**：每个状态都能追溯到延迟、状态码、证书天数或错误原因。
3. **本地优先**：默认只监听回环地址，零第三方运行时依赖。
4. **有界行为**：超时、重试、历史条数与报告体积都有上限。
5. **最小可审计**：标准库实现，拒绝任意命令执行与任意文件读写。

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

## 下一阶段

分层方向与每层的“现状 → 缺口 → 目标 → 有界切片 → 验收标准”见
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。下表只保留可排期的版本视图。

### 结构性缺口（先修再扩）

| 编号 | 缺口 | 证据 | 归属版本 |
|---|---|---|---|
| G1 | 无单实例锁，两个进程共享 `data/` 会交错写入 | 全仓库无 `fcntl` / `msvcrt` / `O_EXCL` | `v0.11` |
| G2 | 无 `/healthz` `/readyz` `/metrics` | `server.py` 仅有 `/api/health` | `v0.11` |
| G3 | 仅 JSONL，无索引、无 `schema_version` | `monitor/history.py` 全文件扫描 | `v0.13` |
| G4 | 探测类型固定四类 | `SUPPORTED_TYPES` 在 `monitor/config.py` | `v0.14` |
| G5 | 无内置认证，分享依赖反代 | `server.py` 不读取 `Authorization` | `v0.12` |
| G6 | 配置变更需重启 | 无热加载、无 `SIGHUP` 处理 | `v0.11` 之后 |
| G7 | 告警出口只有通用 Webhook | `monitor/alerts.py` 单一 payload | `v0.15` |

### v0.11 单实例与运行时可观测

- [ ] `data/.sentinel.lock` 排他锁：POSIX `flock` / Windows `msvcrt` / `O_EXCL` 降级
- [ ] 第二个进程启动失败并输出持有者 PID，退出码 3，不写入任何历史
- [ ] `GET /healthz`（进程存活，不触发采样）
- [ ] `GET /readyz`（配置已加载 + 数据目录可写 + 调度器状态），未就绪返回 `503` 与原因
- [ ] `GET /metrics` Prometheus 文本格式：`sentinel_check_up`、`sentinel_check_latency_ms`、`sentinel_history_bytes`、`sentinel_alert_deliveries_total`
- [ ] `deploy/systemd/sentinel.service` 样例（`Restart=on-failure`、`ProtectSystem=strict`）

### v0.12 访问控制

- [ ] 只读分享令牌（`--share-token-env`），仅放行只读 `GET`，`POST /api/refresh` 与 `/api/config` 始终要求本机
- [ ] 令牌使用 `hmac.compare_digest`，不进入日志 / API / 报告
- [ ] 反向代理鉴权配置样例（Nginx / Caddy），只含占位符
- [ ] 读取审计事件：时间、路径、结果码、是否回环，不记录令牌

### v0.13 存储演进

- [ ] `history.jsonl` 增加 `schema_version`，未知版本降级解析
- [ ] 抽出 `HistoryBackend`，新增 `SqliteBackend`（WAL、单写连接）
- [ ] 首次启动从 JSONL 单向导入，保留原文件，写 `meta.migrated_at`
- [ ] `/api/health` 暴露 `storage.backend` / `rows` / `oldest_sample_at`
- [ ] 仅在满足“需要 > 30 天留存 / 检查数 > 200 / 需要任意时间段查询”之一时启动

### v0.14 探测内核扩展

- [ ] 探测注册表替代 `run_check` 的 `if/elif`，现有四类行为不变
- [ ] `dns`：A/AAAA/CNAME、解析耗时、返回条数，`NXDOMAIN` 记为 `fail`
- [ ] `udp`：仅用于明确会回包的协议，不做端口扫描
- [ ] `grpc` / `websocket`：只做健康检查与握手，不做业务调用
- [ ] 出站策略：`denied_cidrs`，配置校验阶段拒绝

### v0.15 告警出口

- [ ] `monitor/notifiers/` 适配器：`generic_webhook`（兼容现有）、`slack`、`teams`、`pagerduty`
- [ ] 有界模板变量，渲染失败回退默认模板并记录原因
- [ ] 静默规则与维护窗口叠加，账本统一记录 `suppressed_by`
- [ ] 去重键跨 provider 共享冷却状态

### v0.16 云原生交付

- [ ] `deploy/k8s/`：Deployment（`/healthz` + `/readyz` 探针、resources、只读根文件系统）、Service、PVC、ConfigMap、Secret
- [ ] `deploy/helm/sentinel/`：模板化上述资源，`values.yaml` 只暴露端口、镜像、资源、既有 PVC/Secret 名
- [ ] CI 增加 `docker build` 冒烟（不推送镜像）

## 明确不做

- 不做 SaaS 控制台，不引入账号体系作为默认路径
- 不执行用户提供的 shell 命令
- 不把探测能力包装成“全量安全扫描”
- 不自动创建 tag、Release 或生产部署

## 优先级

`P0` 安全 / 数据丢失 / 核心失效 → `P1` 高价值缺陷与测试缺口 → `P2` 体验与性能 → `P3` 打磨。

每次迭代只解决一个主要问题，并附可复现的测试证据。
