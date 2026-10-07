"""
Fashion Analyzer — Women's fashion market research module.
Target audience: female shoppers aged 22–35 on Shopee Vietnam.
All text dictionaries are transliterated (no diacritics) for ASCII safety.
"""
from collections import Counter
from typing import Optional

# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

FASHION_SUBCATEGORIES: dict[str, str] = {
    "ao_kieu":    "Ao kieu nu",
    "ao_thun":    "Ao thun nu",
    "ao_so_mi":   "Ao so mi nu",
    "ao_khoac":   "Ao khoac nu",
    "vay_dam":    "Vay dam",
    "chan_vay":   "Chan vay",
    "quan":       "Quan nu",
    "bo_do":      "Bo do nu",
    "giay":       "Giay dep nu",
    "tui_xach":   "Tui xach nu",
    "phu_kien":   "Phu kien thoi trang",
}

# Search keywords per subcategory (used for Shopee crawl sweep)
FASHION_SEARCH_KEYWORDS: dict[str, list[str]] = {
    "ao_kieu":  ["ao kieu nu", "ao blouson nu", "ao crop top nu", "ao len nu co tron"],
    "ao_thun":  ["ao thun nu", "ao thun oversize nu", "ao thun basic nu"],
    "ao_so_mi": ["ao so mi nu", "ao so mi tay bong", "ao so mi cong so nu"],
    "ao_khoac": ["ao khoac nu", "ao khoac jean nu", "ao blazer nu"],
    "vay_dam":  ["dam nu", "vay dam nu", "dam maxi", "dam mini", "dam du tiec nu", "dam di lam nu"],
    "chan_vay": ["chan vay nu", "chan vay chu a", "chan vay midi", "chan vay xep li"],
    "quan":     ["quan jean nu", "quan kaki nu", "quan short nu", "quan culottes nu"],
    "bo_do":    ["set do nu", "bo do nu", "bo do mac nha nu"],
    "giay":     ["giay cao got nu", "giay block heel", "giay sandal nu", "giay slip on nu", "giay sneaker nu"],
    "tui_xach": ["tui xach nu", "tui tote nu", "tui deo cheo nu", "tui bucket nu", "vi nu"],
    "phu_kien": ["vong co nu", "khuyen tai nu", "vong tay nu", "nhan nu thoi trang"],
}

# Flat list of all fashion keywords for trending sweep
ALL_FASHION_KEYWORDS: list[str] = [kw for kws in FASHION_SEARCH_KEYWORDS.values() for kw in kws]

# ---------------------------------------------------------------------------
# Style trends (popular among 22-35 Vietnamese women)
# ---------------------------------------------------------------------------

STYLE_TRENDS: dict[str, list[str]] = {
    "basic_co_dien": [
        "basic", "toi gian", "co dien", "minimalist", "thanh lich",
        "den trang", "don sac", "clean",
    ],
    "cong_so": [
        "di lam", "cong so", "formal", "lich su", "van phong",
        "office lady", "smart casual",
    ],
    "oversize_casual": [
        "oversize", "rong thoai", "comfort", "luoi bieng", "casual",
        "comfy", "co gian", "thoai mai",
    ],
    "y2k_retro": [
        "y2k", "retro", "vintage", "thap nien 2000", "co dien",
        "80s", "90s", "co",
    ],
    "sang_chanh_luxury": [
        "sang chanh", "cao cap", "luxury", "satin", "lua",
        "bling", "bong bay", "fancy",
    ],
    "du_lich_resort": [
        "du lich", "bien", "resort", "mua he", "tropical",
        "bo bien", "nghi duong", "phuot",
    ],
    "boho_romantic": [
        "boho", "hoa", "nu tinh", "romantic", "tu do",
        "mong mo", "maxi hoa", "voan",
    ],
    "streetwear_the_thao": [
        "streetwear", "the thao", "gym", "sport", "active",
        "hop rap", "sneaker", "jogger",
    ],
}

# ---------------------------------------------------------------------------
# Occasions (important for content/affiliate copy direction)
# ---------------------------------------------------------------------------

OCCASIONS: dict[str, list[str]] = {
    "hang_ngay":  ["hang ngay", "di choi", "di dao", "thuong ngay", "weekend", "di cafe"],
    "di_lam":     ["di lam", "van phong", "cong so", "hop", "gap khach", "hoi nghi"],
    "hen_ho":     ["hen ho", "date", "di choi voi ban trai", "romantic dinner", "buoi toi"],
    "tiec_su_kien": ["du tiec", "cuoi", "sinh nhat", "su kien", "dalo", "buffet"],
    "du_lich":    ["du lich", "bien", "resort", "phuot", "di chuyen", "mang di xa"],
    "the_thao":   ["gym", "yoga", "chay bo", "the thao", "tap luyen", "pilates"],
    "o_nha":      ["o nha", "mac nha", "do mac nha", "thoai mai", "do ngu"],
}

# ---------------------------------------------------------------------------
# Sentiment: fashion-specific positive / negative signals
# ---------------------------------------------------------------------------

FASHION_POSITIVE: set[str] = {
    # Appearance
    "dep", "xinh", "sang", "chat", "xit", "dinh", "xin xo", "cute",
    "tre trung", "nu tinh", "thanh lich", "sang chanh", "hack dang",
    "ton dang", "gau hon", "cao hon",
    # Fit
    "vua vat", "vua nguoi", "mac len dep", "om nguoi", "dang dep",
    "ton dang", "mac len hon hinh",
    # Quality
    "vai day", "vai mem", "vai mat", "co gian tot", "ben mau",
    "duong may dep", "ky cao", "chat lieu tot", "khong nhan",
    # Value
    "dang tien", "gia tot", "re ma dep", "xung dang", "hoan hao",
    "qua xin", "yeu lam",
    # Shop/delivery
    "goi dep", "dong goi ca", "ship nhanh", "hang dung mo ta",
    "shop nhiet tinh", "ho tro tot",
}

FASHION_NEGATIVE: set[str] = {
    # Size (most common complaint in fashion)
    "size nho", "size lon", "nho hon tuong", "lon hon tuong",
    "khong vua", "so do sai", "size ao", "size sai",
    # Color mismatch
    "mau khac hinh", "mau nhat hon", "mau sap", "khac mau",
    "anh ao", "khac xa thuc te", "mau khong chuan",
    # Fabric quality
    "vai mong", "vai xau", "de bai", "de hong", "co dat",
    "nong buc", "kho chiu", "chet mau", "phai mau",
    # Stitching/finish
    "duong may xau", "net chi", "khong ky cao", "thieu sot",
    # Fit issues
    "khong co dan hoi", "bung bung", "cang nguoi", "khong co form",
    "khong ton dang", "mac len khong dep",
    # Mismatch with listing
    "khong dung mo ta", "khac anh", "hang ao", "khong nhu y",
    # Return/complaint
    "that vong", "tra hang", "khieu nai", "hoan tien",
}

# ---------------------------------------------------------------------------
# Buying intent signals (complement PRICE_INQUIRY_KEYWORDS)
# ---------------------------------------------------------------------------

FASHION_BUY_SIGNALS: set[str] = {
    "order duoc khong", "dat hang nhu the nao", "link mua", "mua o dau",
    "shop con size khong", "con mau nao khong", "con hang khong",
    "xin gia", "bao nhieu tien", "gia ban", "bao nhieu",
    "ship ve", "ship toan quoc", "free ship khong",
    "chot", "chot don", "chot lien", "mua ngay",
    "them vao gio hang", "add to cart",
    "code giam gia", "ma giam", "sale khong",
}

# ---------------------------------------------------------------------------
# Price segments (VND) tuned for 22-35 female buyers
# ---------------------------------------------------------------------------

PRICE_SEGMENTS: dict[str, tuple] = {
    "sieu_re":   (0,          150_000),       # flash sale / básic
    "binh_dan":  (150_000,    350_000),       # everyday wear sweet spot
    "trung_cap": (350_000,    800_000),       # quality casual / work
    "kha":       (800_000,  2_000_000),       # premium / occasion
    "cao_cap":   (2_000_000, float("inf")),   # luxury
}

PRICE_SEGMENT_LABELS: dict[str, str] = {
    "sieu_re":   "Sieu re (<150k)",
    "binh_dan":  "Binh dan (150-350k)",
    "trung_cap": "Trung cap (350-800k)",
    "kha":       "Kha (800k-2tr)",
    "cao_cap":   "Cao cap (>2tr)",
}

# ---------------------------------------------------------------------------
# Core analysis functions
# ---------------------------------------------------------------------------

def detect_styles(text: str) -> list[str]:
    """Return list of matching style trend keys found in text."""
    if not text:
        return []
    lower = text.lower()
    return [style for style, kws in STYLE_TRENDS.items() if any(kw in lower for kw in kws)]


def detect_occasions(text: str) -> list[str]:
    """Return list of matching occasion keys found in text."""
    if not text:
        return []
    lower = text.lower()
    return [occ for occ, kws in OCCASIONS.items() if any(kw in lower for kw in kws)]


def classify_price_segment(price_vnd: float) -> str:
    """Return price segment key for a given price in VND."""
    for seg, (lo, hi) in PRICE_SEGMENTS.items():
        if lo <= price_vnd < hi:
            return seg
    return "cao_cap"


def has_buy_signal(text: str) -> bool:
    """Return True if the text contains a fashion buying-intent signal."""
    if not text:
        return False
    lower = text.lower()
    return any(sig in lower for sig in FASHION_BUY_SIGNALS)


