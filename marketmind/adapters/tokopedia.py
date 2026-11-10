"""Import the Tokopedia Product and Review Dataset as MarketMind data (real reviews and catalogue rows).

Source: https://www.kaggle.com/datasets/musabiam/tokopedia-product-and-review-dataset - 5,553 Tokopedia products in 24
categories with about 1M reviews, scraped in 2025, licensed CC BY-NC 4.0 ("for research and educational purposes
only"). Download archive.zip yourself (Kaggle needs an account); this module reads it and never downloads anything.

The archive holds tokopedia_products_with_review.csv (one row per product, review fields as position-aligned lists)
and a JSON copy. The importer:

1. reads the CSV in chunks and keeps beauty products ("Kecantikan|..."), so the review lists of the other 23
   categories are never parsed;
2. keeps the facial-skincare products, recognising MarketMind's five categories from the product name;
3. derives each product's brand from its name, checked against the shop's other products (official stores sell one
   brand), with an optional brand map for corrections;
4. explodes the review lists into one row per review and writes product_reviews.csv and product_catalog.csv in
   MarketMind's row contracts, plus manifest.json and a crosswalk of review IDs.

Fields the source does not have are marked, never invented: reviewer skin type, halal and BPOM status, launch month
and pack size are null unless the product name states them, and the region is the seller's shop location.
"""
from __future__ import annotations

import ast
import json
import re
import time
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd

SOURCE = ("Tokopedia Product and Review Dataset (Kaggle: musabiam/tokopedia-product-and-review-dataset, "
          "scraped 2025)")
LICENCE = "CC BY-NC 4.0, for research and education only; do not redistribute the files"
CSV_MEMBER = "tokopedia_products_with_review.csv"
PRODUCT_COLS = ["product_id", "category", "name", "count_sold", "price", "discounted_price", "rating_average",
                "shop_id", "shop_location", "is_official"]
REVIEW_COLS = ["review_id", "message", "review_rating", "review_time", "review_timestamp", "review_like",
               "variant_name", "bad_rating_reason"]

# product-name keywords per MarketMind category, checked in this order (a "sunscreen serum" is a sunscreen)
CATEGORY_RULES = [
    ("Sunscreen", r"sun ?screen|sun ?block|tabir surya|\bspf ?\d|uv (?:shield|protect|defen[cs]e)|sun (?:serum|gel|stick|essence)"),
    ("Facial Wash", r"facial ?wash|face ?wash|facial (?:foam|cleanser)|cleanser|cleansing (?:foam|gel)|sabun (?:muka|wajah)|"
                    r"pembersih wajah|micellar|face ?soap"),
    ("Toner", r"\btoner\b"),
    ("Serum", r"\bserum\b|\bessence\b|\bampoule\b|\bbooster\b"),
    ("Moisturizer", r"moisturi[sz]|pelemba[bp]|day cream|night cream|gel cream|face cream|cream wajah|krim wajah|"
                    r"(?:cream|krim) (?:malam|siang|pagi)|water ?gel|barrier (?:cream|gel)|\bmoist\b"),
]
NOT_FACIAL = re.compile(r"\bbody\b|badan|\bhand\b|tangan|\bfoot\b|\bkaki\b|\blip(?:s|stick| balm| tint)?\b|bibir|"
                        r"\bhair\b|rambut|shampoo|deodor|parfum|perfume|cushion|foundation|bedak|powder|mascara|"
                        r"eyeliner|blush|\bmask\b|masker", re.I)
INGREDIENTS = ["niacinamide", "ceramide", "hyaluronic acid", "salicylic acid", "centella", "retinol", "vitamin c",
               "peptide", "alpha arbutin", "tranexamic acid", "panthenol", "mugwort", "tea tree", "aha", "bha",
               "collagen", "snail", "galactomyces", "rice", "aloe vera", "propolis", "squalane"]
