# -*- coding: utf-8 -*-
"""
Hermes 会话格式策略 — 适配 Hermes 的 SQLite messages 表
messages 表字段：id, session_id, role, content, tool_call_id, tool_calls, 
tool_name, timestamp, token_count, finish_reason, reasoning, reasoning_content,
reasoning_details, codex_reasoning_items, codex_message_items
"""

from typing import Dict, List, Any, Tuple
import json
import re


class HermesFormatStrategy:
    """
    Hermes 会话格式策略
    - assistant 消息：role='assistant' 且 content 非空
    - 不直接删行（SQLite），而是将 content 替换为新文本
    - thinking/reasoning 为独立字段
    """

    def get_assistant_messages(self, rows: List[Dict[str, Any]]) -> List[Tuple[int, Dict[str, Any]]]:
        """从 SQLite 行中提取助手消息，content 必须非空"""
        messages = []
        for idx, row in enumerate(rows):
            role = row.get('role', '')
            if role == 'assistant' and row.get('content'):
                messages.append((idx, row))
        # 筛选可能带拒绝回复的：content 非空且 tool_name 为空（纯文本回复）
            # 检测拒绝回复不只看纯文本，也看.tool_calls=空
        return messages

    def get_thinking_items(self, rows: List[Dict[str, Any]]) -> List[Tuple[int, Dict[str, Any]]]:
        """Hermes 的 reasoning 是独立字段，不是独立行。只要 reasoning_content 非空就标记"""
        items = []
        for idx, row in enumerate(rows):
            reasoning_content = row.get('reasoning_content') or row.get('reasoning') or row.get('reasoning_details') or ''
            if reasoning_content:
                items.append((idx, row))
        return items

    def extract_text_content(self, row: Dict[str, Any]) -> str:
        """从 Hermes 消息行提取纯文本内容"""
        # 当 tool_call_id 非空时会带 tool 结果，但角色可能是 'tool' 或 'assistant'
        # 纯 assistant 文本回复时，content 是纯字符串
        content = row.get('content', '')
        if not content:
            # 可能是 tool_calls-only 消息（没有 content 字段，只有 tool_calls）
            return ''
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            # 列表内容项可能是文本块
            texts = []
            for item in content:
                if isinstance(item, str):
                    texts.append(item)
                elif isinstance(item, dict) and item.get('text'):
                    texts.append(item['text'])
            return '\n'.join(texts)
        return str(content) if content else ''

    def update_text_content(self, row: Dict[str, Any], new_text: str) -> Dict[str, Any]:
        """返回更新后的行（浅拷贝足够，因为只用 content 字段）"""
        updated = dict(row)
        updated['content'] = new_text
        # 清理 tool_calls（拒绝回复通常没有 tool_calls）
        return updated

    def remove_thinking(self, row: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """
        移除 reasoning 相关字段，返回 (更新后的行, 被移除的字段数)
        """
        updated = dict(row)
        removed = 0
        for field in ('reasoning', 'reasoning_content', 'reasoning_details', 'codex_reasoning_items'):
            if updated.get(field):
                updated[field] = None
                removed += 1
        return updated, removed