def analyze_fashion_sentiment(text: str) -> dict:
    """Extended sentiment analysis tuned for fashion comments."""
    if not text or not text.strip():
        return {"score": 0.0, "label": "trung_lap", "pos_signals": [], "neg_signals": []}
    lower = text.lower()
    pos = [w for w in FASHION_POSITIVE if w in lower]
    neg = [w for w in FASHION_NEGATIVE if w in lower]
    total = len(pos) + len(neg)
    score = round((len(pos) - len(neg)) / total, 3) if total else 0.0
    label = (
        "rat_tich_cuc" if score >= 0.4 else
        "tich_cuc"     if score >= 0.1 else
        "rat_tieu_cuc" if score <= -0.4 else
        "tieu_cuc"     if score <= -0.1 else
        "trung_lap"
    )
    return {"score": score, "label": label, "pos_signals": pos[:5], "neg_signals": neg[:5]}


def analyze_fashion_comment(comment: dict) -> dict:
    content = comment.get("content") or ""
    sentiment = analyze_fashion_sentiment(content)
    return {
        **comment,
        "sentiment_score":  sentiment["score"],
        "sentiment_label":  sentiment["label"],
        "pos_signals":      sentiment["pos_signals"],
        "neg_signals":      sentiment["neg_signals"],
        "styles":           detect_styles(content),
        "occasions":        detect_occasions(content),
        "has_buy_signal":   has_buy_signal(content),
    }


def analyze_fashion_comments_batch(comments: list[dict]) -> dict:
    """
    Full fashion comment batch analysis.
    Returns rich insights for affiliate content planning (22-35 female buyers).
    """
    if not comments:
        return _empty_batch()

    analyzed = [analyze_fashion_comment(c) for c in comments]
    n = len(analyzed)

    scores     = [a["sentiment_score"] for a in analyzed]
    overall    = round(sum(scores) / n, 3)
    pos_count  = sum(1 for s in scores if s > 0.1)
    neg_count  = sum(1 for s in scores if s < -0.1)
    buy_count  = sum(1 for a in analyzed if a["has_buy_signal"])

    # Aggregate styles and occasions
    all_styles = [s for a in analyzed for s in a["styles"]]
    all_occ    = [o for a in analyzed for o in a["occasions"]]
    all_pos    = [sig for a in analyzed for sig in a["pos_signals"]]
    all_neg    = [sig for a in analyzed for sig in a["neg_signals"]]

    # Top pain points (negative signals grouped)
    size_complaints  = sum(1 for a in analyzed if any(s in ["size nho","size lon","khong vua","so do sai","nho hon tuong","lon hon tuong"] for s in a["neg_signals"]))
    color_complaints = sum(1 for a in analyzed if any(s in ["mau khac hinh","mau nhat hon","khac mau","anh ao"] for s in a["neg_signals"]))
    fabric_complaints= sum(1 for a in analyzed if any(s in ["vai mong","vai xau","co dat","nong buc","chet mau"] for s in a["neg_signals"]))

    return {
        "comment_count":      n,
        "overall_sentiment":  overall,
        "sentiment_label":    _sentiment_label(overall),
        "positive_pct":       round(pos_count / n * 100, 1),
        "negative_pct":       round(neg_count / n * 100, 1),
        "buy_signal_pct":     round(buy_count / n * 100, 1),
        "buy_signal_count":   buy_count,
        "top_styles":         [s for s, _ in Counter(all_styles).most_common(5)],
        "top_occasions":      [o for o, _ in Counter(all_occ).most_common(5)],
        "top_pos_signals":    [s for s, _ in Counter(all_pos).most_common(8)],
        "top_neg_signals":    [s for s, _ in Counter(all_neg).most_common(8)],
        "pain_points": {
            "size_complaints":   round(size_complaints / n * 100, 1),
            "color_complaints":  round(color_complaints / n * 100, 1),
            "fabric_complaints": round(fabric_complaints / n * 100, 1),
        },
    }


def score_product_for_fashion(product: dict) -> float:
    """
    Affiliate opportunity score for women's fashion (0-100).
    Combines trending score + price sweet spot bonus + commission.
    """
    base       = product.get("trending_score") or 0
    price      = product.get("price_min") or product.get("price") or 0
    commission = product.get("commission_rate") or 0

    seg = classify_price_segment(price)
    price_bonus = {"binh_dan": 15, "trung_cap": 20, "kha": 10, "sieu_re": 5, "cao_cap": 0}.get(seg, 0)
    comm_bonus  = min(commission * 2, 20)  # max +20 from commission

    return round(min(base + price_bonus + comm_bonus, 100), 2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sentiment_label(score: float) -> str:
    if score >= 0.3:  return "Rat tich cuc"
    if score >= 0.1:  return "Tich cuc"
    if score <= -0.3: return "Rat tieu cuc"
    if score <= -0.1: return "Tieu cuc"
    return "Trung lap"


def _empty_batch() -> dict:
    return {
        "comment_count": 0, "overall_sentiment": 0.0, "sentiment_label": "Trung lap",
        "positive_pct": 0, "negative_pct": 0,
        "buy_signal_pct": 0, "buy_signal_count": 0,
        "top_styles": [], "top_occasions": [], "top_pos_signals": [], "top_neg_signals": [],
        "pain_points": {"size_complaints": 0, "color_complaints": 0, "fabric_complaints": 0},
    }
