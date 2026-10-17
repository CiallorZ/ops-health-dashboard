# Sentinel · 运维健康看板

一个零依赖、默认只监听本机的运维健康看板。它把网络连通性、TCP 端口、TLS 证书和 HTTP 服务状态放在同一条实时时间线上，帮助你在用户投诉前发现异常。

> 当前版本：`v0.2.0`。状态来自真实检测；失败就是失败，不做“演示模式”或伪造成功率。

## 功能

- **四类检查**：ICMP ping、TCP 端口、TLS 证书有效期、HTTP 状态码与延迟。
- **本地工具箱**：JSON 格式化、CIDR 计算、IP 分析、哈希/HMAC，统一错误与输入上限。
- **可解释状态**：`ok` / `warn` / `fail`，并保留原始错误信息、延迟、状态码与证书到期时间。
- **历史采样**：每次完整检测写入本地 `data/history.jsonl`，页面展示最近 32 次健康轨迹。
- **有界超时**：每个检查独立超时，任一检查失败不会拖垮整个看板。
- **安全默认值**：只监听 `127.0.0.1`，CSP、`nosniff`、禁止 iframe，配置校验拒绝 URL 内的凭据。
- **无构建链**：Python 标准库 + 原生 HTML/CSS/JS，不安装运行时依赖。
- **三端运行**：Windows 本机、Docker、任意有 Python 3.11+ 的机器。

## 快速开始

要求：Python 3.11 或更高版本。

```powershell
python server.py
```

浏览器打开 <http://127.0.0.1:8080>。默认每 30 秒拉取一次最新状态，点击右上角刷新按钮可立即重新采样。页面中的“随身工具”无需额外服务：JSON 在浏览器本地处理，其余工具只在本机 API 内做确定性计算。

修改 `checks.json` 后重启服务。所有资产都在这个文件里，不需要改代码。

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

启动项会做两件事：登录后拉起看板，以及检查 `origin/main` 的已验证更新。更新只在工作区干净时执行 fast-forward，并先跑测试。日志位于 `data\logs\`（已加入 `.gitignore`，不会提交）。

## 配置

最小示例：

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
      "type": "http",
      "target": "https://example.com/health",
      "expected_status": [200, 204],
      "timeout_seconds": 5,
      "tags": ["production", "api"]
    },
    {
      "id": "ssh",
      "name": "跳板机 SSH",
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

字段说明：

| 字段 | 说明 |
|---|---|
| `id` | 唯一标识，只能使用字母、数字、`-`、`_` |
| `type` | `http` / `tcp` / `tls` / `ping` |
| `target` | HTTP 为完整 URL；其余为主机名或 IP |
| `port` | `tcp` 必填；`tls` 默认 443 |
| `expected_status` | HTTP 可接受状态码，默认 `[200]` |
| `verify_tls` | 是否验证证书链，默认 `true`；不验证会显著降低判断可信度 |
| `timeout_seconds` | 单项超时，范围 0.2–60 秒 |
| `enabled` | 设为 `false` 可暂时停用单项，不必删除 |

## API

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/health` | 进程存活与版本，不触发资产检测 |
| `GET` | `/api/status` | 获取缓存状态；`?force=1` 强制重新检测 |
| `GET` | `/api/history?limit=40` | 读取历史摘要 |
| `GET` | `/api/config` | 只读配置，不含任何秘密 |
| `GET` | `/api/tools` | 工具目录与输入元数据 |
| `POST` | `/api/tools/run` | 执行 allow-list 工具；请求体最多 64 KiB |

`/api/status` 默认缓存 8 秒，避免浏览器多标签页同时制造重复请求。

工具 API 只接受 `application/json`，输入会做类型和长度校验。`json-format` 明确只在浏览器本地执行，服务端会拒绝其内容；其余工具不访问外部网络，也不会执行任意命令。

## 测试

无第三方依赖：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q monitor toolbox server.py tests
node --check dashboard\app.js
git diff --check
```

CI 会在 Python 3.11 和 3.13 上执行同一套测试，并检查 Python 编译、JavaScript 语法和差异空白。测试覆盖配置拒绝路径、HTTP/TLS 边界、并发刷新去重、历史持久化、HTTP 安全响应头及工具箱的校验/错误路径。

## Docker

```powershell
docker compose up --build -d
```

容器只映射到本机 `127.0.0.1:8080`。数据保存在 `dashboard-data` volume。

## 安全边界

- 看板没有登录系统。不要直接暴露到公网。
- 配置里不要写密码、Token、Cookie 或带凭据的 URL；后端会拒绝 URL 内嵌凭据。
- 不执行用户提供的任意命令；`ping` 的 target 经过主机名/地址格式校验，且不通过 shell。
- 远程资产检测会从运行看板的主机发起。把本机放在正确网络位置，结果才有意义。
- TLS 检查用于发现证书到期和握手异常，不等同于完整的外部安全扫描。

## Roadmap

- [x] `v0.1` 基线：四类检测、实时看板、历史、CI、Docker。
- [x] `v0.2` 工具基础：JSON/CIDR/IP/HASH、注册表、统一错误、API/UI 测试。
- [ ] `v0.3` 诊断与报告：本机网络摘要、DNS/路由诊断、可离线导出的报告。
- [ ] `v0.4` 监控连续性：重试策略、分组资产、按天趋势、可选 Webhook 告警。
- [ ] `v0.5` Windows 与自动化：系统/磁盘/进程摘要、受控计划任务视图、发布与备份说明。

更细的验收标准和依赖关系见 [`ROADMAP.md`](ROADMAP.md)。

## 文档

- [`AGENTS.md`](AGENTS.md)：长期开发规则和质量门禁。
- [`ROADMAP.md`](ROADMAP.md)：分阶段产品路线与验收标准。
- [`CHANGELOG.md`](CHANGELOG.md)：版本变更记录。
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)：模块边界、数据流和扩展方式。
- [`docs/SECURITY.md`](docs/SECURITY.md)：威胁模型和运行边界。
- [`docs/TESTING.md`](docs/TESTING.md)：测试命令、范围和已知限制。

## License

MIT

