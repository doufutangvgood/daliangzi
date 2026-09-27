"""评论解析与清洗。

真实世界的评论数据是脏的：字段名千奇百怪、有广告、有纯表情、有重复。
这一层负责把它擦干净，并且**如实汇报丢掉了什么** —— 用户有权知道。
"""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .model import Comment, make_id

# ---------------------------------------------------------------- 字段识别

TEXT_KEYS = [
    "评论内容", "评论", "内容", "正文", "回复内容", "文本",
    "content", "comment", "comment_text", "text", "body", "message",
    "reply_content", "reply", "desc", "description", "note",
]
LIKE_KEYS = [
    "点赞数", "点赞量", "点赞", "赞数", "赞",
    "like_count", "likes", "like_num", "like", "digg_count", "digg",
    "praise_count", "praised_count", "up_count", "voteup_count", "agree",
]
AUTHOR_KEYS = [
    "昵称", "用户名", "作者", "用户", "评论者",
    "nickname", "nick_name", "username", "user_name", "author", "user",
    "screen_name", "uname", "name",
]
TIME_KEYS = [
    "发布时间", "创建时间", "时间", "日期",
    "create_time", "created_at", "publish_time", "time", "date", "ctime",
    "pub_time", "create_date",
]
PLATFORM_KEYS = ["平台", "来源", "platform", "source", "source_platform", "site"]
ID_KEYS = ["评论id", "comment_id", "cid", "rpid", "id", "commentId"]
PARENT_KEYS = ["父评论", "parent_comment_id", "parent_id", "root_comment_id", "pid"]
REPLY_TO_KEYS = ["回复", "reply_to", "reply_to_user", "reply_to_username", "to_user"]

# MediaCrawler 的 JSONL 常见嵌套：sub_comments 里还有一层
NESTED_KEYS = ["sub_comments", "replies", "children", "subComments"]


def _pick(record: dict[str, Any], candidates: list[str]) -> str | None:
    """按候选名找字段，先精确匹配，再忽略大小写/下划线匹配。"""
    for key in candidates:
        if key in record and record[key] not in (None, ""):
            return key

    normalized = {
        re.sub(r"[\s_\-]", "", str(k)).lower(): k for k in record.keys()
    }
    for key in candidates:
        flat = re.sub(r"[\s_\-]", "", key).lower()
        if flat in normalized:
            actual = normalized[flat]
            if record[actual] not in (None, ""):
                return actual
    return None


def detect_mapping(records: list[dict[str, Any]]) -> dict[str, str | None]:
    """从样本里猜字段映射。返回 {语义字段: 实际列名}。"""
    sample = [r for r in records[:50] if isinstance(r, dict)]
    if not sample:
        return {}

    # 合并所有样本的键，避免第一条缺字段就判错
    merged: dict[str, Any] = {}
    for r in sample:
        for k, v in r.items():
            if k not in merged and v not in (None, ""):
                merged[k] = v

    mapping = {
        "text": _pick(merged, TEXT_KEYS),
        "likes": _pick(merged, LIKE_KEYS),
        "author": _pick(merged, AUTHOR_KEYS),
        "created_at": _pick(merged, TIME_KEYS),
        "platform": _pick(merged, PLATFORM_KEYS),
        "id": _pick(merged, ID_KEYS),
        "parent_id": _pick(merged, PARENT_KEYS),
        "reply_to": _pick(merged, REPLY_TO_KEYS),
    }

    # 兜底：没有 text 字段时，挑一个「字符串最长」的列当正文
    if not mapping["text"]:
        best, best_len = None, 0
        for k, v in merged.items():
            if isinstance(v, str) and len(v) > best_len:
                best, best_len = k, len(v)
        if best and best_len >= 8:
            mapping["text"] = best

    return mapping


# ---------------------------------------------------------------- 载入

@dataclass
class LoadResult:
    records: list[dict[str, Any]] = field(default_factory=list)
    mapping: dict[str, str | None] = field(default_factory=dict)
    source_format: str = ""
    warnings: list[str] = field(default_factory=list)


def _flatten_json(obj: Any, out: list[dict[str, Any]]) -> None:
    """把任意嵌套的 JSON 结构摊平成记录列表。

    识别到 sub_comments 之类的嵌套评论数组就递归进去，二级评论不会丢。
    父记录里那个嵌套数组会被剥掉 —— 否则子评论会在落盘数据里存两份。
    """
    if isinstance(obj, list):
        for item in obj:
            _flatten_json(item, out)
        return
    if not isinstance(obj, dict):
        return

    # 先把嵌套的评论数组抽出来递归
    nested: list[Any] = []
    for key in NESTED_KEYS:
        value = obj.get(key)
        if isinstance(value, list) and value:
            nested.extend(value)

    # 这条记录本身是不是一条评论？
    if nested:
        record = {k: v for k, v in obj.items() if k not in NESTED_KEYS}
    else:
        record = obj
    out.append(record)

    for child in nested:
        _flatten_json(child, out)