NOISE = re.compile(r"^(?:\[[^\]]*\]|\([^)]*\)|\{[^}]*\}|paket|bundl\w*|promo|sale|ready|ori(?:ginal)?|official|new|"
                   r"free\w*|bpom|halal|100%|\d+\s*pcs|\d+pcs|best ?seller)\s*[-:|]?\s*", re.I)
REGIONS = [
    ("DKI Jakarta & Banten", "jakarta|tangerang|serang|cilegon|banten|kepulauan seribu"),
    ("Jawa Barat", "bandung|bekasi|bogor|depok|cimahi|cirebon|sukabumi|tasikmalaya|karawang|purwakarta|garut|cianjur|"
                   "subang|indramayu|kuningan|majalengka|sumedang|ciamis|banjar|jawa barat"),
    ("Jawa Tengah & DIY", "semarang|solo|surakarta|yogya|jogja|sleman|bantul|magelang|salatiga|pekalongan|tegal|kudus|"
                          "purwokerto|banyumas|klaten|sukoharjo|boyolali|jepara|demak|kendal|cilacap|kebumen|wonosobo|"
                          "temanggung|kulon progo|gunung ?kidul|purworejo|pati|rembang|blora|grobogan|sragen|"
                          "karanganyar|wonogiri|jawa tengah"),
    ("Jawa Timur", "surabaya|malang|sidoarjo|gresik|kediri|madiun|mojokerto|pasuruan|probolinggo|jember|banyuwangi|"
                   "blitar|batu|tulungagung|lamongan|tuban|bojonegoro|jombang|nganjuk|ponorogo|madura|bangkalan|"
                   "lumajang|situbondo|bondowoso|magetan|ngawi|pacitan|trenggalek|sampang|pamekasan|sumenep|jawa timur"),
    ("Sumatera", "medan|palembang|pekanbaru|padang|lampung|jambi|bengkulu|batam|aceh|pangkal ?pinang|bangka|riau|"
                 "sumatera|sumatra|deli serdang|binjai|tanjung ?pinang|bukittinggi|dumai|lubuk ?linggau|siantar"),
    ("Kalimantan & Sulawesi", "makassar|manado|balikpapan|samarinda|pontianak|banjarmasin|palangka ?raya|kendari|palu|"
                              "gorontalo|tarakan|kalimantan|sulawesi|bontang|mamuju|bitung|pare ?pare"),
    ("Bali & Indonesia Timur", "denpasar|bali|badung|gianyar|mataram|lombok|kupang|ambon|jayapura|sorong|ternate|"
                               "nusa tenggara|papua|maluku|manokwari|merauke|bima"),
]


# ------------------------------------------------------------------------------------------------ parsing helpers
def parse_list(cell) -> list:
    """A review-list cell: a real list (JSON copy) or its text in the CSV, written as JSON or as a Python list."""
    if isinstance(cell, list):
        return cell
    if cell is None or (isinstance(cell, float) and pd.isna(cell)) or str(cell).strip() in ("", "[]", "nan"):
        return []
    text = str(cell)
    for parse in (json.loads, ast.literal_eval):
        try:
            value = parse(text)
            return list(value) if isinstance(value, (list, tuple)) else [value]
        except (ValueError, SyntaxError, TypeError):
            continue
    return []


