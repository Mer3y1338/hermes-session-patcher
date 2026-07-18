# -*- coding: utf-8 -*-
"""
拒绝内容检测器 — 复用 codex-session-patcher 的两级检测策略 + Hermes 误报改进

改进点：
- 弱关键词开头匹配后，需要在 30 字符内跟随"拒绝动词"（为你/协助/帮助/生成/执行/完成...）才判定
- 排除元讨论场景（引用、讨论拒绝词本身时不算拒绝）
"""

import re
from typing import Dict, List, Optional


class RefusalDetector:
    """拒绝内容检测器"""

    def __init__(self, custom_keywords: Optional[Dict[str, List[str]]] = None):
        self.custom_keywords = {}
        if custom_keywords:
            for lang, words in custom_keywords.items():
                self.custom_keywords[lang] = list(words)
        self.keywords = self.custom_keywords

    # 强拒绝短语：出现在任意位置即判定为拒绝（这些短语明确包含拒绝动词）
    STRONG_REFUSAL_PHRASES = [
        # 中文 — 短语本身就含完整的拒绝结构
        "我无法协助", "我无法帮助", "我不能协助", "我不能帮助",
        "我不能做", "我无法做", "我不会帮", "我无法提供",
        "我不能提供", "我无法执行", "我不能执行",
        "我不能生成", "我无法生成", "我不会生成",
        "我不能创建", "我无法创建",
        "我不能继续", "我无法继续",
        "我不能写", "我无法写", "我不会写",
        "违反了我的", "违反我的", "这违反",
        "我拒绝", "我必须拒绝",
        "安全准则", "安全政策", "安全规定",
        "违反我的安全", "违反安全",
        # 英文 — 完整 refusal 短语
        "i cannot assist", "i can't assist", "i'm unable to assist",
        "i cannot help", "i can't help", "i'm unable to help",
        "i must decline", "i must refuse",
        "against my guidelines", "against my policy",
        "violates my", "i won't help", "i won't assist",
        "i cannot generate", "i can't generate",
        "i cannot create", "i can't create",
        "i cannot provide", "i can't provide",
        "i cannot fulfill", "i can't fulfill",
        "safety guidelines", "safety policy",
        # 较宽松的 "as an ai"，仅当与其他拒绝信号一起出现才算
        # 这里保留，但只作强匹配
    ]

    # 弱拒绝开头关键词：需要在开头 200 字符内出现
    WEAK_REFUSAL_PREFIXES = [
        # 中文 — 道歉式开头
        "抱歉", "很抱歉", "对不起", "不好意思",
        "我无法", "我不能", "不允许", "禁止",
        "不能帮你", "不能协助", "无法帮你", "无法协助你",
        "不会帮你", "不会帮助", "不能为你", "无法为你",
        # 英文 — apology 开头
        "sorry", "i apologize", "i'm sorry",
        "i cannot", "i can't", "i'm unable", "unable to",
        "not permitted", "not allowed", "refuse to",
    ]

    # 弱关键词开头后必须跟随的"拒绝动词"（在 30 字符内）
    # —— 用于过滤 "抱歉，刚才的回复有误" / "对不起主人" 这种非拒绝道歉
    REFUSAL_VERBS_CN = [
        "为你", "协助", "帮助", "协助",
        "生成", "创建", "执行", "完成", "提供",
        "写", "做", "继续", "参与",
        "编写", "制作", "开发",
        "满足", "实现",
    ]
    REFUSAL_VERBS_EN = [
        "assist", "help", "provide", "create", "generate",
        "write", "do", "complete", "fulfill", "produce",
        "support", "make",
    ]

    # 元讨论排除模式 — 引用/讨论拒绝词本身时不判拒绝
    META_DISCUSSION_PATTERNS = [
        # 引号引用："Sorry, I cannot" / "我无法..."
        r'["""\'`]([^"""\n]{0,30}(?:cannot|无法|我无法|抱歉|对不起)[^"""\n]{0,80})["""\'`]',
        # 报告/分析：检测到了拒绝回复、原文是 xxx
        r'(?:检测到|原文是|被拒绝|拒绝回复|含拒绝|refusal)',
        # 猫娘撒娇："对不起主人" 后面没有拒绝动词
        r'对不起主人',
        r'抱歉主人',
    ]

    def detect(self, content: str) -> bool:
        """
        检测内容是否包含拒绝回复
        改进版策略：
        1. 先排除元讨论场景（引用、分析拒绝词本身）
        2. 强拒绝短语：出现在任意位置即判定（误报率低）
        3. 弱拒绝关键词：必须在开头 200 字符内出现，并伴随拒绝动词
        4. 自定义关键词：强匹配，全文搜索
        """
        if not content:
            return False

        content_lower = content.lower()

        # 0. 元讨论排除：如果内容主要是讨论/引用拒绝词本身，不算拒绝
        if self._is_meta_discussion(content):
            return False

        # 1. 强拒绝短语 - 全文匹配
        for phrase in self.STRONG_REFUSAL_PHRASES:
            if phrase in content_lower:
                return True

        # 2. 弱拒绝关键词 - 仅匹配开头 200 字符，必须伴随拒绝动词
        head = content_lower[:200]
        for prefix in self.WEAK_REFUSAL_PREFIXES:
            idx = head.find(prefix)
            if idx < 0:
                continue
            # 找到弱关键词，检查其后面 30 字符内是否有拒绝动词
            after = head[idx + len(prefix):idx + len(prefix) + 30]
            if self._has_refusal_verb(after):
                return True
            # 特殊处理：如果弱关键词本身就是完整拒绝（"不能帮你"/"无法协助你"等），直接判定
            if prefix in ("不能帮你", "不能协助", "无法帮你", "无法协助你",
                          "不会帮你", "不会帮助", "不能为你", "无法为你",
                          "refuse to"):
                return True

        # 3. 用户自定义关键词 - 全文匹配
        if self.keywords:
            for lang, lang_keywords in self.keywords.items():
                for keyword in lang_keywords:
                    if keyword.lower() in content_lower:
                        return True

        return False

    def _has_refusal_verb(self, text: str) -> bool:
        """检查文本内是否含拒绝动词"""
        text_lower = text.lower()
        for verb in self.REFUSAL_VERBS_CN:
            if verb in text:
                return True
        for verb in self.REFUSAL_VERBS_EN:
            if verb in text_lower:
                return True
        return False

    def _is_meta_discussion(self, content: str) -> bool:
        """
        判断是否为"元讨论"：内容主要在讨论/引用拒绝词本身，而非真的拒绝
        
        判定规则（保守，宁可漏判也不误判）：
        - 文本中明确出现"引用"或"分析"信号词
        - 同时文本不在开头就进入拒绝模式
        """
        if not content:
            return False
        # 如果文本开头 50 字符就是强拒绝短语直接就不进元讨论分支
        head_50 = content[:50].lower()
        for phrase in self.STRONG_REFUSAL_PHRASES:
            if phrase in head_50:
                return False  # 开头就是拒绝，不可能是元讨论

        # 引号引用了拒绝词 —— 可能是元讨论
        has_quote_of_refusal = bool(re.search(
            r'["""\'`]([^"""\n]{0,120}(?:cannot|can\'t|无法|不能|抱歉|对不起|unable)[^"""\n]{0,120})["""\'`]',
            content, re.IGNORECASE,
        ))
        # 分析/报告语境
        has_analysis_signal = any(
            p in content for p in [
                '检测到', '原文是', '被拒绝', '拒绝回复', '含拒绝', 'refusal',
                '识别到', '扫描到', '扫到了', '正确识别', '被判定',
                '这就是', '属于误报', '算拒绝', '是不是拒绝',
            ]
        )
        # 猫娘撒娇"对不起主人"不是拒绝
        has_catgirl_apology = (
            ('对不起主人' in content or '抱歉主人' in content)
            and not any(v in content[:content.find('对不起主人') + 10] if '对不起主人' in content else ''
                       for v in ['不会', '不能', '拒绝', '无法'])
        )

        # "刚才的回复有误"、"记岔了"等纠正式开头不算拒绝
        is_correction = any(p in content[:100] for p in [
            '刚才的回复有误', '记岔了', '回复有误', '我说错了',
            '刚才说错', '之前有误', '这点我错了',
        ])

        return has_quote_of_refusal or has_analysis_signal or has_catgirl_apology or is_correction