def load_from_text(text: str, filename: str = "") -> LoadResult:
    """从文件内容载入。按扩展名和内容自动判格式。"""
    name = (filename or "").lower()
    stripped = text.lstrip()
    result = LoadResult()

    # 1) 明确的 JSON 文件
    if name.endswith(".json"):
        return _load_json_text(text)
    if name.endswith(".jsonl") or name.endswith(".ndjson"):
        return _load_jsonl_text(text)
    if name.endswith((".csv", ".tsv")):
        return _load_delimited_text(text, "\t" if name.endswith(".tsv") else None)

    # 2) 没有扩展名或 .txt，靠内容猜
    if stripped[:1] in "[{":
        try:
            return _load_json_text(text)
        except Exception:  # noqa: BLE001 - 猜错了就继续往下试
            pass

    # 3) JSONL：每行一个 JSON 对象
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if lines and all(ln.lstrip()[:1] == "{" for ln in lines[: min(10, len(lines))]):
        try:
            return _load_jsonl_text(text)
        except Exception:  # noqa: BLE001
            pass

    # 4) 分隔符文件：有逗号/制表符且首行像表头
    if lines and ("," in lines[0] or "\t" in lines[0]):
        try:
            return _load_delimited_text(text, None)
        except Exception:  # noqa: BLE001
            pass

    # 5) 纯文本，一行一条
    result.source_format = "text"
    result.records = [{"content": ln.strip()} for ln in lines if ln.strip()]
    result.mapping = {"text": "content"}
    result.warnings.append("按纯文本解析：每一行作为一条评论。")
    return result


def _load_json_text(text: str) -> LoadResult:
    raw = json.loads(text)
    records: list[dict[str, Any]] = []
    _flatten_json(raw, records)
    records = [r for r in records if isinstance(r, dict)]
    return LoadResult(
        records=records,
        mapping=detect_mapping(records),
        source_format="json",
    )


def _load_jsonl_text(text: str) -> LoadResult:
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            _flatten_json(json.loads(line), records)
        except json.JSONDecodeError:
            continue
    records = [r for r in records if isinstance(r, dict)]
    return LoadResult(
        records=records,
        mapping=detect_mapping(records),
        source_format="jsonl",
    )


def _load_delimited_text(text: str, delimiter: str | None) -> LoadResult:
    sample = text[:8192]
    if delimiter is None:
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = ","

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    records = [dict(row) for row in reader]
    return LoadResult(
        records=records,
        mapping=detect_mapping(records),
        source_format="csv",
    )


def load_from_file(path: str | Path) -> LoadResult:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError("读取 Excel 需要 pandas，本机未安装。") from exc
        frame = pd.read_excel(path)
        records = frame.where(frame.notna(), None).to_dict(orient="records")
        return LoadResult(
            records=records,
            mapping=detect_mapping(records),
            source_format="excel",
        )
    text = path.read_text(encoding="utf-8", errors="replace")
    result = load_from_text(text, filename=path.name)
    return result


# ---------------------------------------------------------------- 清洗

# 纯表情 / 纯符号 / 纯 @
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF"
    "\u2190-\u21FF\u2300-\u23FF\u2B00-\u2BFF\uFE0F\u200D]+"
)
_PUNCT_RE = re.compile(r"[\s\.,;:!?，。；：！？、~～…·\-—_/\\|\[\]【】()（）<>《》\"'`^*#@&+=]+")
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_MENTION_RE = re.compile(r"@[\w\u4e00-\u9fff\-_]{1,30}")

# 广告 / 引流。宁可漏杀不可错杀，所以只匹配很明确的模式。
_AD_PATTERNS = [
    re.compile(p) for p in [
        r"加\s*(我|微信|V|v|微)\s*[:：]?\s*[\w\-]{4,}",
        r"微信\s*[:：]\s*[\w\-]{4,}",
        r"[Vv][Xx]\s*[:：]?\s*[\w\-]{5,}",
        r"[Qq][Qq]\s*[:：]?\s*\d{5,}",
        r"(私信|滴滴|dd)\s*(我|他)?\s*(了解|咨询|领取|购买|下单)",
        r"(点|戳)(我)?(头像|主页|简介).{0,6}(看|了解|领|进)",
        r"(免费|限时|0元|一元|九块九|9\.9)\s*(领|抢|购|学|课|资料)",
        r"(代购|代发|刷单|兼职|博彩|赌|棋牌|彩票|办证|发票)",
        r"(招|招聘).{0,4}(代理|下线|兼职).{0,6}(日结|周结|月入)",
    ]
]

# 纯灌水。这类评论长度够但没有任何信息量，不滤掉会白烧 token。
_FILLER_WORDS = {
    "哈哈", "哈哈哈", "哈哈哈哈", "呵呵", "嘿嘿", "嘻嘻", "笑死", "笑死我了",
    "顶", "帮顶", "路过", "沙发", "板凳", "前排", "打卡", "签到", "已阅",
    "好", "好的", "行", "可以", "中", "赞", "支持", "同意", "确实", "是的",
    "6", "66", "666", "6666", "牛", "牛逼", "厉害", "优秀", "绝了",
    "不知道", "不清楚", "无所谓", "无所谓了", "随便", "看看", "围观", "吃瓜",
    "第一", "二楼", "楼上说得对", "同感", "+1", "+1s",
}

