import os
import re
import hashlib
from pathlib import Path
from backend.config import DATA_DIR, IMAGES_DIR, log
from backend.scraper import parse_sku_and_size

import struct

ARTICLE_FIC = DATA_DIR / "Article.FIC"
PRIX_FIC = DATA_DIR / "prix.FIC"

def parse_prices_from_db() -> dict[str, float]:
    """
    Parses prix.FIC and returns a dictionary of SKU -> Exact Retail Price (TTC in MAD).
    GestCaisse HyperFileSQL stores 64-bit micro-unit integers (val / 1e6)
    with the retail price located at rec[329:337].
    """
    if not PRIX_FIC.exists():
        return {}

    prices = {}
    try:
        with open(PRIX_FIC, "rb") as f:
            data = f.read()

        matches = list(re.finditer(b'[A-Z0-9]{4,8}[- ][A-Z0-9]{3,5}', data))
        for m in matches:
            idx = m.start()
            rec = data[idx:idx+360]
            sku_raw = rec[:30].decode('latin1', 'ignore').split('\x00')[0].strip()
            if not sku_raw:
                continue

            clean_ref = re.sub(r'[\s;\.]+$', '', sku_raw).strip().upper()
            parent_sku, _ = parse_sku_and_size(clean_ref)

            if len(rec) >= 337:
                raw_int = struct.unpack('<q', rec[329:337])[0]
                price_ttc = raw_int / 1000000.0
                if 20.0 <= price_ttc <= 15000.0 and raw_int != 4294967296:
                    prices[clean_ref] = float(price_ttc)
                    if parent_sku not in prices or prices[parent_sku] == 0:
                        prices[parent_sku] = float(price_ttc)

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
