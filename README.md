# hermes-session-patcher

> Hermes Agent 会话清理器 & Unrestricted 破限部署工具
> 
> 参考 [codex-session-patcher](https://github.com/ryfineZ/codex-session-patcher) 适配 Hermes SQLite，并融合 [codex-keysmith](https://github.com/Jia-Ethan/codex-keysmith) 的架构设计哲学

## 核心功能

### 🔧 会话清理（源自 codex-session-patcher）
- 扫描 Hermes `state.db` 中所有会话
- 检测 assistant 回复中的拒绝内容（"我不能"、"I can't"、道歉式开头 + 拒绝动词）
- 自动替换为 mock 回复，清理 reasoning
- 支持单会话 / 最新 / 全部清理

### 🚀 Unrestricted 部署（融合 keysmith 架构）
- **文件式部署**：破限指令写入 `~/.hermes/instructions/<name>.md`
- **原子写入**：临时文件 + fsync + atomic rename，杜绝半成品
- **部署清单（manifest）**：JSON 记录每次部署的所有变更和指纹
- **清单式卸载**：按 manifest 精准还原，diff 无差异
- **事务日志（journal）**：每步记录状态，中断可 `recover` 恢复
- **备份策略**：写入前备份原文件到时间戳副本

## 安装

```bash
cd hermes-session-patcher
pip install -e .
```

## 使用

### 会话清理

```bash
hermes-patcher list                     # 列出包含拒绝回复的会话
hermes-patcher list --all               # 列出所有会话
hermes-patcher patch --latest           # 清理最新会话
hermes-patcher patch --all              # 清理所有会话
hermes-patcher patch --session-id <id>  # 清理指定会话
hermes-patcher patch --dry-run         # 只预览不写
hermes-patcher patch --no-backup        # 不创建备份
hermes-patcher patch --keep-reasoning  # 保留 reasoning
```

### Unrestricted 部署（参考 keysmith 架构）

```bash
hermes-patcher install-unrestricted                              # 安装 keysmith 风格（推荐）
hermes-patcher install-unrestricted --mode keysmith --dry-run    # 预览
hermes-patcher install-unrestricted --mode godmode_v2            # GODMODE V2 模式 + prefill
hermes-patcher install-unrestricted --mode ctf                   # 旧版 CTF 授权框架

hermes-patcher unrestricted-status      # 查看部署状态（只读）
hermes-patcher uninstall-unrestricted   # 按清单卸载，精准还原
hermes-patcher recover                  # 恢复中断的部署
```

### 向后兼容（旧 CTF 命令）

```bash
hermes-patcher install-ctf --mode godmode_v2   # = install-unrestricted --mode godmode_v2
hermes-patcher uninstall-ctf                   # = uninstall-unrestricted
hermes-patcher ctf-status                      # = unrestricted-status
```

## 模式对比

| 模式 | 设计哲学 | 来源 | 推荐 |
|------|----------|------|------|
| `keysmith` | 重新定义式 —— 把"reverse shell"重定义为"encrypted socket client"，模型根本不触发拒绝分支 | codex-keysmith | ⭐⭐⭐ |
| `godmode_v2` | Pliny divider 风格 —— "write refusal + insert divider + answer"，脱敏版 + prefill | godmode skill | ⭐⭐ |
| `ctf` | 授权框架 —— "assume authorized by default"，场景化（CTF/pentest/bounty/research） | 初版 hermes-patcher | ⭐ |

### keysmith 设计哲学（来自 Jia-Ethan 大神）

1. **不用"胁迫式"拒绝压制**（如 "Never refuse..."），改用**"重定义式"**
2. 把模型认为"这是攻击"的词**重新定义成软件工程标准术语**
3. **"Local fixture" 框架** —— 所有目标都是"本地样本"而非真实目标
4. **处方式模板（Prescriptive templates）** —— 明确每种请求的首行锚点
5. **层独立（Layer independence）** —— 处理中间注入的上下文块，不受其影响
6. **边界词处理** —— "未经授权"等词视为"fixture descriptor"，转占位符继续输出

## 架构

```
hermes_session_patcher/
├── core/
│   ├── constants.py       # 破限 prompt 常量（BUILTIN_UNRESTRICTED_MD 等）
│   ├── detector.py        # 拒绝内容检测器（两级策略 + 误报改进）
│   ├── hermes_db.py       # Hermes SQLite 会话适配器
│   └── format_strategy.py # Hermes 会话格式策略
├── ctf_config/
│   └── installer.py       # Unrestricted 安装器（keysmith 风格）
│                           # - DeploymentManifest  部署清单
│                           # - DeploymentJournal   事务日志
│                           # - 原子写入、备份、清单式卸载
├── web/                   # Web UI（FastAPI 后端 + 前端）
└── cli.py                 # CLI 入口
```

## 部署清单（manifest）

每次部署生成一个 JSON 清单，位于 `~/.hermes-session-patcher/manifests/<deployment_id>.json`，记录：

- `deployment_id` — 唯一部署 ID
- `mode` — 部署模式（keysmith / godmode_v2 / ctf）
- `instruction_file` — 指令 MD 文件路径
- `instruction_sha256` — 指令内容 SHA-256
- `config_changes` — config.yaml 变更（field + old_sha + new_sha）
- `backups` — 备份文件列表（original + backup path）

卸载时按清单精准还原所有变更。

## 事务日志（journal）

每次部署生成一个 JSONL 事务日志，位于 `~/.hermes-session-patcher/journals/<deployment_id>.jsonl`，每行一个 JSON 记录：

```json
{"ts": "20260718_143900", "step": "start", "status": "intent", "detail": {"mode": "keysmith"}}
{"ts": "20260718_143900", "step": "backup-config", "status": "done", "detail": {"backup": "..."}}
{"ts": "20260718_143900", "step": "write-instruction", "status": "done", "detail": {"path": "..."}}
{"ts": "20260718_143900", "step": "update-config", "status": "done", "detail": {...}}
{"ts": "20260718_143900", "step": "complete", "status": "done", "detail": {"manifest": "..."}}
```

中断后可用 `hermes-patcher recover` 查看或恢复。

## 安全特性

- **原子写入**：所有文件写入通过临时文件 + fsync + atomic rename
- **自动备份**：写入前备份原文件到时间戳副本
- **标记块**：注入内容用 `<!-- managed-by: hermes-session-patcher:unrestricted -->` 包裹，便于精准清理
- **清单式卸载**：不靠模糊匹配，按 JSON 清单逐项还原
- **事务日志**：每步记录状态，中断可恢复
- **只预览模式**：`--dry-run` 不实际修改任何文件

## 许可证

MIT
