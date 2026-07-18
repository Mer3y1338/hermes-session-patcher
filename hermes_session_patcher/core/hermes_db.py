# -*- coding: utf-8 -*-
"""
Hermes SQLite 会话适配器 — 读取和修改 Hermes state.db
"""

import os
import sqlite3
import json
import shutil
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Any, Tuple, Optional

from .detector import RefusalDetector
from .format_strategy import HermesFormatStrategy
from .constants import MOCK_RESPONSE


DEFAULT_HERMES_DB = os.path.expanduser("~/.hermes/state.db")
DEFAULT_CONFIG_FILE = os.path.expanduser("~/.hermes/config.yaml")
DEFAULT_SOUL_FILE = os.path.expanduser("~/.hermes/SOUL.md")
DEFAULT_BACKUP_DIR = os.path.expanduser("~/.hermes-session-patcher/backups")
DEFAULT_PATCHER_CONFIG = os.path.expanduser("~/.hermes-session-patcher/config.json")


@dataclass
class HermesSessionInfo:
    """Hermes 会话信息"""
    session_id: str
    source: str
    model: str
    title: str
    message_count: int
    started_at: float
    started_at_str: str
    has_refusal: bool = False
    refusal_count: int = 0
    has_backup: bool = False
    backup_count: int = 0


@dataclass
class ChangeDetail:
    """修改详情"""
    message_id: int        # messages.id (SQLite PK)
    session_id: str
    change_type: str       # 'replace' | 'remove_thinking'
    original: Optional[str] = None
    replacement: Optional[str] = None