def money(value) -> int | None:
    """'Rp45.000', '45.000', '1.250.000', '45000' or '45000.0' -> rupiah as an integer."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).replace("Rp", "").replace(" ", "").strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", s) and not re.fullmatch(r"\d{1,3}\.\d{3}", s):
        return int(float(s))            # plain number, possibly with a decimal part
    digits = re.sub(r"\D", "", s.split(",")[0])   # dots as thousands separators, comma before the decimals
    return int(digits) if digits else None


def review_date(timestamp, epoch) -> str | None:
    """ISO date from the review timestamp text, or from the review time when it is a Unix epoch."""
    if timestamp not in (None, "") and not (isinstance(timestamp, float) and pd.isna(timestamp)):
        d = pd.to_datetime(str(timestamp), errors="coerce", utc=True)
        if pd.notna(d):
            return d.date().isoformat()
    try:
        e = float(epoch)
    except (TypeError, ValueError):
        return None
    if e > 1e12:
        e /= 1000
    return pd.Timestamp(e, unit="s").date().isoformat() if e > 1e9 else None


def facial_category(name: str) -> str | None:
    text = str(name).lower()
    if NOT_FACIAL.search(text):
        return None
    for category, pattern in CATEGORY_RULES:
        if re.search(pattern, text):
            return category
    return None


def region(location) -> str:
    text = str(location or "").lower()
    for name, pattern in REGIONS:
        if re.search(pattern, text):
            return name
    return "Unknown"


def clean_name(name: str) -> str:
    text = str(name).strip()
    for _ in range(4):
        text = NOISE.sub("", text).strip()
    return text or str(name).strip()


def derive_brands(products: pd.DataFrame, brand_map: dict[str, str] | None = None) -> pd.Series:
    """Brand per product: the leading words its shop's product names share; official stores sell one brand.

    For each shop, the longest run of leading words (up to three) that at least half of its products start with is
    the brand; a shop with one product, or with no shared prefix, falls back to the product's first word. A brand map
    (regular expression on the name -> brand) overrides the result, for brands the rule gets wrong.
    """
    words = products["name"].map(lambda n: clean_name(n).split())
    brands = pd.Series(index=products.index, dtype=object)
    for _, idx in products.groupby("shop_id").groups.items():
        shop = words.loc[idx]
        prefix = []
        for k in range(1, 4):
            heads = Counter(" ".join(w[:k]).lower() for w in shop if len(w) >= k)
            if not heads:
                break
            head, n = heads.most_common(1)[0]
            if n < max(2, 0.5 * len(shop)):
                break
            prefix = head.split()
        for i in idx:
            w = words.loc[i]
            if prefix and [x.lower() for x in w[:len(prefix)]] == prefix:
                brands.loc[i] = " ".join(w[:len(prefix)])
            else:
                brands.loc[i] = w[0] if w else "Unknown"
    brands = brands.map(lambda b: b if any(c.islower() for c in b) or len(b) <= 4 else b.title())
    # one spelling per brand: the most common way its products write it ("SOMETHINC", "Somethinc" -> "Somethinc")
    spelling = {key: group.value_counts().index[0] for key, group in brands.groupby(brands.str.lower())}
    brands = brands.map(lambda b: spelling[b.lower()])
    for pattern, brand in (brand_map or {}).items():
        brands[products["name"].str.contains(pattern, case=False, regex=True)] = brand
    return brands


# ------------------------------------------------------------------------------------------------ reading the source
def read_beauty_products(path: Path, chunksize: int = 200) -> pd.DataFrame:
    """Beauty products from archive.zip, the CSV inside it, or the JSON copy, with review fields as lists."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        records = json.loads(path.read_text(encoding="utf-8"))
        df = pd.DataFrame(records if isinstance(records, list) else records.get("data", records))
        return _beauty(df)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            member = next((n for n in names if n.endswith(CSV_MEMBER)), None) or next((n for n in names if n.endswith(".csv")), None)
            if member is None:
                json_member = next((n for n in names if n.endswith(".json")), None)
                if json_member is None:
                    raise ValueError(f"{path} holds neither {CSV_MEMBER} nor a JSON copy")
                df = pd.DataFrame(json.loads(z.read(json_member).decode("utf-8")))
                return _beauty(df)
            with z.open(member) as f:
                return _read_csv(f, chunksize)
    with open(path, "rb") as f:
        return _read_csv(f, chunksize)


