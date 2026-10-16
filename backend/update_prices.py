from backend.sync.ecommerce_client import WooCommerceBridgeClient
from backend.sync.local_reader import get_grouped_catalog
from backend.config import log

client = WooCommerceBridgeClient()
grouped = get_grouped_catalog()

res = client.session.get(f"{client.base_url}/products", params={"per_page": 100})
products = res.json() if res.status_code == 200 else []
print(f"Found {len(products)} products on WooCommerce.")

for p in products:
    sku = p.get("sku")
    model = grouped.get(sku)
    if not model:
        continue

    real_price = model.get("price", 0.0)
    old_price = p.get("price")
    print(f"Updating {sku} (ID #{p['id']}): {old_price} -> {real_price} MAD")

    variations = model.get("variations", [])
    unique_sizes = list(dict.fromkeys([v.get("size") for v in variations if v.get("size")]))

    # Set parent price
    client.session.put(
        f"{client.base_url}/products/{p['id']}",
        json={"regular_price": str(real_price)},
        timeout=15
    )

    # Set variation prices
    if unique_sizes:
        client._sync_variations_for_product(p["id"], sku, variations, unique_sizes, real_price)

print("All WooCommerce products updated to exact GestCaisse prices successfully!")
