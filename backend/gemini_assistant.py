import os
import re
import json
import base64
import requests
from pathlib import Path
from backend.config import GEMINI_API_KEY, IMAGES_DIR, log

import time

FALLBACK_MODELS = ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-flash-latest", "gemini-3.5-flash"]

def _call_gemini(parts: list) -> str | None:
    """
    Helper to invoke Gemini API with safety checks, automatic fallback across models,
    and exponential backoff on HTTP 429/503.
    """
    if not GEMINI_API_KEY:
        return None

    payload = {
        "contents": [{
            "parts": parts
        }]
    }

    for model in FALLBACK_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        for attempt in range(2):
            try:
                res = requests.post(url, json=payload, timeout=20)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        content_parts = candidates[0].get("content", {}).get("parts", [])
                        if content_parts:
                            return content_parts[0].get("text", "").strip()
                elif res.status_code in (429, 503):
                    # Rate limit or high demand on this model - backoff brief moment
                    time.sleep(2)
                    continue
                else:
                    break
            except Exception:
                pass

    return None

def is_valid_fashion_image(image_path: str) -> bool:
    """
    Uses Gemini Vision to inspect an image and check if it's apparel, shoes, or sportswear.
    Rejects mechanical parts, empty boxes, car filters, and unrelated images.
    """
    if not GEMINI_API_KEY or not Path(image_path).exists():
        return True # Default to pass if AI not available

    try:
        img_bytes = Path(image_path).read_bytes()
        # Compress / limit if too large
        if len(img_bytes) > 4 * 1024 * 1024:
            return True

        b64 = base64.b64encode(img_bytes).decode("utf-8")
        prompt = (
            "You are a luxury fashion e-commerce product inspector for a store selling Nike/Adidas sportswear, sneakers, hoodies, and apparel. "
            "Examine this image carefully: Is this an item of fashion, clothing, apparel, sportswear, shoes, or sneakers (on a model, hanger, or clean background)? "
            "Reply strictly with YES if it is fashion/clothing/shoes. "
            "Reply strictly with NO if it is irrelevant (e.g. car parts, metal cans, mechanical oil filters, random cardboard boxes, paper documents, or unrelated junk)."
        )

        parts = [
            {"text": prompt},
            {
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": b64
                }
            }
        ]

        verdict = _call_gemini(parts)
        if verdict:
            is_valid = "yes" in verdict.lower()
            if not is_valid:
                log(f"  🛡️ Gemini Vision AI rejected non-apparel image: {Path(image_path).name} ({verdict})")
            return is_valid
    except Exception as e:
        log(f"  ⚠️ Vision inspection error: {e}")

    return True

def filter_apparel_images(image_paths: list[str]) -> list[str]:
    """Filters a list of downloaded candidate images, keeping only verified apparel/sneakers."""
    verified = []
    for p in image_paths:
        if is_valid_fashion_image(p):
            verified.append(p)
    return verified

def enrich_product_with_ai(sku: str, candidate_title: str = "") -> dict:
    """
    Uses Gemini AI to generate:
    - Official commercial product name (e.g., 'Nike Sportswear Tech Fleece Windrunner')
    - Brand (Nike, Adidas, etc.)
    - Exact category (Hoodies, Sneakers, T-Shirts, Sportswear)
    - Short luxury marketing description
    Caches result in Images/<SKU>/ai_meta.json.
    """
    clean_sku = re.sub(r'[\s\.\-_]+[A-Z0-9]+$', '', sku.strip())
    parent_safe = "".join(c if c.isalnum() else "_" for c in clean_sku)
    cache_file = IMAGES_DIR / parent_safe / "ai_meta.json"

    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    if not GEMINI_API_KEY:
        return {
            "title": candidate_title or sku,
            "brand": "Nike",
            "category": "Sportswear",
            "description": f"Authentic Nike sportswear model {sku} synchronized directly with GestCaisse."
        }

    prompt = (
        f"You are an expert luxury sportswear catalog manager for a high-end streetwear boutique selling authentic Nike, Under Armour, and Adidas apparel.\n"
        f"Product SKU: {sku}\n"
        f"Search snippet title: {candidate_title}\n\n"
        f"Please provide the official commercial product information in strict JSON format:\n"
        f"{{\n"
        f'  "title": "Official product model name without promotional text (e.g. Nike Tech Fleece Windrunner Full-Zip Hoodie)",\n'
        f'  "brand": "Nike or Adidas or Under Armour",\n'
        f'  "category": "One of: Hoodies, Sneakers, T-Shirts, Sportswear, Pants",\n'
        f'  "description": "2 crisp, compelling sentences describing the fit, premium fabric, and style."\n'
        f"}}\n"
        f"Respond with JSON only. No markdown formatting."
    )

    raw = _call_gemini([{"text": prompt}])
    if raw:
        try:
            # Clean JSON if wrapped in markdown blocks
            clean_json = re.sub(r'^```json\s*', '', raw, flags=re.MULTILINE)
            clean_json = re.sub(r'^```\s*', '', clean_json, flags=re.MULTILINE).strip()
            data = json.loads(clean_json)

            # Cache to disk
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            return data
        except Exception as e:
            log(f"  ⚠️ Error parsing Gemini JSON: {e}")

    return {
        "title": candidate_title or sku,
        "brand": "Nike",
        "category": "Sportswear",
        "description": f"Authentic athletic apparel model {sku}."
    }