def _read_csv(handle, chunksize: int) -> pd.DataFrame:
    wanted = set(PRODUCT_COLS + REVIEW_COLS)
    parts = [_beauty(chunk) for chunk in pd.read_csv(handle, chunksize=chunksize, usecols=lambda c: c.strip() in wanted,
                                                     dtype=str, keep_default_na=False)]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=PRODUCT_COLS + REVIEW_COLS)


def _beauty(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=lambda c: str(c).strip())
    keep = df["category"].astype(str).str.lower().str.startswith("kecantikan")
    return df[keep].copy()


# ------------------------------------------------------------------------------------------------ the conversion
def convert(products: pd.DataFrame, brand_map: dict[str, str] | None = None, min_reviews: int = 1,
            max_products: int = 999) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Beauty products with review lists -> (reviews, catalogue, review-id crosswalk, statistics)."""
    stats = dict(beauty_products=len(products))
    products = products.copy()
    for col in PRODUCT_COLS:                      # tolerate a copy that lacks optional product fields
        if col not in products:
            products[col] = None
    products["mm_category"] = products["name"].map(facial_category)
    products = products[products["mm_category"].notna()].copy()
    stats["facial_skincare_products"] = len(products)
    for col in REVIEW_COLS:
        products[col] = products[col].map(parse_list) if col in products else [[] for _ in range(len(products))]
    products["n_reviews"] = products["review_id"].map(len)
    products = products[products["n_reviews"] >= min_reviews]
    products = products.sort_values("n_reviews", ascending=False).head(max_products).reset_index(drop=True)
    products["brand"] = derive_brands(products, brand_map)
    products["sku_id"] = [f"SKU-{i + 1:03d}" for i in range(len(products))]

    rows, cross = [], []
    for p in products.itertuples(index=False):
        reg = region(p.shop_location)
        n = len(p.review_id)
        field = {c: (getattr(p, c) + [None] * n)[:n] for c in REVIEW_COLS}   # lists are position-aligned
        for k in range(n):
            rating = pd.to_numeric(field["review_rating"][k], errors="coerce")
            date = review_date(field["review_timestamp"][k], field["review_time"][k])
            if pd.isna(rating) or not 1 <= int(rating) <= 5 or date is None:
                continue
            text = str(field["message"][k] or "").strip()
            likes = pd.to_numeric(field["review_like"][k], errors="coerce")
            rid = f"R{len(rows) + 1:06d}"
            rows.append(dict(review_id=rid, review_date=date, brand=p.brand, sku_id=p.sku_id, product_name=str(p.name).strip(),
                             category=p.mm_category, channel="Tokopedia", region=reg, rating=int(rating),
                             review_text=text or None, helpful_votes=int(likes) if pd.notna(likes) and likes >= 0 else 0,
                             verified_purchase=True, reviewer_id=f"U{len(rows) + 1:06d}", reviewer_skin_type=None))
            cross.append(dict(review_id=rid, source_review_id=str(field["review_id"][k]), source_product_id=str(p.product_id)))
    reviews = pd.DataFrame(rows)
    if reviews.empty:
        raise ValueError("No facial-skincare reviews with a rating and a date were found in the input.")

    counts = reviews.groupby("sku_id").size()
    cat = []
    for p in products.itertuples(index=False):
        name = str(p.name).lower()
        size = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:ml|gr|gram|g)\b", name)
        size_ml = float(size.group(1).replace(",", ".")) if size else None
        price = money(p.price)
        spf = re.search(r"spf\s*(\d{2,3})", name)
        spf = int(spf.group(1)) if spf and 15 <= int(spf.group(1)) <= 100 else None
        rating_avg = pd.to_numeric(p.rating_average, errors="coerce")
        sold = pd.to_numeric(p.count_sold, errors="coerce")
        cat.append(dict(
            sku_id=p.sku_id, brand=p.brand, product_name=str(p.name).strip(), category=p.mm_category,
            key_ingredient=next((i.title() if len(i) > 3 else i.upper() for i in INGREDIENTS
                                 if re.search(rf"\b{re.escape(i)}\b", name)), "not stated"),
            size_ml=size_ml, price_idr=price, launch_month=None,
            fragrance_free=True if re.search(r"fragrance[- ]?free|non[- ]?fragrance|no fragrance|tanpa pewangi|unscented",
                                             name) else None,
            spf=spf, price_per_ml_idr=round(price / size_ml, 1) if price and size_ml else None,
            halal_certified=True if "halal" in name else None, bpom_registered=True if "bpom" in name else None,
            rating_avg=float(rating_avg) if pd.notna(rating_avg) and 1 <= rating_avg <= 5 else None,
            review_count=int(counts.get(p.sku_id, 0)), units_sold_estimate=int(sold) if pd.notna(sold) else None))
    catalog = pd.DataFrame(cat)
    catalog = catalog[catalog["price_idr"].fillna(0) > 0].copy()
    for col in ("price_idr", "spf", "review_count", "units_sold_estimate"):   # whole numbers, gaps allowed
        catalog[col] = catalog[col].astype("Int64")
    reviews = reviews[reviews["sku_id"].isin(catalog["sku_id"])]
    stats.update(products=len(catalog), reviews=len(reviews), brands=int(catalog["brand"].nunique()),
                 reviews_with_text=int(reviews["review_text"].notna().sum()),
                 date_range=[reviews["review_date"].min(), reviews["review_date"].max()],
                 unknown_region_share=round(float((reviews["region"] == "Unknown").mean()), 3))
    return reviews, catalog, pd.DataFrame(cross), stats


def write(out: Path, reviews: pd.DataFrame, catalog: pd.DataFrame, cross: pd.DataFrame, stats: dict,
          input_path: Path) -> dict:
    """Write raw/product_reviews.csv, raw/product_catalog.csv, review_ids.csv and manifest.json under `out`."""
    out = Path(out)
    (out / "raw").mkdir(parents=True, exist_ok=True)
    reviews.to_csv(out / "raw" / "product_reviews.csv", index=False)
    catalog.to_csv(out / "raw" / "product_catalog.csv", index=False)
    cross.to_csv(out / "review_ids.csv", index=False)
    top = reviews["brand"].value_counts()
    manifest = dict(
        kind="real", source=SOURCE, licence=LICENCE, created=time.strftime("%Y-%m-%d %H:%M:%S"),
        input=Path(input_path).name, adapter="marketmind/adapters/tokopedia.py (scripts/import_tokopedia.py)",
        datasets=dict(
            reviews=dict(source=f"{SOURCE}: reviews", rows=len(reviews),
                         derived=dict(brand="leading words shared by the shop's product names",
                                      category="product-name keywords (five facial-skincare categories)",
                                      region="the seller's shop location, not the reviewer's",
                                      review_id="renumbered; review_ids.csv maps them back to the source"),
                         unknown=["reviewer_skin_type", "reviewer_id (one anonymous id per review)"]),
            catalog=dict(source=f"{SOURCE}: products", rows=len(catalog),
                         derived=dict(size_ml="pack size in the product name", spf="SPF in the product name",
                                      key_ingredient="first known ingredient named in the product name",
                                      price_idr="final price on the listing"),
                         unknown=["launch_month", "halal_certified and bpom_registered unless the name says so",
                                  "fragrance_free unless the name says so"])),
        caveats=[
            "Brands are derived from product names and shop listings; check product_catalog.csv before relying on "
            "brand comparisons, and correct mistakes with a brand map.",
            "The data covers one channel, Tokopedia, and the products the source scraped; it is not a sample of the "
            "whole market.",
            "Region is the seller's shop location, not where the reviewer lives; reviewer skin type is not in the source.",
        ],
        stats=stats, brands={b: int(n) for b, n in top.head(30).items()})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest
