# Sentinel 工作台演示

这是独立的静态交互原型，不接入 Sentinel 后端，也不向输入的目标发起请求。所有资产、指标、曲线和事件都是模拟数据。添加的对象仅存在当前页面内，刷新页面后消失。

在仓库根目录启动：

```powershell
python -m http.server 18125 --bind 127.0.0.1 --directory demo
```

浏览器访问 `http://127.0.0.1:18125/`。演示支持领域导航、状态筛选、搜索、对象详情、事件钻取、模拟趋势范围切换、模拟添加、模拟刷新与重置。`Ctrl+K` / `Cmd+K` 打开快捷查找，`/` 聚焦列表搜索；动效遵循系统的减少动态效果设置。

界面的监控时间线和详情组织参考 [Uptime Kuma](https://github.com/louislam/uptime-kuma)；节点、指标和事件的分层参考 [Netdata 仪表板文档](https://github.com/netdata/netdata/blob/master/docs/dashboards-and-charts/README.md)。仅借鉴交互结构，没有复制代码或图形资源。

不要将本演示的状态、资产或可用率作为真实监控结论；真实系统仍使用项目的 `server.py` 和 `dashboard/`。
