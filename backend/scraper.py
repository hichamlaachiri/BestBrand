import sys
import os
import re
import json
import requests
from io import BytesIO
from PIL import Image
from backend.config import IMAGES_DIR, SERPER_API_KEY, log

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass



HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Regex to extract clothing sizes or shoe sizes from the end of SKU
SIZE_REGEX = re.compile(
    r'[\s\.\-]+('
    r'[X2-5]*[SML]|TU|ONE\s*SIZE|'  # XS, S, M, L, XL, 2XL, 3XL, TU...
    r'[0-9]{1,2}(?:[\.,][0-9]{1,2})?(?:\s*[0-9]/[0-9])?' # 38, 40, 42.5, 41 1/3, 8.5...
    r')[\.\s]*$',
    re.IGNORECASE
)

def parse_sku_and_size(raw_sku: str) -> tuple[str, str]:
    """
    Parses a reference into (parent_sku, size).
    Examples:
      'IH4302-012 S' -> ('IH4302-012', 'S')
      '6007640-110 40' -> ('6007640-110', '40')
      'HF4490-301 42.5' -> ('HF4490-301', '42.5')
      'CZ5478-001' -> ('CZ5478-001', '')
    """
    cleaned = raw_sku.strip()
    match = SIZE_REGEX.search(cleaned)
    if match:
        size = match.group(1).strip().upper()
        parent = cleaned[:match.start()].strip()
        # Clean trailing punctuation
        parent = re.sub(r'[\s\.\-_]+$', '', parent)
        if len(parent) >= 4:
            return parent, size
    return cleaned, ""

def clean_sku(raw_sku: str) -> str:
    """Normalize and strip clothing & shoe size suffixes from SKU."""
    parent_sku, _ = parse_sku_and_size(raw_sku)
    return parent_sku

def fetch_product_images(reference: str, max_images: int = 3) -> dict:
    """
    Search for reference images and download up to `max_images` into a dedicated reference folder.
    Uses the clean parent SKU for folder naming so variations share the same images.
    Returns: {"folder": str, "images": list[str], "sku": str, "parent_sku": str}
    """
    cleaned_query, extracted_size = parse_sku_and_size(reference)
    log(f"\n🔍 Searching images for reference: '{reference}' (Model SKU: '{cleaned_query}', Size: '{extracted_size}')...")

    parent_safe = "".join(c if c.isalnum() else "_" for c in cleaned_query.strip())
    raw_safe = "".join(c if c.isalnum() else "_" for c in reference.strip())

    # Prefer parent model folder, with fallback to legacy raw folder if it already has images
    target_folder = IMAGES_DIR / parent_safe
    legacy_folder = IMAGES_DIR / raw_safe
    if not target_folder.exists() and legacy_folder.exists() and list(legacy_folder.glob("*.jpg")):
        target_folder = legacy_folder

    target_folder.mkdir(parents=True, exist_ok=True)

    # Check if we already have images in the folder
    existing_images = [str(p) for p in target_folder.glob("*.jpg") if p.is_file() and p.stat().st_size > 2000]
    if len(existing_images) >= max_images:
        log(f"  ℹ️ Found {len(existing_images)} existing images in '{target_folder}'.")
        return {"folder": str(target_folder), "images": existing_images[:max_images], "sku": reference, "parent_sku": cleaned_query}

    img_urls = []

    search_term = f"Nike {cleaned_query}" if not any(b in cleaned_query.lower() for b in ("nike", "adidas", "puma", "jordan")) else cleaned_query

    # 1. Try Serper API (Google Images) if API key is present
    if SERPER_API_KEY:
        try:
            url = "https://google.serper.dev/images"
            headers = {
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json"
            }
            payload = {"q": search_term, "gl": "us", "hl": "en"}
            res = requests.post(url, headers=headers, json=payload, timeout=10)
            if res.status_code == 200:
                data = res.json()
                # Extract and cache candidate commercial title
                candidate_title = ""
                for itm in data.get("images", []):
                    t = itm.get("title")
                    if t and len(t) > 5:
                        clean_t = re.sub(r'^(Buy|Shop|Order)\s+', '', t, flags=re.IGNORECASE)
                        clean_t = re.sub(r'(@|\|)\s*(Nike|Adidas|Puma|Amazon|eBay|StockX).*$', '', clean_t, flags=re.IGNORECASE).strip()
                        if len(clean_t) > 6:
                            candidate_title = clean_t
                            break

                meta_file = target_folder / "meta.json"
                if candidate_title and not meta_file.exists():
                    try:
                        with open(meta_file, "w", encoding="utf-8") as mf:
                            json.dump({"title": candidate_title, "sku": cleaned_query}, mf, indent=2)
                    except Exception:
                        pass

                for item in data.get("images", [])[:10]:
                    u = item.get("imageUrl")
                    if u and u.startswith("http") and u not in img_urls:
                        img_urls.append(u)
        except Exception as e:
            log(f"  ⚠️ Serper API error: {e}")

    # 2. Fallback / supplement with Bing Images scraper
    if len(img_urls) < max_images:
        log("  ℹ️ Fetching additional candidates from Bing image search...")
        search_url = f"https://www.bing.com/images/search?q={requests.utils.quote(search_term)}"
        try:
            response = requests.get(search_url, headers=HEADERS, timeout=10)
            if response.status_code == 200:
                found = re.findall(r'&quot;murl&quot;:&quot;(http[^&]+)&quot;', response.text)
                for u in found:
                    if u not in img_urls:
                        img_urls.append(u)
        except Exception as e:
            log(f"  ❌ Bing search failed: {e}")

    if not img_urls:
        log(f"  ⚠️ No image search results found for '{reference}'.")
        return {"folder": str(target_folder), "images": existing_images, "sku": reference, "parent_sku": cleaned_query}

    downloaded_paths = list(existing_images)
    img_idx = len(downloaded_paths) + 1

    for url in img_urls:
        if len(downloaded_paths) >= max_images:
            break
        try:
            target_path = target_folder / f"{parent_safe}_{img_idx}.jpg"
            log(f"  📥 Downloading image #{img_idx}: {url[:75]}...")
            img_res = requests.get(url, headers=HEADERS, timeout=10)
            if img_res.status_code == 200 and len(img_res.content) > 2000:
                image = Image.open(BytesIO(img_res.content))
                if image.mode in ("RGBA", "P"):
                    image = image.convert("RGB")
                
                image.save(target_path, "JPEG", quality=92)
                
                # Gemini AI Vision verification
                from backend.gemini_assistant import is_valid_fashion_image
                if not is_valid_fashion_image(str(target_path)):
                    try:
                        target_path.unlink()
                    except Exception:
                        pass
                    continue

                log(f"  ✅ Image #{img_idx} verified & saved: {target_path}")
                downloaded_paths.append(str(target_path))
                img_idx += 1
        except Exception as e:
            log(f"  ❌ Download/processing failed: {e}")

    return {
        "folder": str(target_folder),
        "images": downloaded_paths,
        "sku": reference,
        "parent_sku": cleaned_query
    }