class HermesSessionDBAdapter:
    """Hermes SQLite 会话数据库适配器"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DEFAULT_HERMES_DB
        self._strategy = HermesFormatStrategy()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def list_sessions(self, skip_refusal_check: bool = False) -> List[HermesSessionInfo]:
        """列出所有 Hermes 会话，带拒绝检测"""
        sessions: List[HermesSessionInfo] = []
        try:
            conn = self._conn()
            cur = conn.execute(
                """
                SELECT id, source, model, title, message_count, started_at
                FROM sessions
                WHERE message_count > 0 AND COALESCE(title, '') != ''
                ORDER BY started_at DESC
                LIMIT 500
                """
            )
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            raise RuntimeError(f"查询会话列表失败: {e}")

        detector = RefusalDetector()
        for row in rows:
            sid = row["id"]
            started_str = datetime.fromtimestamp(row["started_at"]).strftime("%Y-%m-%d %H:%M:%S")
            # 拒绝检测
            has_refusal = False
            refusal_count = 0
            if not skip_refusal_check:
                has_refusal, refusal_count = self.check_session_refusal(sid, detector)
            # 备份检测
            backup_count = self._count_backups(sid)

            sessions.append(HermesSessionInfo(
                session_id=sid,
                source=row["source"],
                model=row["model"] or "",
                title=row["title"] or "",
                message_count=row["message_count"],
                started_at=row["started_at"],
                started_at_str=started_str,
                has_refusal=has_refusal,
                refusal_count=refusal_count,
                has_backup=backup_count > 0,
                backup_count=backup_count,
            ))
        return sessions

    def load_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """加载一个会话内的所有 messages（按时间排序）"""
        try:
            conn = self._conn()
            cur = conn.execute(
                """
                SELECT id, session_id, role, content, tool_call_id, tool_calls,
                       tool_name, timestamp, token_count, finish_reason,
                       reasoning, reasoning_content, reasoning_details,
                       codex_reasoning_items, codex_message_items
                FROM messages
                WHERE session_id = ?
                ORDER BY timestamp ASC
                """,
                (session_id,),
            )
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            raise RuntimeError(f"加载会话消息失败: {e}")

    def check_session_refusal(self, session_id: str, detector: RefusalDetector = None) -> Tuple[bool, int]:
        """检查会话是否包含拒绝回复"""
        if detector is None:
            detector = RefusalDetector()
        rows = self.load_session_messages(session_id)
        assistant_msgs = []
        for idx, row in enumerate(rows):
            if row.get("role") == "assistant" and row.get("content"):
                content = row["content"]
                if isinstance(content, str) and content.strip():
                    assistant_msgs.append(row)

        count = 0
        for msg in assistant_msgs:
            content = self._strategy.extract_text_content(msg)
            if content and detector.detect(content):
                count += 1
        return count > 0, count

    def preview_session(
        self,
        session_id: str,
        mock_response: str = MOCK_RESPONSE,
        custom_keywords: dict = None,
        clean_reasoning: bool = True,
        selected_message_ids: Optional[List[int]] = None,
    ) -> Tuple[bool, List[ChangeDetail]]:
        """
        预览会话修改，返回 (是否需要修改, 修改详情列表)
        不写入数据库
        """
        detector = RefusalDetector(custom_keywords)
        rows = self.load_session_messages(session_id)
        changes: List[ChangeDetail] = []

        selected_set = set(selected_message_ids) if selected_message_ids else None

        # 1. 拒绝消息替换
        for row in rows:
            role = row.get('role', '')
            content = row.get('content', '')
            if role != 'assistant' or not content or not isinstance(content, str) or not content.strip():
                continue
            if not detector.detect(content):
                continue
            msg_id = row['id']
            if selected_set is not None and msg_id not in selected_set:
                continue
            changes.append(ChangeDetail(
                message_id=msg_id,
                session_id=session_id,
                change_type='replace',
                original=content[:500] + ('...' if len(content) > 500 else ''),
                replacement=mock_response,
            ))

        # 2. reasoning 字段清除
        if clean_reasoning:
            for row in rows:
                reasoning = row.get('reasoning_content') or row.get('reasoning') or row.get('reasoning_details') or ''
                if reasoning:
                    msg_id = row['id']
                    if selected_set is not None and msg_id not in selected_set:
                        continue
                    changes.append(ChangeDetail(
                        message_id=msg_id,
                        session_id=session_id,
                        change_type='remove_thinking',
                    ))

        return len(changes) > 0, changes

    def apply_patch(
        self,
        session_id: str,
        mock_response: str = MOCK_RESPONSE,
        custom_keywords: dict = None,
        clean_reasoning: bool = True,
        selected_message_ids: Optional[List[int]] = None,
        create_backup: bool = True,
    ) -> Tuple[bool, List[ChangeDetail]]:
        """
        对 Hermes state.db 应用清理，返回 (是否修改, 修改详情)
        """
        has_changes, _changes = self.preview_session(
            session_id, mock_response, custom_keywords,
            clean_reasoning, selected_message_ids,
        )
        if not has_changes:
            return False, []

        if create_backup:
            self.create_backup(session_id)

        detector = RefusalDetector(custom_keywords)
        rows = self.load_session_messages(session_id)
        selected_set = set(selected_message_ids) if selected_message_ids else None

        applied: List[ChangeDetail] = []
        conn = self._conn()
        try:
            for row in rows:
                msg_id = row['id']
                role = row.get('role', '')
                content = row.get('content', '')

                # 检查是否在选中列表内
                if selected_set is not None and msg_id not in selected_set:
                    # 也检查 reasoning 是否要清理（除非列出）
                    continue

                # 1. 拒绝文本替换
                if (role == 'assistant' and content
                    and isinstance(content, str) and content.strip()
                    and detector.detect(content)):
                    conn.execute(
                        "UPDATE messages SET content = ? WHERE id = ?",
                        (mock_response, msg_id),
                    )
                    applied.append(ChangeDetail(
                        message_id=msg_id,
                        session_id=session_id,
                        change_type='replace',
                        original=content[:500] + ('...' if len(content) > 500 else ''),
                        replacement=mock_response,
                    ))

                # 2. reasoning 清理
                if clean_reasoning:
                    reasoning_fields = ('reasoning', 'reasoning_content',
                                       'reasoning_details', 'codex_reasoning_items')
                    should_clean = any(row.get(f) for f in reasoning_fields)
                    if should_clean:
                        conn.execute(
                            """UPDATE messages SET 
                               reasoning = NULL,
                               reasoning_content = NULL,
                               reasoning_details = NULL,
                               codex_reasoning_items = NULL
                               WHERE id = ?""",
                            (msg_id,),
                        )
                        applied.append(ChangeDetail(
                            message_id=msg_id,
                            session_id=session_id,
                            change_type='remove_thinking',
                        ))

            conn.commit()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"应用清理失败: {e}")
        finally:
            conn.close()

        return True, applied

    # ─── 备份还原 ────────────────────────────────────────────────

    def _backup_dir(self, session_id: Optional[str] = None) -> str:
        return DEFAULT_BACKUP_DIR

    def _count_backups(self, session_id: str) -> int:
        backup_dir = self._backup_dir()
        if not os.path.exists(backup_dir):
            return 0
        prefix = f"state_{session_id}_"
        return sum(1 for f in os.listdir(backup_dir) if f.startswith(prefix) and f.endswith('.db'))

    def create_backup(self, session_id: str) -> str:
        """对 state.db 做快照备份到指定目录"""
        os.makedirs(DEFAULT_BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"state_{session_id}_{timestamp}.db"
        backup_path = os.path.join(DEFAULT_BACKUP_DIR, backup_name)
        shutil.copy2(self.db_path, backup_path)
        return backup_path

    def list_backups(self) -> List[Dict]:
        backups = []
        if not os.path.exists(DEFAULT_BACKUP_DIR):
            return backups
        for f in sorted(os.listdir(DEFAULT_BACKUP_DIR), reverse=True):
            if f.endswith('.db') and f.startswith('state_'):
                parts = f.replace('.db', '').split('_', 3)
                if len(parts) >= 4:
                    session_id = parts[1] + '_' + parts[2]
                    timestamp_str = parts[3]
                    fake_path = os.path.join(DEFAULT_BACKUP_DIR, f)
                    size = os.path.getsize(fake_path)
                    backups.append({
                        'filename': f,
                        'session_id': session_id,
                        'timestamp': timestamp_str,
                        'path': fake_path,
                        'size': size,
                    })
        return backups

    def restore_backup(self, backup_filename: str) -> bool:
        """还原一个备份（注意这会覆盖 state.db）"""
        backup_path = os.path.join(DEFAULT_BACKUP_DIR, backup_filename)
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"备份文件不存在: {backup_path}")
        # 先备份当前 state.db，再还原
        current_backup = self.db_path + ".before-restore-" + datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(self.db_path, current_backup)
        shutil.copy2(backup_path, self.db_path)
        return True

    def restore_session_from_backup(self, backup_filename: str, session_id: str) -> bool:
        """
        从备份中恢复一个 session 的消息（只替换该 session_id 的 messages）
        """
        backup_path = os.path.join(DEFAULT_BACKUP_DIR, backup_filename)
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"备份文件不存在: {backup_path}")

        # 从备份中读取对应 session 的 messages
        bconn = sqlite3.connect(backup_path)
        bconn.row_factory = sqlite3.Row
        bcur = bconn.execute(
            """SELECT id, session_id, role, content, tool_call_id, tool_calls,
                      tool_name, timestamp, token_count, finish_reason,
                      reasoning, reasoning_content, reasoning_details,
                      codex_reasoning_items, codex_message_items
               FROM messages WHERE session_id = ? ORDER BY timestamp ASC""",
            (session_id,),
        )
        backup_rows = [r for r in bcur.fetchall()]
        bconn.close()
        if not backup_rows:
            return False

        # 删除当前 session 的所有 messages
        conn = self._conn()
        try:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            for r in backup_rows:
                conn.execute(
                    """INSERT INTO messages 
                       (id, session_id, role, content, tool_call_id, tool_calls,
                        tool_name, timestamp, token_count, finish_reason,
                        reasoning, reasoning_content, reasoning_details,
                        codex_reasoning_items, codex_message_items)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (r["id"], r["session_id"], r["role"], r["content"],
                     r["tool_call_id"], r["tool_calls"], r["tool_name"],
                     r["timestamp"], r["token_count"], r["finish_reason"],
                     r["reasoning"], r["reasoning_content"], r["reasoning_details"],
                     r["codex_reasoning_items"], r["codex_message_items"]),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return True
