import re
import json
import time
import threading
from pathlib import Path
from backend.config import STATE_FILE, SYNC_INTERVAL_SECONDS, ENABLE_AUTO_IMAGE_UPLOAD, LOW_RESOURCE_MODE, log
from backend.sync.local_reader import get_local_catalog, get_grouped_catalog, compute_catalog_hash
from backend.sync.ecommerce_client import WooCommerceBridgeClient
from backend.scraper import get_product_commercial_title
from backend.gemini_assistant import enrich_product_with_ai, filter_apparel_images

def determine_categories(title: str, variations: list[dict]) -> list[dict]:
    """Auto-detects WooCommerce categories from shoe sizes or apparel keywords."""
    sizes = [str(v.get("size", "")).strip() for v in variations if str(v.get("size", "")).strip()]
    is_shoe = any(re.match(r'^(3[5-9]|4[0-8])(\.5)?$', s) for s in sizes)
    if is_shoe:
        return [{"id": 19, "name": "Sneakers"}]

    t_lower = title.lower()
    if any(k in t_lower for k in ("hoodie", "fleece", "windrunner", "jacket", "veste", "sweat")):
        return [{"id": 20, "name": "Hoodies"}, {"id": 21, "name": "Sportswear"}]
    elif any(k in t_lower for k in ("t-shirt", "tee", "top")):
        return [{"id": 22, "name": "T-Shirts"}, {"id": 21, "name": "Sportswear"}]
    else:
        return [{"id": 21, "name": "Sportswear"}]


