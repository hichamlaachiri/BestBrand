import os
import requests
from pathlib import Path
from requests.auth import HTTPBasicAuth
from backend.config import WEB_API_URL, API_KEY, API_SECRET, WP_USER, WP_APP_PASSWORD, log

class WooCommerceBridgeClient:
    """
    Client for WooCommerce REST API v3.
    Provides product synchronization, stock updates, media upload, and order monitoring.
    """
    def __init__(self, base_url: str = None, api_key: str = None, api_secret: str = None, wp_user: str = None, wp_app_pass: str = None):
        self.base_url = (base_url or WEB_API_URL).rstrip("/")
        self.api_key = api_key or API_KEY
        self.api_secret = api_secret or API_SECRET
        self.wp_user = wp_user or WP_USER
        self.wp_app_password = (wp_app_pass or WP_APP_PASSWORD).replace(" ", "")
        self.auth = HTTPBasicAuth(self.api_key, self.api_secret) if self.api_key else None
        self.wp_auth = HTTPBasicAuth(self.wp_user, self.wp_app_password) if (self.wp_user and self.wp_app_password) else None
        self.session = requests.Session()
        from urllib3.util.retry import Retry
        from requests.adapters import HTTPAdapter
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
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
        Supports Variable Products with Size (Taille) dropdown variations and Categories.
        """
        if not self.is_configured():
            return {"success": False, "message": "API not configured"}

        sku = product_data.get("sku") or product_data.get("parent_sku")
        existing = self.get_product_by_sku(sku)

        variations = product_data.get("variations", [])
        sizes = [str(v.get("size", "")).strip() for v in variations if str(v.get("size", "")).strip()]
        if not sizes and product_data.get("sizes"):
            sizes = [str(s).strip() for s in product_data.get("sizes") if str(s).strip()]

        unique_sizes = list(dict.fromkeys(sizes))
        is_variable = bool(len(unique_sizes) > 0)

        payload = {
            "name": product_data.get("name") or product_data.get("title") or sku,
            "sku": sku,
            "type": "variable" if is_variable else "simple",
            "stock_status": "instock" if product_data.get("in_stock", True) else "outofstock",
        }

        if not is_variable:
            payload["regular_price"] = str(product_data.get("price", "0.0"))
            payload["manage_stock"] = True
            payload["stock_quantity"] = product_data.get("stock_quantity", 1)

        # Categories
        categories = product_data.get("categories")
        if categories:
            payload["categories"] = [{"id": c} if isinstance(c, int) else {"name": str(c)} for c in categories]

        # Attributes (Taille dropdown)
        if unique_sizes:
            payload["attributes"] = [
                {
                    "name": "Taille",
                    "position": 0,
                    "visible": True,
                    "variation": is_variable,
                    "options": unique_sizes
                }
            ]

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
                res = self.session.put(url, json=payload, timeout=20)
                action = "Updated"
            else:
                url = f"{self.base_url}/products"
                res = self.session.post(url, json=payload, timeout=20)
                action = "Created"

            if res.status_code in (200, 201):
                res_data = res.json()
                prod_id = res_data.get("id")
                log(f"  🌐 WooCommerce: {action} product ID #{prod_id} (SKU: {sku})")

                # If variable, batch create/update the variations
                if is_variable and unique_sizes:
                    self._sync_variations_for_product(prod_id, sku, variations, unique_sizes, product_data.get("price", 0.0))

                return {"success": True, "id": prod_id, "action": action}
            else:
                log(f"  ❌ WooCommerce error for SKU '{sku}': {res.status_code} {res.text[:150]}")
                return {"success": False, "status_code": res.status_code, "error": res.text}
        except Exception as e:
            log(f"  ❌ WooCommerce request failed: {e}")
            return {"success": False, "error": str(e)}

    def _sync_variations_for_product(self, prod_id: int, parent_sku: str, variations: list[dict], unique_sizes: list[str], default_price: float):
        """Creates or updates size variations under a variable product."""
        try:
            var_url = f"{self.base_url}/products/{prod_id}/variations"
            existing_res = self.session.get(var_url, params={"per_page": 50}, timeout=10)
            existing_vars = existing_res.json() if existing_res.status_code == 200 else []
            existing_by_size = {}
            for ev in existing_vars:
                for att in ev.get("attributes", []):
                    if att.get("name") == "Taille":
                        existing_by_size[att.get("option")] = ev["id"]

            create_list = []
            update_list = []

            var_dict = {str(v.get("size", "")).strip(): v for v in variations if str(v.get("size", "")).strip()}

            for s in unique_sizes:
                v_data = var_dict.get(s, {})
                price = v_data.get("price") or default_price
                var_payload = {
                    "regular_price": str(price),
                    "manage_stock": True,
                    "stock_quantity": v_data.get("stock_quantity", 3),
                    "attributes": [{"name": "Taille", "option": s}]
                }
                sub_sku = v_data.get("sku") or f"{parent_sku}-{s}"
                var_payload["sku"] = sub_sku

                if s in existing_by_size:
                    var_payload["id"] = existing_by_size[s]
                    update_list.append(var_payload)
                else:
                    create_list.append(var_payload)

            if create_list or update_list:
                batch_url = f"{self.base_url}/products/{prod_id}/variations/batch"
                self.session.post(batch_url, json={"create": create_list, "update": update_list}, timeout=20)
                log(f"    📏 Synced {len(create_list) + len(update_list)} size variations for #{prod_id} ({', '.join(unique_sizes)})")
        except Exception as e:
            log(f"  ⚠️ Error syncing variations for product #{prod_id}: {e}")


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

            auth = self.wp_auth or self.auth
            res = self.session.post(media_url, headers=headers, data=img_data, timeout=20, auth=auth)
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