def fetch_product_image(reference: str) -> str | None:
    """Backward compatibility wrapper returning the folder or first image path."""
    res = fetch_product_images(reference, max_images=3)
    if res["images"]:
        return res["images"][0]
    return None

def get_product_commercial_title(sku: str) -> str:
    """
    Returns commercial title from meta.json if available, or queries Serper once.
    Falls back to SKU if not found.
    """
    cleaned_query, _ = parse_sku_and_size(sku)
    parent_safe = "".join(c if c.isalnum() else "_" for c in cleaned_query.strip())
    raw_safe = "".join(c if c.isalnum() else "_" for c in sku.strip())

    for folder_name in (parent_safe, raw_safe):
        meta_file = IMAGES_DIR / folder_name / "meta.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("title"):
                        return data["title"]
            except Exception:
                pass

    if SERPER_API_KEY:
        try:
            url = "https://google.serper.dev/images"
            headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
            payload = {"q": cleaned_query, "gl": "us", "hl": "en"}
            res = requests.post(url, headers=headers, json=payload, timeout=8)
            if res.status_code == 200:
                data = res.json()
                for itm in data.get("images", []):
                    t = itm.get("title")
                    if t and len(t) > 5:
                        clean_t = re.sub(r'^(Buy|Shop|Order)\s+', '', t, flags=re.IGNORECASE)
                        clean_t = re.sub(r'(@|\|)\s*(Nike|Adidas|Puma|Amazon|eBay|StockX).*$', '', clean_t, flags=re.IGNORECASE).strip()
                        if len(clean_t) > 6:
                            folder = IMAGES_DIR / parent_safe
                            folder.mkdir(parents=True, exist_ok=True)
                            try:
                                with open(folder / "meta.json", "w", encoding="utf-8") as mf:
                                    json.dump({"title": clean_t, "sku": cleaned_query}, mf, indent=2)
                            except Exception:
                                pass
                            return clean_t
        except Exception:
            pass

    return cleaned_query