class LocalSyncAgent:
    """
    Local Sync Agent (Bridge Architecture) for SMART GestCaisse.
    Monitors local WinDev/HFSQL database changes and synchronizes products, prices,
    stock, and images to WooCommerce in real-time.
    Includes offline queueing for network resilience.
    """
    def __init__(self):
        self.client = WooCommerceBridgeClient()
        self.running = False
        self.lock = threading.Lock()
        self.state = self._load_state()
        self.thread = None

    def _load_state(self) -> dict:
        """Loads persistent sync state from disk."""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "last_hash": "",
            "last_synced_at": 0,
            "synced_products": {},
            "offline_queue": []
        }

    def _save_state(self):
        """Saves sync state to disk atomically."""
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            log(f"⚠️ Error saving sync state: {e}")

    def get_status(self) -> dict:
        """Returns comprehensive bridge status."""
        catalog = get_local_catalog()
        grouped = get_grouped_catalog()
        total_with_images = sum(1 for item in grouped.values() if item.get("images"))
        conn_test = self.client.test_connection()

        return {
            "caisse_db_connected": len(catalog) > 0,
            "total_articles": len(catalog),
            "unique_models": len(grouped),
            "models_with_images": total_with_images,
            "image_coverage_pct": round((total_with_images / len(grouped) * 100) if grouped else 0, 1),
            "ecommerce_configured": self.client.is_configured(),
            "ecommerce_status": conn_test,
            "pending_queue_count": len(self.state.get("offline_queue", []))
        }

    def sync_single_sku(self, sku: str) -> bool:
        """Synchronizes a single SKU (or parent model) immediately."""
        grouped = get_grouped_catalog()
        item = grouped.get(sku.strip().upper())
        if not item:
            # Check individual articles
            catalog = get_local_catalog()
            match = next((a for a in catalog if a["reference"].upper() == sku.strip().upper()), None)
            if match:
                item = {
                    "parent_sku": match["reference"],
                    "title": match["reference"],
                    "price": match["price"],
                    "barcode": match["barcode"],
                    "images": match["images"],
                    "article_code": match["article_code"]
                }

        if not item:
            log(f"  ⚠️ SKU '{sku}' not found in local GestCaisse catalog.")
            return False

        return self._sync_product_item(item)

    def _sync_product_item(self, item: dict) -> bool:
        """Pushes a product to WooCommerce, uploading images if available."""
        if not self.client.is_configured():
            log("  ℹ️ WooCommerce credentials not configured. Changes queued locally.")
            with self.lock:
                self.state.setdefault("offline_queue", []).append(item)
                self._save_state()
            return False

        parent_sku = item["parent_sku"]
        candidate_title = get_product_commercial_title(parent_sku)

        # Gemini 3.6 Flash AI Enrichment (Official title, category, description)
        ai_meta = enrich_product_with_ai(parent_sku, candidate_title)
        clean_ai_title = ai_meta.get("title") or candidate_title or parent_sku
        if clean_ai_title.upper() == parent_sku.upper():
            final_title = parent_sku
        else:
            final_title = f"{clean_ai_title} ({parent_sku})"

        ai_cat_name = str(ai_meta.get("category", "Sportswear")).lower()
        cat_map = {
            "hoodies": [{"id": 20, "name": "Hoodies"}, {"id": 21, "name": "Sportswear"}],
            "sneakers": [{"id": 19, "name": "Sneakers"}],
            "t-shirts": [{"id": 22, "name": "T-Shirts"}, {"id": 21, "name": "Sportswear"}],
            "sportswear": [{"id": 21, "name": "Sportswear"}],
            "pants": [{"id": 21, "name": "Sportswear"}]
        }
        variations = item.get("variations", [])
        categories = cat_map.get(ai_cat_name, determine_categories(final_title, variations))

        # Image Handling: verify with Gemini Vision before upload
        image_urls = []
        if ENABLE_AUTO_IMAGE_UPLOAD and item.get("images"):
            verified_images = filter_apparel_images(item["images"])
            for img_path in verified_images[:3]:
                uploaded = self.client.upload_media_image(img_path, caption=parent_sku)
                if uploaded and uploaded.get("url"):
                    image_urls.append(uploaded["url"])

        product_payload = {
            "sku": parent_sku,
            "name": final_title,
            "price": item.get("price", 0.0),
            "barcode": item.get("barcode", ""),
            "article_code": item.get("article_code", ""),
            "description": ai_meta.get("description", ""),
            "image_urls": image_urls,
            "variations": variations,
            "categories": categories
        }

        res = self.client.upsert_product(product_payload)
        if res.get("success"):
            with self.lock:
                self.state.setdefault("synced_products", {})[item["parent_sku"]] = {
                    "web_id": res.get("id"),
                    "synced_at": time.time(),
                    "price": item.get("price", 0.0)
                }
                self._save_state()
            return True
        else:
            with self.lock:
                self.state.setdefault("offline_queue", []).append(item)
                self._save_state()
            return False

    def check_for_changes_and_sync(self):
        """Scans local database and synchronizes changes."""
        catalog = get_local_catalog()
        if not catalog:
            return

        current_hash = compute_catalog_hash(catalog)
        with self.lock:
            last_hash = self.state.get("last_hash", "")
            queue = list(self.state.get("offline_queue", []))

        # 1. Process queued items first if connection is available
        if queue and self.client.is_configured():
            log(f"\n🔄 Local Sync Agent: Processing {len(queue)} queued offline updates...")
            remaining_queue = []
            for q_item in queue:
                ok = self._sync_product_item(q_item)
                if not ok:
                    remaining_queue.append(q_item)
            with self.lock:
                self.state["offline_queue"] = remaining_queue
                self._save_state()

        # 2. Check if local catalog changed
        if current_hash != last_hash:
            log(f"\n⚡ Database Change Detected in GestCaisse! (Hash changed)")
            grouped = get_grouped_catalog()
            synced_dict = self.state.get("synced_products", {})

            changed_count = 0
            for parent_sku, model_data in grouped.items():
                last_info = synced_dict.get(parent_sku)
                # If never synced or price changed
                if not last_info or last_info.get("price") != model_data.get("price"):
                    self._sync_product_item(model_data)
                    changed_count += 1

            with self.lock:
                self.state["last_hash"] = current_hash
                self.state["last_synced_at"] = time.time()
                self._save_state()

            log(f"✅ Real-time Sync completed. {changed_count} models updated.")

    def sync_all_catalog(self, batch_size: int = 50) -> dict:
        """
        Full catalog sync to WooCommerce.
        Iterates over all models in GestCaisse and sends them in batches.
        """
        if not self.client.is_configured():
            log("❌ Cannot perform full sync: WooCommerce API is not configured in .env.")
            return {"success": False, "message": "API not configured"}

        grouped = get_grouped_catalog()
        log(f"\n🚀 Starting Full Catalog Sync: {len(grouped)} products to WooCommerce...")

        items = list(grouped.values())
        created_total = 0
        updated_total = 0

        for i in range(0, len(items), batch_size):
            chunk = items[i:i+batch_size]
            create_batch = []

            for item in chunk:
                payload = {
                    "sku": item["parent_sku"],
                    "name": item["parent_sku"],
                    "regular_price": str(item.get("price", "0.0")),
                    "manage_stock": True,
                    "stock_quantity": 1,
                    "stock_status": "instock"
                }
                if item.get("barcode"):
                    payload["meta_data"] = [{"key": "_barcode", "value": item["barcode"]}]
                create_batch.append(payload)

            log(f"  📤 Syncing batch {i//batch_size + 1}/{(len(items)+batch_size-1)//batch_size} ({len(create_batch)} items)...")
            res = self.client.batch_sync_products(create_list=create_batch)
            if res.get("success"):
                created_total += res.get("created", 0)
                updated_total += res.get("updated", 0)

        catalog = get_local_catalog()
        with self.lock:
            self.state["last_hash"] = compute_catalog_hash(catalog)
            self.state["last_synced_at"] = time.time()
            self._save_state()

        log(f"\n✨ Full Catalog Sync Complete! Created: {created_total} | Updated: {updated_total}")
        return {"success": True, "created": created_total, "updated": updated_total}

    def sync_catalog_ai(self, limit: int = None, only_with_images: bool = True) -> int:
        """
        Synchronizes products using Gemini 3.6 Flash AI enrichment, 
        Vision image filtering, and variable size dropdowns.
        """
        grouped = get_grouped_catalog()
        items = list(grouped.values())
        if only_with_images:
            items = [item for item in items if item.get("images")]
        
        if limit:
            items = items[:limit]

        log(f"\n🚀 Starting Gemini AI Catalog Sync for {len(items)} products (Images required: {only_with_images})...")
        success_count = 0
        for idx, item in enumerate(items, 1):
            sku = item.get("parent_sku")
            log(f"\n📦 [{idx}/{len(items)}] Processing {sku} with Gemini AI...")
            try:
                ok = self._sync_product_item(item)
                if ok:
                    success_count += 1
                time.sleep(1.5)  # Safe rate limit for Gemini API & WordPress Media
            except Exception as e:
                log(f"  ❌ Error syncing {sku}: {e}")
        
        log(f"\n✨ Gemini AI Sync Finished: {success_count}/{len(items)} products synced successfully to WooCommerce!")
        return success_count

    def _sync_loop(self):
        """Background monitoring thread."""
        interval = max(60, SYNC_INTERVAL_SECONDS) if LOW_RESOURCE_MODE else SYNC_INTERVAL_SECONDS
        while self.running:
            try:
                self.check_for_changes_and_sync()
            except Exception as e:
                log(f"⚠️ Sync Agent background error: {e}")
            time.sleep(interval)

    def start(self):
        """Starts the sync agent background daemon."""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.thread.start()
        log(f"🌐 Local Sync Agent (Bridge Architecture) started. Interval: {SYNC_INTERVAL_SECONDS}s.")

    def stop(self):
        """Stops the sync agent daemon."""
        self.running = False
        log("Local Sync Agent stopped.")
