import os
import re
import hashlib
from pathlib import Path
from backend.config import DATA_DIR, IMAGES_DIR, log
from backend.scraper import parse_sku_and_size

ARTICLE_FIC = DATA_DIR / "Article.FIC"
PRIX_FIC = DATA_DIR / "prix.FIC"

def parse_prices_from_db() -> dict[str, float]:
    """
    Parses prix.FIC and returns a dictionary of SKU -> Price.
    Uses the 360-byte stride record layout of HyperFileSQL.
    """
    if not PRIX_FIC.exists():
        return {}

    prices = {}
    try:
        with open(PRIX_FIC, "rb") as f:
            data = f.read()

        # Find all SKU references in prix.FIC
        matches = [m.start() for m in re.finditer(b'[A-Z0-9]{4,8}[- ][A-Z0-9]{3,5}', data)]
        for idx in matches:
            rec = data[idx-10:idx+350]
            sku_raw = data[idx:idx+30].decode('latin1', 'ignore').split('\x00')[0].strip()
            if not sku_raw:
                continue

            # In GestCaisse, price is encoded in byte 322 or BCD/int
            # E.g. byte 322 has values like 79, 89, 69 for 790/890/690 DH
            if len(rec) >= 330:
                raw_byte = rec[322]
                if 10 <= raw_byte <= 250:
                    # In apparel retail, 79 -> 790 DH / 79 EUR
                    # We store the base value
                    prices[sku_raw.upper()] = float(raw_byte * 10)
    except Exception as e:
        log(f"⚠️ Error parsing prix.FIC: {e}")

    return prices

def get_local_catalog() -> list[dict]:
    """
    Reads Article.FIC and extracts all articles with their code, reference,
    barcode, size, parent SKU, local images, and prices.
    Returns: list of dicts.
    """
    if not ARTICLE_FIC.exists():
        log(f"⚠️ Database file not found: {ARTICLE_FIC}")
        return []

    prices = parse_prices_from_db()

    try:
        with open(ARTICLE_FIC, "rb") as f:
            data = f.read()

        matches = [m.start() for m in re.finditer(b'AR[0-9]{7}', data)]
        articles = []

        for idx in matches:
            code_art = data[idx:idx+9].decode('latin1', 'ignore').strip()
            raw_desig = data[idx-85:idx-10].decode('latin1', 'ignore').split('\x00')[0].strip()
            raw_barcode = data[idx+51:idx+75].decode('latin1', 'ignore').split('\x00')[0].strip()

            if not raw_desig:
                continue

            parent_sku, size = parse_sku_and_size(raw_desig)
            parent_safe = "".join(c if c.isalnum() else "_" for c in parent_sku.strip())
            raw_safe = "".join(c if c.isalnum() else "_" for c in raw_desig.strip())

            # Check for local images in parent folder or raw folder
            img_dir = IMAGES_DIR / parent_safe
            if not img_dir.exists():
                img_dir = IMAGES_DIR / raw_safe

            local_images = []
            if img_dir.exists():
                local_images = [str(p) for p in sorted(img_dir.glob("*.jpg")) if p.stat().st_size > 2000]

            # Price lookup
            price = prices.get(raw_desig.upper(), prices.get(parent_sku.upper(), 0.0))

            articles.append({
                "article_code": code_art,
                "reference": raw_desig,
                "parent_sku": parent_sku,
                "size": size,
                "barcode": raw_barcode if len(raw_barcode) >= 6 else "",
                "price": price,
                "images": local_images,
                "in_stock": True
            })

        return articles
    except Exception as e:
        log(f"❌ Error reading local catalog from Article.FIC: {e}")
        return []

def get_grouped_catalog() -> dict[str, dict]:
    """
    Groups individual articles into Parent Models with size variations.
    Ideal for WooCommerce Variable Products or synchronized collections.
    """
    articles = get_local_catalog()
    grouped = {}

    for item in articles:
        parent = item["parent_sku"]
        if parent not in grouped:
            grouped[parent] = {
                "parent_sku": parent,
                "title": parent,
                "images": item["images"],
                "price": item["price"],
                "variations": []
            }

        if not grouped[parent]["images"] and item["images"]:
            grouped[parent]["images"] = item["images"]

        if not grouped[parent]["price"] and item["price"]:
            grouped[parent]["price"] = item["price"]

        grouped[parent]["variations"].append({
            "article_code": item["article_code"],
            "sku": item["reference"],
            "size": item["size"],
            "barcode": item["barcode"],
            "price": item["price"]
        })

    return grouped

def compute_catalog_hash(catalog: list[dict]) -> str:
    """Computes MD5 hash of catalog items to quickly detect data changes."""
    content = "|".join(f"{a['article_code']}:{a['reference']}:{a['price']}:{a['barcode']}" for a in catalog)
    return hashlib.md5(content.encode("utf-8")).hexdigest()
