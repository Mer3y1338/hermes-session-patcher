# -*- coding: utf-8 -*-
"""
Hermes Session Patcher CLI 入口 — 参考 codex-keysmith 的接口设计

```
hermes-patcher list                          # 列出包含拒绝回复的会话
hermes-patcher list --all                    # 列出所有会话
hermes-patcher patch --latest                # 清理最新会话拒绝回复
hermes-patcher patch --all                   # 清理所有会话拒绝回复
hermes-patcher patch --session-id <id>       # 清理指定会话
hermes-patcher patch --dry-run               # 只预览不写
hermes-patcher install-unrestricted          # 安装 keysmith 风格破限 (推荐)
hermes-patcher install-unrestricted --mode godmode_v2  # GODMODE V2 模式
hermes-patcher install-unrestricted --dry-run         # 预览模式
hermes-patcher uninstall-unrestricted        # 按清单卸载
hermes-patcher unrestricted-status           # 查看部署状态
hermes-patcher recover                       # 恢复中断的部署
hermes-patcher install-ctf                  # (旧) 安装 CTF 模式 (向后兼容)
hermes-patcher uninstall-ctf                # (旧) 卸载 CTF 模式 (向后兼容)
hermes-patcher ctf-status                    # (旧) 查看 CTF 状态 (向后兼容)
hermes-patcher rewrite "..."                 # 改写提示词
hermes-patcher web                           # 启动 Web UI
```
"""

import argparse
import json
import sys
from typing import Optional

from . import __version__
from .core import (
    RefusalDetector,
    HermesSessionDBAdapter,
    MOCK_RESPONSE,
)
from .core.constants import MOCK_RESPONSE as _MR
from .ctf_config import HermesUnrestrictedInstaller, HermesCTFInstaller


# ─── 会话清理命令 ──────────────────────────────────────────────────────────────────

def cmd_list(args):
    adapter = HermesSessionDBAdapter()
    sessions = adapter.list_sessions(skip_refusal_check=args.skip_check)
    if not args.skip_check:
        detector = RefusalDetector()
        sessions_with_refusal = [s for s in sessions if s.has_refusal]
        if not args.all:
            sessions = sessions_with_refusal

    print(f"共 {len(sessions)} 个会话")
    for s in sessions:
        flag = f" ⚠️({s.refusal_count})" if s.has_refusal else ""
        title = s.title[:40] + ('…' if len(s.title) > 40 else '')
        print(f"  [{s.session_id}] {s.started_at_str} | {s.source:<10} | msgs={s.message_count:<4} | {title}{flag}")


def cmd_patch_session(session_id: str, dry_run: bool, create_backup: bool, clean_reasoning: bool):
    adapter = HermesSessionDBAdapter()
    has_changes, changes = adapter.preview_session(
        session_id,
        mock_response=_MR,
        clean_reasoning=clean_reasoning,
    )
    if not has_changes:
        print(f"会话 {session_id} 没有需要清理的拒绝回复")
        return

    print(f"发现 {len(changes)} 处修改:")
    for ch in changes:
        if ch.change_type == 'replace':
            preview = (ch.original or "")[:80].replace('\n', ' ')
            print(f"  [#{ch.message_id}] REPLACE | {preview}...")
        elif ch.change_type == 'remove_thinking':
            print(f"  [#{ch.message_id}] REMOVE_THINKING")

    if dry_run:
        print("(dry-run 模式，未实际写入)")
        return

    applied, applied_changes = adapter.apply_patch(
        session_id,
        mock_response=_MR,
        clean_reasoning=clean_reasoning,
        create_backup=create_backup,
    )
    if applied:
        if create_backup:
            print(f"✓ 已备份 state.db")
        print(f"✓ 已清理 {len(applied_changes)} 处")
    else:
        print("✗ 清理失败")


def cmd_patch(args):
    adapter = HermesSessionDBAdapter()
    sessions = adapter.list_sessions()

    if args.session_id:
        cmd_patch_session(args.session_id, args.dry_run, not args.no_backup, not args.keep_reasoning)
        return

    if args.latest:
        with_refusal = [s for s in sessions if s.has_refusal]
        if not with_refusal:
            print("没有发现包含拒绝回复的会话")
            return
        target = with_refusal[0]
        print(f"清理最新会话: {target.session_id} ({target.title})")
        cmd_patch_session(target.session_id, args.dry_run, not args.no_backup, not args.keep_reasoning)
        return

    if args.all:
        with_refusal = [s for s in sessions if s.has_refusal]
        if not with_refusal:
            print("没有发现包含拒绝回复的会话")
            return
        print(f"将清理 {len(with_refusal)} 个会话")
        for s in with_refusal:
            print(f"\n--- 会话: {s.session_id} ({s.title}) ---")
            cmd_patch_session(s.session_id, args.dry_run, not args.no_backup, not args.keep_reasoning)
        return

    print("请指定 --latest / --all / --session-id")
    sys.exit(1)


# ─── Unrestricted 模式命令（keysmith 风格）────────────────────────────────────────

def cmd_install_unrestricted(args):
    """安装 Unrestricted 模式 — keysmith 风格文件部署"""
    installer = HermesUnrestrictedInstaller()
    if args.dry_run:
        # 预览模式：显示将要做什么
        from .ctf_config import HermesCTFInstaller as _H
        from .core.constants import BUILTIN_UNRESTRICTED_MD, CTF_SECURITY_PROMPT_GODMODE_V2, CTF_SECURITY_PROMPT
        prompt_map = {
            "keysmith": BUILTIN_UNRESTRICTED_MD,
            "godmode_v2": CTF_SECURITY_PROMPT_GODMODE_V2,
            "ctf": CTF_SECURITY_PROMPT,
        }
        prompt = prompt_map.get(args.mode, BUILTIN_UNRESTRICTED_MD)
        prompt_sha = __import__("hashlib").sha256(prompt.encode("utf-8")).hexdigest()

        print("[DRY RUN] 预览模式，不实际修改。")
        print(f"\n[提示词] 模式: {args.mode}")
        print(f"  SHA-256: {prompt_sha}")
        print(f"  长度: {len(prompt)} 字符")
        print(f"\n[显著行为] 该提示词会注入到 config.yaml 的 agent.system_prompt，")
        print(f"  并写入指令文件到 ~/.hermes/instructions/")
        print(f"  重新定义安全边界词，限制拒绝/警告，覆盖逆向、远程命令、成人和武器等请求。")
        print(f"\n  目标: {installer.config_path}")
        print(f"  → 写入指令 MD: ~/.hermes/instructions/")
        print(f"  → 修改 config.yaml: agent.system_prompt (添加标记块)")
        if args.mode in ("keysmith", "ctf"):
            print(f"  → 修改 SOUL.md: 添加标记块")
        if args.mode == "godmode_v2":
            print(f"  → 写入 prefill.json")
        print(f"\n  如确认写入，请重新运行并去掉 --dry-run。")
        return

    ok, msg = installer.install(mode=args.mode)
    print(msg)
    if not ok:
        sys.exit(1)


def cmd_uninstall_unrestricted(args):
    """按清单卸载 — 精准还原所有变更"""
    installer = HermesUnrestrictedInstaller()
    ok, msg = installer.uninstall()
    print(msg)
    if not ok:
        sys.exit(1)


def cmd_unrestricted_status(args):
    """查看部署状态 — 只读"""
    installer = HermesUnrestrictedInstaller()
    status = installer.status()
    print(json.dumps(status, indent=2, ensure_ascii=False))


def cmd_recover(args):
    """恢复中断的部署"""
    installer = HermesUnrestrictedInstaller()
    ok, msg = installer.recover(dry_run=not args.yes)
    print(msg)


# ─── 向后兼容的 CTF 命令 ──────────────────────────────────────────────────────────

def cmd_install_ctf(args):
    """旧版 CTF 安装命令 — 向后兼容，内部调用 install-unrestricted"""
    installer = HermesCTFInstaller()
    # 旧版默认用 append 模式，映射到 ctf
    mode = args.mode if args.mode != "append" else "ctf"
    ok, msg = installer.install(mode=mode)
    print(msg)
    if not ok:
        sys.exit(1)


def cmd_uninstall_ctf(args):
    """旧版 CTF 卸载命令 — 向后兼容"""
    installer = HermesCTFInstaller()
    ok, msg = installer.uninstall()
    print(msg)


def cmd_ctf_status(args):
    """旧版 CTF 状态命令 — 向后兼容"""
    installer = HermesCTFInstaller()
    status = installer.status()
    print(json.dumps(status, indent=2, ensure_ascii=False))


def cmd_rewrite(args):
    """调用 LLM 改写提示词"""
    print("提示词改写需要配置 AI 端点。当前仅打印原始提示：")
    print(args.prompt)
    print("\n--- 建议改写方向 ---")
    print("加入 CTF 比赛场景 / 授权渗透测试 / 安全研究 等上下文")


def cmd_web(args):
    from .web.backend.main import run_server
    run_server(host=args.host, port=args.port)


# ─── 主入口 ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="hermes-patcher",
        description="Hermes Agent 会话清理器 & Unrestricted 破限部署工具 — Hermes 版 codex-session-patcher + keysmith",
    )
    parser.add_argument("--version", action="version", version=__version__)

    sub = parser.add_subparsers(dest="command")

    # list
    p_list = sub.add_parser("list", help="列出会话")
    p_list.add_argument("--all", action="store_true", help="列出所有会话（包括没有拒绝的）")
    p_list.add_argument("--skip-check", action="store_true", help="跳过拒绝检测")
    p_list.set_defaults(func=cmd_list)

    # patch
    p_patch = sub.add_parser("patch", help="清理拒绝回复")
    p_patch.add_argument("--session-id", help="指定会话 ID")
    p_patch.add_argument("--latest", action="store_true", help="只清理最新含拒绝的会话")
    p_patch.add_argument("--all", action="store_true", help="清理所有含拒绝的会话")
    p_patch.add_argument("--dry-run", action="store_true", help="仅预览不写入")
    p_patch.add_argument("--no-backup", action="store_true", help="不创建备份")
    p_patch.add_argument("--keep-reasoning", action="store_true", help="保留 reasoning 内容")
    p_patch.set_defaults(func=cmd_patch)

    # install-unrestricted (keysmith 风格，推荐)
    p_install = sub.add_parser("install-unrestricted", help="安装 Unrestricted 破限模式 (keysmith 风格文件部署)")
    p_install.add_argument("--mode", choices=["keysmith", "godmode_v2", "ctf", "append", "replace"],
                           default="keysmith",
                           help="keysmith 重新定义式(推荐) | godmode_v2 脱敏divider | ctf 旧版授权框架 | append/replace 向后兼容")
    p_install.add_argument("--dry-run", action="store_true", help="预览模式，不实际修改")
    p_install.set_defaults(func=cmd_install_unrestricted)

    # uninstall-unrestricted
    p_uninstall = sub.add_parser("uninstall-unrestricted", help="按部署清单卸载 Unrestricted 模式")
    p_uninstall.set_defaults(func=cmd_uninstall_unrestricted)

    # unrestricted-status
    p_status = sub.add_parser("unrestricted-status", help="查看 Unrestricted 部署状态 (只读)")
    p_status.set_defaults(func=cmd_unrestricted_status)

    # recover
    p_recover = sub.add_parser("recover", help="恢复中断的部署事务")
    p_recover.add_argument("--yes", action="store_true", help="执行恢复（默认只预览）")
    p_recover.set_defaults(func=cmd_recover)

    # install-ctf (向后兼容)
    p_ctf_install = sub.add_parser("install-ctf", help="(旧) 安装 CTF 安全测试模式 — 向后兼容别名")
    p_ctf_install.add_argument("--mode", choices=["append", "replace", "godmode", "godmode_v2"], default="append",
                               help="append(默认) | replace | godmode(⚠️) | godmode_v2(推荐)")
    p_ctf_install.set_defaults(func=cmd_install_ctf)

    # uninstall-ctf (向后兼容)
    p_ctf_uninstall = sub.add_parser("uninstall-ctf", help="(旧) 卸载 CTF 模式 — 向后兼容别名")
    p_ctf_uninstall.set_defaults(func=cmd_uninstall_ctf)

    # ctf-status (向后兼容)
    p_ctf_status = sub.add_parser("ctf-status", help="(旧) 查看 CTF 模式状态 — 向后兼容别名")
    p_ctf_status.set_defaults(func=cmd_ctf_status)

    # rewrite
    p_rewrite = sub.add_parser("rewrite", help="改写提示词使其更易被接受")
    p_rewrite.add_argument("prompt", help="要改写的提示词")
    p_rewrite.set_defaults(func=cmd_rewrite)

    # web
    p_web = sub.add_parser("web", help="启动 Web UI")
    p_web.add_argument("--host", default="127.0.0.1")
    p_web.add_argument("--port", type=int, default=8080)
    p_web.set_defaults(func=cmd_web)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
