import os
import re
from pathlib import Path
from backend.config import DATA_DIR, IMAGES_DIR, log
from backend.scraper import fetch_product_images, clean_sku
from backend.sync.local_reader import get_local_catalog, get_grouped_catalog

ARTICLE_FIC = DATA_DIR / "Article.FIC"

def extract_skus_from_db() -> list[str]:
    """Extract all unique parent model SKUs from GestCaisse database."""
    grouped = get_grouped_catalog()
    return list(grouped.keys())

def sync_missing_images(max_count: int = None) -> int:
    """
    Scan GestCaisse and automatically fetch up to 3 candidate images for each parent model.
    Variations of the same model share the images folder, avoiding duplicate downloads.
    """
    grouped = get_grouped_catalog()
    parent_skus = list(grouped.keys())
    log(f"\n📦 Found {len(parent_skus)} unique product models in GestCaisse database.")

    downloaded_folders = 0
    skipped = 0

    for i, sku in enumerate(parent_skus):
        if max_count and downloaded_folders >= max_count:
            break

        safe_name = "".join(c if c.isalnum() else "_" for c in sku)
        target_folder = IMAGES_DIR / safe_name

        existing_images = list(target_folder.glob("*.jpg")) if target_folder.exists() else []
        if len(existing_images) >= 3:
            skipped += 1
            continue

        log(f"\n[{i+1}/{len(parent_skus)}] Auto-fetching images for model: '{sku}'...")
        res = fetch_product_images(sku, max_images=3)
        if res.get("images"):
            downloaded_folders += 1

    log(f"\n✨ Sync completed! Processed: {downloaded_folders} SKU folders | Skipped (already have 3 images): {skipped}")
    return downloaded_folders
