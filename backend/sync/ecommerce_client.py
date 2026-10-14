import os
import requests
from pathlib import Path
from requests.auth import HTTPBasicAuth
from backend.config import WEB_API_URL, API_KEY, API_SECRET, log

class WooCommerceBridgeClient:
    """
    Client for WooCommerce REST API v3.
    Provides product synchronization, stock updates, media upload, and order monitoring.
    """
    def __init__(self, base_url: str = None, api_key: str = None, api_secret: str = None):
        self.base_url = (base_url or WEB_API_URL).rstrip("/")
        self.api_key = api_key or API_KEY
        self.api_secret = api_secret or API_SECRET
        self.auth = HTTPBasicAuth(self.api_key, self.api_secret) if self.api_key else None
        self.session = requests.Session()
        if self.auth:
            self.session.auth = self.auth
        self.session.headers.update({
            "User-Agent": "SMART-GestCaisse-Bridge/1.0",
            "Accept": "application/json"
        })

    def is_configured(self) -> bool:
        """Checks if valid API credentials have been provided."""
        return bool(
            self.api_key 
            and self.api_secret 
            and "yourwebsite.com" not in self.base_url 
            and "your_api_key_here" not in self.api_key
        )

    def test_connection(self) -> dict:
        """Tests connectivity and authentication with WooCommerce REST API."""
        if not self.is_configured():
            return {
                "success": False,
                "status_code": 0,
                "message": "WooCommerce API credentials not configured in .env (WEB_API_URL, API_KEY, API_SECRET)"
            }

        endpoint = f"{self.base_url}/products"
        try:
            res = self.session.get(endpoint, params={"per_page": 1}, timeout=10)
            if res.status_code == 200:
                total_products = res.headers.get("X-WP-Total", "unknown")
                return {
                    "success": True,
                    "status_code": 200,
                    "total_products_on_web": total_products,
                    "message": f"Connected to WooCommerce successfully! Products online: {total_products}"
                }
            else:
                return {
                    "success": False,
                    "status_code": res.status_code,
                    "message": f"WooCommerce API returned HTTP {res.status_code}: {res.text[:200]}"
                }
        except Exception as e:
            return {
                "success": False,
                "status_code": 0,
                "message": f"Connection failed: {e}"
            }

    def get_product_by_sku(self, sku: str) -> dict | None:
        """Looks up a product on WooCommerce by its SKU reference."""
        if not self.is_configured():
            return None
        try:
            url = f"{self.base_url}/products"
            res = self.session.get(url, params={"sku": sku.strip()}, timeout=10)
            if res.status_code == 200:
                items = res.json()
                if items:
                    return items[0]
            return None
        except Exception as e:
            log(f"⚠️ Error querying product SKU '{sku}': {e}")
            return None

    def upsert_product(self, product_data: dict) -> dict:
        """
        Creates or updates a single product on WooCommerce based on SKU.
        product_data should contain: sku, name/title, price, barcode, images, sizes.
        """
        if not self.is_configured():
            return {"success": False, "message": "API not configured"}

        sku = product_data.get("sku") or product_data.get("parent_sku")
        existing = self.get_product_by_sku(sku)

        payload = {
            "name": product_data.get("name") or product_data.get("title") or sku,
            "sku": sku,
            "regular_price": str(product_data.get("price", "0.0")),
            "manage_stock": True,
            "stock_status": "instock" if product_data.get("in_stock", True) else "outofstock",
            "stock_quantity": product_data.get("stock_quantity", 1),
        }

        # Add barcode meta if present
        barcode = product_data.get("barcode")
        if barcode:
            payload["meta_data"] = [
                {"key": "_barcode", "value": barcode},
                {"key": "_gestcaisse_code", "value": product_data.get("article_code", "")}
            ]

        # Add image URLs if provided
        image_urls = product_data.get("image_urls")
        if image_urls:
            payload["images"] = [{"src": u} for u in image_urls]

        try:
            if existing:
                prod_id = existing["id"]
                url = f"{self.base_url}/products/{prod_id}"
                res = self.session.put(url, json=payload, timeout=15)
                action = "Updated"
            else:
                url = f"{self.base_url}/products"
                res = self.session.post(url, json=payload, timeout=15)
                action = "Created"

            if res.status_code in (200, 201):
                res_data = res.json()
                log(f"  🌐 WooCommerce: {action} product ID #{res_data.get('id')} (SKU: {sku})")
                return {"success": True, "id": res_data.get("id"), "action": action}
            else:
                log(f"  ❌ WooCommerce error for SKU '{sku}': {res.status_code} {res.text[:150]}")
                return {"success": False, "status_code": res.status_code, "error": res.text}
        except Exception as e:
            log(f"  ❌ WooCommerce request failed: {e}")
            return {"success": False, "error": str(e)}

    def batch_sync_products(self, create_list: list[dict] = None, update_list: list[dict] = None) -> dict:
        """
        Executes high-performance batch upsert on WooCommerce (up to 100 products per request).
        """
        if not self.is_configured():
            return {"success": False, "message": "API not configured"}

        payload = {
            "create": create_list or [],
            "update": update_list or []
        }

        url = f"{self.base_url}/products/batch"
        try:
            res = self.session.post(url, json=payload, timeout=30)
            if res.status_code in (200, 201):
                data = res.json()
                created = len(data.get("create", []))
                updated = len(data.get("update", []))
                log(f"  🚀 WooCommerce Batch Sync: {created} created, {updated} updated.")
                return {"success": True, "created": created, "updated": updated}
            else:
                log(f"  ❌ Batch sync failed: HTTP {res.status_code} - {res.text[:150]}")
                return {"success": False, "status_code": res.status_code}
        except Exception as e:
            log(f"  ❌ Batch sync exception: {e}")
            return {"success": False, "error": str(e)}

    def upload_media_image(self, file_path: str, caption: str = "") -> dict | None:
        """Uploads a local JPEG image to WordPress Media Library."""
        if not self.is_configured() or not os.path.exists(file_path):
            return None

        # WordPress Media endpoint is at /wp-json/wp/v2/media
        wp_api_base = self.base_url.split("/wc/v")[0] + "/wp/v2"
        media_url = f"{wp_api_base}/media"

        file_name = Path(file_path).name
        headers = {
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Content-Type": "image/jpeg"
        }

        try:
            with open(file_path, "rb") as f:
                img_data = f.read()

            res = self.session.post(media_url, headers=headers, data=img_data, timeout=20)
            if res.status_code in (200, 201):
                data = res.json()
                media_id = data.get("id")
                source_url = data.get("source_url")
                log(f"  🖼️ Uploaded image to WordPress media: ID #{media_id} ({source_url})")
                return {"id": media_id, "url": source_url}
            else:
                log(f"  ⚠️ Media upload warning: HTTP {res.status_code}")
                return None
        except Exception as e:
            log(f"  ⚠️ Media upload error: {e}")
            return None

    def get_pending_orders(self) -> list[dict]:
        """Fetches pending/processing orders from website for local synchronization."""
        if not self.is_configured():
            return []

        url = f"{self.base_url}/orders"
        try:
            res = self.session.get(url, params={"status": "processing", "per_page": 20}, timeout=10)
            if res.status_code == 200:
                return res.json()
            return []
        except Exception as e:
            log(f"⚠️ Error fetching orders: {e}")
            return []
