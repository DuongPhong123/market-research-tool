import re
import logging
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)

STOPWORDS_VI = {
    "va", "cua", "la", "trong", "co", "duoc", "cho", "voi", "khong", "nay",
    "da", "mot", "cac", "nhu", "ve", "tu", "khi", "theo", "bi", "thi",
    "ra", "vao", "day", "do", "o", "tai", "de", "nen", "hay", "hoac",
    "ma", "the", "rat", "lam", "qua", "vay", "nhe", "a", "oi", "nhi",
    "em", "anh", "chi", "ban", "toi", "minh", "ho", "chung", "bao", "nhieu",
    "that", "dung", "van", "con", "dang", "se", "can", "muon", "phai",
    "thay", "biet", "noi", "lam", "dung", "mua", "ban", "co", "khong", "het",
    "shop", "ship", "oke", "ok", "on", "tot", "duoc", "nhan", "dat",
}

POSITIVE_WORDS = {
    "tot", "tuyet", "dinh", "xin", "ngon", "dep", "chat", "on", "hai long",
    "yeu thich", "recommend", "thich", "ung", "ung y", "chat luong",
    "nhanh", "dung", "du", "chuan", "ok", "oke", "good", "nice", "perfect",
    "xuat sac", "amazing", "tuyet voi", "hoan hao", "5 sao", "sieu", "qua dinh",
    "xung dang", "dang tien", "gia tot", "re ma chat", "dung tot", "ben",
}

NEGATIVE_WORDS = {
    "kem", "te", "do", "xau", "nhat", "cham", "thieu", "sai", "loi",
    "hong", "vo", "nhai", "fake", "gia", "dat", "khong dang", "that vong",
    "phan nan", "khieu nai", "tra hang", "hoan tien", "lua", "doi mai",
    "khong nhu mo ta", "khac hinh", "kem chat luong", "rac", "khong dung duoc",
    "be", "phai", "bong", "xuoc", "meo", "co", "rut", "khong vua",
}

# Phrases signalling buying intent / price inquiry (transliterated Vietnamese)
PRICE_INQUIRY_KEYWORDS = {
    "xin gia", "gia bao nhieu", "bao nhieu tien", "gia thi truong",
    "gia si", "gia le", "gia goc", "link mua", "mua o dau",
    "dat hang", "order duoc khong", "inbox gia", "cho xin gia",
    "pm gia", "dm gia", "nhan inbox", "lien he shop",
    "mua nhu the nao", "con hang khong", "co ban khong",
    "gia the nao", "dang ban khong", "mua duoc khong",
    "bao nhieu", "gia ban", "ban gia",
}

PRODUCT_PATTERNS = [
    r"(?:mua|dat|order|dung|thu)\s+([a-zA-Z\s]{3,30})",
    r"san pham\s+([a-zA-Z\s]{3,30})",
    r"([a-zA-Z\s]{3,20})\s+(?:chat luong|tot|ngon|dinh|xin)",
    r"([a-zA-Z\s]{3,20})\s+(?:gia|tien|dong)",
]

PAIN_POINT_PATTERNS = [
    r"(?:khong|chua|thieu|can|muon)\s+([a-zA-Z\s]{3,30})",
    r"(?:bi|gap|phan nan|kho chiu|buc)\s+([a-zA-Z\s]{3,30})",
    r"(?:tai sao|sao|ly do|vi sao)\s+([a-zA-Z\s]{3,30})",
    r"mong\s+(?:rang|la|sao)?\s*([a-zA-Z\s]{3,30})",
]


def analyze_sentiment(text: str) -> float:
    if not text or not text.strip():
        return 0.0
    text_lower = text.lower()
    pos_count = sum(1 for w in POSITIVE_WORDS if w in text_lower)
    neg_count = sum(1 for w in NEGATIVE_WORDS if w in text_lower)
    total = pos_count + neg_count
    if total == 0:
        return 0.0
    return round((pos_count - neg_count) / total, 3)