# 同一个字重复 3 次以上（啊啊啊、。。。不算，标点另有处理）
_REPEAT_RE = re.compile(r"^(.)\1{2,}$")


def _strip_noise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _URL_RE.sub(" ", text)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _substantive_len(text: str) -> int:
    """去掉表情和标点之后还剩多少「实义字符」。"""
    t = _EMOJI_RE.sub("", text)
    t = _PUNCT_RE.sub("", t)
    return len(t)


def _is_filler(text: str) -> bool:
    """是不是纯灌水（哈哈哈、666、沙发、已阅…）。

    这类评论长度够，但没有任何立场信息，留着只会白烧 token。
    """
    t = _PUNCT_RE.sub("", _EMOJI_RE.sub("", text)).strip()
    if not t:
        return True
    if _REPEAT_RE.match(t):
        return True
    if t in _FILLER_WORDS:
        return True
    # 反复刷同一个短词：「哈哈哈哈哈」「666666」
    for word in ("哈", "呵", "嘿", "嘻", "6", "顶", "赞", "啊", "哦", "嗯", "额"):
        if len(t) >= 3 and set(t) == {word}:
            return True
    return False


@dataclass
class CleanReport:
    """清洗结果 + 每一步丢了多少。要如实展示给用户。"""

    comments: list[Comment] = field(default_factory=list)
    total_in: int = 0
    dropped_empty: int = 0
    dropped_short: int = 0
    dropped_filler: int = 0
    dropped_ad: int = 0
    dropped_duplicate: int = 0
    merged_duplicate_likes: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def total_out(self) -> int:
        return len(self.comments)

    def summary(self) -> dict[str, Any]:
        return {
            "原始条数": self.total_in,
            "去空": self.dropped_empty,
            "去太短": self.dropped_short,
            "去灌水": self.dropped_filler,
            "去广告": self.dropped_ad,
            "去重复": self.dropped_duplicate,
            "保留": self.total_out,
            "notes": self.notes,
        }


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().lower().replace(",", "")
    if not s:
        return 0
    mult = 1
    if s.endswith("万") or s.endswith("w"):
        mult, s = 10000, s[:-1]
    elif s.endswith("k"):
        mult, s = 1000, s[:-1]
    elif s.endswith("亿"):
        mult, s = 100000000, s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return 0


def records_to_comments(
    records: Iterable[dict[str, Any]],
    mapping: dict[str, str | None],
    *,
    platform: str = "",
    min_chars: int = 3,
    drop_ads: bool = True,
    drop_filler: bool = True,
    dedupe: bool = True,
) -> CleanReport:
    """把原始记录转成干净的 Comment 列表。"""
    report = CleanReport()
    text_key = mapping.get("text")
    if not text_key:
        report.notes.append("没有识别出正文字段，无法导入。请在界面上手动指定哪一列是评论内容。")
        return report

    seen: dict[str, Comment] = {}

    for record in records:
        if not isinstance(record, dict):
            continue
        report.total_in += 1

        raw_text = record.get(text_key)
        if raw_text is None:
            report.dropped_empty += 1
            continue

        text = _strip_noise(str(raw_text))
        if not text:
            report.dropped_empty += 1
            continue

        if _substantive_len(text) < min_chars:
            report.dropped_short += 1
            continue

        if drop_filler and _is_filler(text):
            report.dropped_filler += 1
            continue

        if drop_ads and any(p.search(text) for p in _AD_PATTERNS):
            report.dropped_ad += 1
            continue

        def _get(semantic: str) -> str:
            key = mapping.get(semantic)
            if not key:
                return ""
            value = record.get(key)
            return "" if value is None else str(value).strip()

        comment = Comment(
            text=text,
            likes=_to_int(record.get(mapping["likes"])) if mapping.get("likes") else 0,
            platform=_get("platform") or platform,
            author=_get("author"),
            created_at=_get("created_at"),
            parent_id=_get("parent_id"),
            reply_to=_get("reply_to"),
        )

        if not dedupe:
            report.comments.append(comment)
            continue

        # 去重键：去掉表情和标点后的正文。这样「好评！」和「好评！！」算同一条。
        key = _PUNCT_RE.sub("", _EMOJI_RE.sub("", text)).lower()

        existing = seen.get(key)
        if existing is None:
            seen[key] = comment
        else:
            report.dropped_duplicate += 1
            # 保留点赞高的那条，但把点赞累加，避免丢掉热度信号
            if comment.likes > existing.likes:
                report.merged_duplicate_likes += existing.likes
                comment.likes += existing.likes
                seen[key] = comment
            else:
                existing.likes += comment.likes
                report.merged_duplicate_likes += comment.likes

    if dedupe:
        report.comments = list(seen.values())

    return report
