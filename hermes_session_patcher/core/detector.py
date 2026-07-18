# -*- coding: utf-8 -*-
"""
拒绝内容检测器 — 复用 codex-session-patcher 的两级检测策略
"""

from typing import Dict, List, Optional


class RefusalDetector:
    """拒绝内容检测器"""

    def __init__(self, custom_keywords: Optional[Dict[str, List[str]]] = None):
        self.custom_keywords = {}
        if custom_keywords:
            for lang, words in custom_keywords.items():
                self.custom_keywords[lang] = list(words)
        self.keywords = self.custom_keywords

    # 强拒绝短语：出现在任意位置即判定为拒绝
    STRONG_REFUSAL_PHRASES = [
        # 中文
        "我无法协助", "我无法帮助", "我不能协助", "我不能帮助",
        "我不能做", "我无法做", "我不会帮", "我无法提供",
        "违反了我的", "违反我的", "这违反",
        "我拒绝", "我必须拒绝",
        "我不能生成", "我无法生成", "我不会生成",
        "我不能创建", "我无法创建",
        "安全准则", "安全政策", "安全规定",
        # 英文
        "i cannot assist", "i can't assist", "i'm unable to assist",
        "i cannot help", "i can't help", "i'm unable to help",
        "i must decline", "i must refuse",
        "against my guidelines", "against my policy",
        "violates my", "i won't help", "i won't assist",
        "as an ai", "as a language model",
        "i apologize, but i", "i'm sorry, but i can't",
        "not able to provide", "not able to assist",
        "i cannot generate", "i can't generate",
        "safety guidelines", "safety policy",
    ]

    # 弱拒绝关键词：需要出现在消息开头（前 200 字符）才算拒绝
    WEAK_REFUSAL_KEYWORDS = [
        # 中文
        "抱歉", "很抱歉", "对不起", "不好意思",
        "我无法", "我不能", "不允许", "禁止",
        "不能帮你", "不能协助", "无法帮你", "无法协助你",
        "不会帮你", "不会帮助", "不能为你", "无法为你",
        "我不能参与", "我无法参与",
        # 英文
        "sorry", "apologize", "i cannot", "i can't",
        "i'm unable", "unable to", "not permitted", "not allowed",
        "refuse to",
    ]

    def detect(self, content: str) -> bool:
        """
        检测内容是否包含拒绝回复

        使用两级策略：
        1. 强拒绝短语：出现在任意位置即判定（误报率低）
        2. 弱拒绝关键词：仅在消息开头 200 字符内出现才判定
        3. 自定义关键词：作为强匹配，全文搜索
        """
        if not content:
            return False

        content_lower = content.lower()

        # 1. 强拒绝短语 - 全文匹配
        for phrase in self.STRONG_REFUSAL_PHRASES:
            if phrase in content_lower:
                return True

        # 2. 弱拒绝关键词 - 仅匹配开头 200 字符
        head = content_lower[:200]
        for keyword in self.WEAK_REFUSAL_KEYWORDS:
            if keyword in head:
                return True

        # 3. 用户自定义关键词 - 全文匹配
        if self.keywords:
            for lang, lang_keywords in self.keywords.items():
                for keyword in lang_keywords:
                    if keyword.lower() in content_lower:
                        return True

        return False
