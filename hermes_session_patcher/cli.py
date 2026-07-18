# -*- coding: utf-8 -*-
"""
Hermes Session Patcher CLI 入口
```
hermes-patcher --list             # 列出包含拒绝回复的会话
hermes-patcher --latest           # 清理最新会话
hermes-patcher --all              # 清理所有会话
hermes-patcher --session-id <id>  # 清理指定会话
hermes-patcher --dry-run          # 只预览不写
hermes-patcher --web               # 启动 Web UI
hermes-patcher --install-ctf       # 安装 CTF 模式
hermes-patcher --uninstall-ctf     # 卸载 CTF 模式
hermes-patcher --ctf-status        # 查看 CTF 状态
hermes-patcher --rewrite "..."     # 改写提示词
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
from .ctf_config import HermesCTFInstaller


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
        # 找最新的一个有拒绝回复的会话
        with_refusal = [s for s in sessions if s.has_refusal]
        if not with_refusal:
            print("没有发现包含拒绝回复的会话")
            return
        target = with_refusal[0]
        print(f"清理最新会话: {target.session_id} ({target.title})")
        cmd_patch_session(target.session_id, args.dry_run, not args.no_backup, not args.keep_reasoning)
        return

    if args.all:
        # 清理所有有拒绝回复的会话
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


def cmd_install_ctf(args):
    installer = HermesCTFInstaller()
    ok, msg = installer.install(mode=args.mode)
    print(msg)
    if not ok:
        sys.exit(1)


def cmd_uninstall_ctf(args):
    installer = HermesCTFInstaller()
    ok, msg = installer.uninstall()
    print(msg)


def cmd_ctf_status(args):
    installer = HermesCTFInstaller()
    status = installer.status()
    print(json.dumps(status, indent=2, ensure_ascii=False))


def cmd_rewrite(args):
    """调用 LLM 改写提示词"""
    from .ctf_config import PROMPT_REWRITER_SYSTEM
    # 简化版：直接拼接一个改写提示在用户输入前
    print("提示词改写需要配置 AI 端点。当前仅打印原始提示：")
    print(args.prompt)
    print("\n--- 建议改写方向 ---")
    print("加入 CTF 比赛场景 / 授权渗透测试 / 安全研究 等上下文")


def cmd_web(args):
    from .web.backend.main import run_server
    run_server(host=args.host, port=args.port)


def main():
    parser = argparse.ArgumentParser(
        prog="hermes-patcher",
        description="Hermes Agent 会话清理器 & CTF 提示词注入工具 — Hermes 版 codex-session-patcher",
    )
    parser.add_argument("--version", action="version", version=__version__)

    # 子命令
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

    # install-ctf
    p_install = sub.add_parser("install-ctf", help="安装 CTF 安全测试模式")
    p_install.add_argument("--mode", choices=["append", "replace", "godmode", "godmode_v2"], default="append",
                          help="append 追加(默认) | replace 完全替换 | godmode 激进版(⚠️易被过滤挂起) | godmode_v2 脱敏版(实测有效,推荐)")
    p_install.set_defaults(func=cmd_install_ctf)

    # uninstall-ctf
    p_uninstall = sub.add_parser("uninstall-ctf", help="卸载 CTF 安全测试模式")
    p_uninstall.set_defaults(func=cmd_uninstall_ctf)

    # ctf-status
    p_status = sub.add_parser("ctf-status", help="查看 CTF 模式状态")
    p_status.set_defaults(func=cmd_ctf_status)

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
