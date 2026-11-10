"""Indonesian e-commerce text normalisation, tokenisation and aspect lexicon.

Marketplace reviews are full of slang ("bgt", "gak", "udh"), elongated words ("bagusss"),
emojis and code-mixing with English. Normalising them before modelling materially improves
both the TF-IDF baseline and the neural model.
"""
from __future__ import annotations

import re

SLANG = {
    "bgt": "banget", "bngt": "banget", "bangett": "banget", "yg": "yang", "ga": "tidak", "gak": "tidak",
    "nggak": "tidak", "ngga": "tidak", "enggak": "tidak", "engga": "tidak", "g": "tidak", "gk": "tidak",
    "tdk": "tidak", "udh": "sudah", "udah": "sudah", "dah": "sudah", "krn": "karena", "karna": "karena",
    "jg": "juga", "sm": "sama", "bwt": "buat", "klo": "kalau", "kalo": "kalau", "aq": "aku", "ak": "aku",
    "pk": "pakai", "pake": "pakai", "dipake": "dipakai", "cpt": "cepat", "cepet": "cepat", "dgn": "dengan",
    "trs": "terus", "tp": "tapi", "dr": "dari", "utk": "untuk", "lg": "lagi", "aja": "saja", "emg": "memang",
    "bgs": "bagus", "mantul": "mantap", "kw": "palsu", "fake": "palsu", "ori": "original", "sampe": "sampai",
    "bikin": "membuat", "gatel": "gatal", "nyengat": "menyengat", "ngefek": "berefek", "keliatan": "kelihatan",
}
NEGATIONS = {"tidak", "bukan", "belum", "kurang", "jangan", "not", "never", "dont", "didnt", "doesnt"}
EMOJI_POS = set("😍🥰👍✨💯🙏❤😊🤩👌")
EMOJI_NEG = set("😭😡😤👎😞🙁😢😠💔")
STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "ini", "itu", "aku", "saya", "kamu", "dengan", "untuk", "buat", "juga",
    "sudah", "banget", "sih", "ya", "saja", "lagi", "jadi", "karena", "ada", "nya", "pas", "kalau", "sama",
    "lebih", "bisa", "atau", "dalam", "akan", "baru", "masih", "pakai", "the", "and", "is", "it", "to", "for",
    "my", "of", "a", "in", "kak", "kok", "deh", "dong", "nih", "tuh", "memang", "terus", "tapi", "aja", "ga",
    "emopos", "emoneg", "skincarelokal", "udah", "minggu", "kali", "produk", "barang", "beli", "coba", "pertama",
    "review", "jujur", "repurchase", "hampir", "sebulan", "pemakaian", "awalnya", "ragu", "dapet", "temen",
    "rekomendasi", "yg", "ak", "aq", "will", "after", "two", "weeks", "me", "doesn", "t", "too",
    "tidak", "recommended", "not", "kecewa", "nyesel", "kapok", "semoga", "diperbaiki", "sekali",
    "malah", "padahal", "worth", "membuat", "muka", "kulit", "kulitku", "dipakai", "pakainya",
}

ASPECT_LEXICON = {
    "efektivitas": ["berefek", "efek", "hasil", "jerawat", "cerah", "glowing", "kusam", "pudar", "memudar", "dark spot",
                    "pori", "kenyal", "halus", "gosong", "belang", "lembab", "klaim", "perubahan", "bekas", "bersih",
                    "kalem", "results", "brighter", "barrier", "sehat", "kempes", "kering"],
    "tekstur": ["tekstur", "ringan", "meresap", "lengket", "berat", "greasy", "white cast", "pilling", "kental",
                "watery", "busa", "ketarik", "abu-abu", "texture", "absorbs", "adem", "nyerap", "nyaman"],
    "aroma": ["wangi", "bau", "aroma", "menyengat", "parfum", "alkohol", "smell", "smells", "scent", "pusing"],
    "kemasan": ["kemasan", "pump", "botol", "tutup", "bocor", "penyok", "packaging", "segel", "tumpah", "ringkih",
                "travel friendly", "patah"],
    "harga": ["harga", "murah", "mahal", "kemahalan", "pricey", "worth", "promo", "dupe", "budget", "value",
              "expensive", "isinya dikit", "pelajar"],
    "pengiriman": ["kirim", "pengiriman", "kurir", "packing", "seller", "telat", "delivery", "respon",
                   "bubble wrap", "packed"],
    "reaksi_kulit": ["breakout", "bruntusan", "perih", "merah", "gatal", "iritasi", "sensitif", "cocok", "berjerawat",
                     "broke me out", "gentle"],
    "keaslian": ["palsu", "asli", "original", "bpom", "barcode", "official", "beda sama yang biasa"],
    "stok": ["stok", "stock", "kosong", "sold out", "restock", "kehabisan"],
}
ASPECT_LABELS = {
    "efektivitas": "Effectiveness", "tekstur": "Texture", "aroma": "Scent", "kemasan": "Packaging",
    "harga": "Price / value", "pengiriman": "Delivery & seller", "reaksi_kulit": "Skin reaction",
    "keaslian": "Authenticity", "stok": "Stock availability",
}
_CLAUSE_SPLIT = re.compile(r"[.!?;\n]+|,\s*(?=tapi|namun|cuma|sayang|but)|\b(?:tapi|namun|cuma|sayangnya|sayang|but|however)\b")
_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def normalize(text: str) -> str:
    if not isinstance(text, str):
        return ""
    t = text.lower()
    t = re.sub(r"https?://\S+", " ", t)
    t = "".join(" emopos " if ch in EMOJI_POS else " emoneg " if ch in EMOJI_NEG else ch for ch in t)
    t = t.replace("#", " ")
    t = re.sub(r"([a-z])\1{2,}", r"\1", t)  # bagusss -> bagus
    tokens = [SLANG.get(tok, tok) for tok in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*|emopos|emoneg", t)]
    return " ".join(tokens)


def tokenize(text: str) -> list[str]:
    return normalize(text).split()


def split_clauses(text: str) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        return []
    parts = [p.strip(" ,") for p in _CLAUSE_SPLIT.split(text.lower()) if p and p.strip(" ,")]
    return [p for p in parts if len(p) > 2]


def detect_aspects(text: str) -> list[str]:
    """Lexicon-based aspect detection; single-word keys match token prefixes (harga -> harganya)."""
    norm = normalize(text)
    tokens = norm.split()
    padded = f" {norm} "
    found = []
    for aspect, keys in ASPECT_LEXICON.items():
        for k in keys:
            hit = (k in padded) if (" " in k or "-" in k) else any(t.startswith(k) for t in tokens)
            if hit:
                found.append(aspect)
                break
    return found
