# Sentinel · 运维健康看板

Sentinel 是一个自托管的轻量监控工作台，用于集中查看已配置目标的可用性、延迟、证书和本机磁盘容量。它从真实采样生成状态、历史与告警；适合希望先在本机或小规模环境中建立基础监控闭环的团队。

**当前状态：开发中。** 已发布版本为 [v0.13.0](VERSION)；本分支还包含未发布的断言、本机磁盘和系统名称解析能力。请以 [变更记录](CHANGELOG.md) 和所在分支代码为准，发布包不包含尚未合入的开发分支功能。

[快速开始](#快速开始) · [监控能力](#监控能力) · [配置](#配置监控) · [安全与运行边界](#安全与运行边界) · [架构](docs/ARCHITECTURE.md) · [路线图](ROADMAP.md)

## 当前已实现

| 检查类型 | 真实观测 | 使用边界 |
| --- | --- | --- |
| `http` | HTTP 状态码、响应耗时 | 目标为完整 HTTP(S) URL；默认验证 TLS 证书 |
| `tcp` | 指定端口的连接与耗时 | TCP 端口可连通不代表应用功能正常 |
| `tls` | TLS 握手、证书到期时间 | 证书结果来自实际握手，默认验证证书 |
| `ping` | 系统 ICMP Echo 检查 | 需要系统 `ping` 命令；失败也可能是网络策略禁止 ICMP |
| `disk` | 本机路径所在文件系统的容量 | 开发分支能力；无容量断言时为 `unknown` |
| `dns` | 运行主机的系统名称解析与耗时 | 开发分支能力；可能命中 hosts 或缓存，并非指定 DNS 服务器检查 |

一个检查可以配置域、分组、标签、超时、重试和声明式断言。结果在工作台中提供搜索、筛选、逐项状态时间线、最近变化和证据；后台调度可按配置周期采样。Webhook 支持状态变化通知、冷却、重试、签名与投递账本，维护窗口可抑制告警而继续采样。

**尚未实现：**数据库和中间件专用指标采集、Kubernetes 对象/集群状态、远程主机资源指标和自动发现。`domain` 只是分类字段，不能把 TCP 检查归类为数据库后就当作数据库指标监控。能力规划见 [重构计划](docs/REBUILD_PLAN.md)。

## 快速开始

需要 Python 3.11 或更高版本；运行时仅使用 Python 标准库。仓库默认的 `checks.json` 含公网示例目标，启动前请检查并替换成你有权访问的目标。以下示例只检查本机 HTTP 服务：

1. 新建 `checks.local.json`：

```json
{
  "version": 1,
  "monitor_interval_seconds": 60,
  "checks": [
    {
      "id": "sentinel-health",
      "name": "Sentinel 健康接口",
      "type": "http",
      "target": "http://127.0.0.1:8080/api/health",
      "expected_status": [200],
      "timeout_seconds": 3
    }
  ]
}
```

2. 在仓库根目录启动：

```powershell
python server.py --config checks.local.json --data-dir data/local
```

3. 打开 [http://127.0.0.1:8080](http://127.0.0.1:8080)。服务进程运行时后台采样；页面每 10 秒读取状态。刷新按钮可以请求新一轮检查。

`--no-scheduler` 可关闭后台定时任务，但页面和 API 请求仍可能按需触发采样。配置更改需重启进程；默认监听 `127.0.0.1:8080`。检查 CLI 参数：

```powershell
python server.py --help
python server.py --version
```

### 其他运行方式

- 已发布的 Windows 包：[下载 v0.13.0](docs/downloads/sentinel-0.13.0.zip) · [SHA256](docs/downloads/sentinel-0.13.0.zip.sha256)。包内能力以该发布版本为准。
- 容器：审查根目录 `compose.yaml` 与 `checks.json` 后执行 `docker compose up --build -d`。默认端口映射为本机 `127.0.0.1:8080`。容器中的 `localhost` 和磁盘路径属于容器自身。
- 本地示例与截图复现说明见 [测试文档](docs/TESTING.md) 和 `examples/`；不要将演示目标当成生产资产。

## 配置监控

配置文件是 JSON，顶层使用 `version: 1` 和 `checks` 数组，最多 200 个检查。每个检查必须有唯一 `id`、`name`、`type` 和 `target`；`tcp` 需要 `port`，`tls` 默认端口 443。`timeout_seconds` 为 0.2–60 秒，`retry_attempts` 为 0–2 次，`monitor_interval_seconds` 为 10–3600 秒。配置无效时服务会报告错误。

例如，本机磁盘剩余容量低于 20% 时预警、低于 10% 时失败（Windows 路径在 JSON 中需转义）：

```json
{
  "id": "system-disk",
  "name": "系统盘容量",
  "type": "disk",
  "target": "C:\\",
  "timeout_seconds": 5,
  "assertions": [
    {"metric": "free_percent", "op": "<", "warn": 20, "fail": 10}
  ]
}
```

Linux 可使用 `/` 或明确授权的本机绝对路径。磁盘采集不读取文件内容；本机磁盘和系统名称解析由有超时限制的子进程执行，冻结式打包运行环境暂不支持。`dns` 不接受 `port`，地址最多保留 16 个，`address_count` 是保留数量而非完整记录总数。它不验证特定记录类型、TTL 或权威答案。

断言最多 8 条，支持 `==`、`!=`、`>`、`>=`、`<`、`<=`、`in`、`exists`、`missing`。缺少所需证据时显示未知，不推测为健康。完整配置、告警与部署细节可参考 [安全说明](docs/SECURITY.md)、[测试说明](docs/TESTING.md) 和仓库 `examples/`。

## 查看结果与接口

- **工作台：**查看当前状态、检查详情、最近采样、状态变化、证书日历、维护窗口、通知与存储状态。
- **历史与趋势：**逐项近期历史最多 40 轮，长期趋势按真实 UTC 日聚合；没有采样的日期不会补造。可用率是已记录样本中非 `fail` 的比例，不是时间加权 SLA。
- **留存：**历史当前文件上限 4 MiB、最多 2 份归档、最多加载 5000 行；截断会显示在结果中。
- **离线报告：**通过 `/api/report` 下载基于当前快照的 HTML 报告。

| 接口 | 用途 |
| --- | --- |
| `GET /healthz`, `GET /readyz` | 进程存活与就绪检查 |
| `GET /api/status` | 最新快照；`?force=1` 可请求重新采样 |
| `POST /api/refresh` | 强制重新采样 |
| `GET /api/history`, `/api/trends`, `/api/certificates` | 有界历史、日趋势和证书到期信息 |
| `GET /api/config`, `/api/maintenance`, `/api/alerts` | 只读配置、维护窗口和脱敏投递账本 |
| `GET /metrics` | Prometheus 文本格式指标 |
| `GET /api/report` | 自包含 HTML 报告 |

## 安全与运行边界

默认仅监听回环地址，**没有内置账号体系**；如需对外或向局域网暴露，须自行部署合适的访问控制与反向代理。不要将密码、Token、Cookie 或私钥写入目标、名称或版本库；Webhook 地址和签名秘密可通过 `webhook_url_env` 与 `signing_secret_env` 指定环境变量。只监控你有权访问的目标。

采样、超时、重试、响应与历史均有边界；这些限制不能替代对目标系统容量、访问授权和网络策略的评估。详见 [安全说明](docs/SECURITY.md)。

## 开发与验证

```powershell
python -W error::ResourceWarning -m unittest discover -s tests -q
python -m compileall -q monitor toolbox server.py tests
node --check dashboard\app.js
git diff --check
```

网络测试使用本地替身，不要求访问公网。项目约定、API 结构和扩展方向见 [架构文档](docs/ARCHITECTURE.md)、[测试文档](docs/TESTING.md) 和 [路线图](ROADMAP.md)。

## 许可证

[MIT](LICENSE)。