def is_price_inquiry(text: str) -> bool:
    """Return True if the comment contains a price/buying-intent signal."""
    if not text:
        return False
    text_lower = text.lower()
    return any(kw in text_lower for kw in PRICE_INQUIRY_KEYWORDS)


def extract_keywords(text: str, top_n: int = 10) -> list[str]:
    if not text or not text.strip():
        return []
    text_clean = re.sub(r"[^\w\s]", " ", text)
    text_clean = re.sub(r"\s+", " ", text_clean).strip().lower()
    words = text_clean.split()
    keywords = [w for w in words if len(w) >= 3 and w not in STOPWORDS_VI and not w.isdigit()]
    freq = Counter(keywords)
    return [w for w, _ in freq.most_common(top_n)]


def extract_product_mentions(text: str) -> list[str]:
    if not text:
        return []
    mentions = []
    text_lower = text.lower()
    for pattern in PRODUCT_PATTERNS:
        for match in re.findall(pattern, text_lower):
            clean = match.strip()
            if len(clean) >= 3 and clean not in STOPWORDS_VI:
                mentions.append(clean)
    return list(set(mentions))[:5]


def extract_pain_points(text: str) -> list[str]:
    if not text:
        return []
    pain_points = []
    text_lower = text.lower()
    for pattern in PAIN_POINT_PATTERNS:
        for match in re.findall(pattern, text_lower):
            clean = match.strip()
            if len(clean) >= 5 and clean not in STOPWORDS_VI:
                pain_points.append(clean)
    return list(set(pain_points))[:3]


def analyze_comment(comment: dict) -> dict:
    content = comment.get("content") or ""
    return {
        **comment,
        "sentiment_score": analyze_sentiment(content),
        "keywords": extract_keywords(content, top_n=5),
        "product_mentions": extract_product_mentions(content),
        "pain_points": extract_pain_points(content),
        "is_price_inquiry": is_price_inquiry(content),
    }


def analyze_comments_batch(comments: list[dict]) -> dict:
    if not comments:
        return {
            "overall_sentiment": 0.0, "sentiment_label": "Trung lap",
            "top_keywords": [], "top_pain_points": [], "top_product_mentions": [],
            "comment_count": 0, "positive_pct": 0, "negative_pct": 0,
            "price_inquiry_count": 0, "price_inquiry_pct": 0.0,
        }
    analyzed = [analyze_comment(c) for c in comments]
    sentiments = [a["sentiment_score"] for a in analyzed]
    overall = sum(sentiments) / len(sentiments) if sentiments else 0.0
    positive_count = sum(1 for s in sentiments if s > 0.1)
    negative_count = sum(1 for s in sentiments if s < -0.1)
    price_inquiry_count = sum(1 for a in analyzed if a.get("is_price_inquiry"))
    all_keywords, all_pain_points, all_mentions = [], [], []
    for a in analyzed:
        all_keywords.extend(a.get("keywords") or [])
        all_pain_points.extend(a.get("pain_points") or [])
        all_mentions.extend(a.get("product_mentions") or [])
    return {
        "overall_sentiment": round(overall, 3),
        "sentiment_label": _sentiment_label(overall),
        "top_keywords": [w for w, _ in Counter(all_keywords).most_common(15)],
        "top_pain_points": [w for w, _ in Counter(all_pain_points).most_common(10)],
        "top_product_mentions": [w for w, _ in Counter(all_mentions).most_common(10)],
        "comment_count": len(analyzed),
        "positive_pct": round(positive_count / len(analyzed) * 100, 1),
        "negative_pct": round(negative_count / len(analyzed) * 100, 1),
        "price_inquiry_count": price_inquiry_count,
        "price_inquiry_pct": round(price_inquiry_count / len(analyzed) * 100, 1),
    }


def _sentiment_label(score: float) -> str:
    if score >= 0.3: return "Rat tich cuc"
    elif score >= 0.1: return "Tich cuc"
    elif score <= -0.3: return "Rat tieu cuc"
    elif score <= -0.1: return "Tieu cuc"
    return "Trung lap"
