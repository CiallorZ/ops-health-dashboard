# 发布流程

## 版本规则

采用 [Semantic Versioning](https://semver.org/)：

- **MAJOR**：不兼容的 API / 配置 / 行为变化；
- **MINOR**：向后兼容的功能新增；
- **PATCH**：向后兼容的缺陷修复。

版本号同时维护在：

- `VERSION`
- `monitor/__init__.py`
- `dashboard/index.html` 页脚
- `CHANGELOG.md`

## 提交前检查

1. 阅读 `git status`、`git diff` 与 `git diff --staged`；
2. 确认没有凭据、调试代码、生成文件或无关改动；
3. 执行 `docs/TESTING.md` 中的全部门禁；
4. API / UI 改动完成临时端口手工验收；
5. 更新 `CHANGELOG.md` 与相关文档。

## 版本发布

1. 功能提交进入持续维护分支；
2. 创建或更新 Pull Request，附实际改动、测试证据与已知限制；
3. 等待远端 CI 针对最新提交通过；
4. 确认无冲突、无阻塞评论；
5. 由维护者按合并策略合入 `main`。

**合并不等于发布。** 自动化不得自行创建 tag、GitHub Release、生产部署或修改生产配置。

## 回滚

- 代码回滚使用可审查的 revert 提交，不使用 force push；
- 配置回滚前先备份 `checks.json` 与 `data/history.jsonl`；
- 任何安全或数据丢失风险都必须先报告，不自动合并。

## 变更记录

`CHANGELOG.md` 按 Keep a Changelog 格式维护：

```markdown
## [0.5.0] - 2026-10-21

### Added
- ...

### Fixed
- ...
```
