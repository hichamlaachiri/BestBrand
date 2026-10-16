import sys
import os
import time

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from services.background_worker import BackgroundListenerDaemon
from backend.hfsql_reader import sync_missing_images
from backend.sync.sync_manager import LocalSyncAgent

from backend.config import LOW_RESOURCE_MODE

def print_status(agent: LocalSyncAgent):
    print("=" * 65)
    print(" 🤖 SMART GestCaisse Bridge & Local Real-Time Sync Agent")
    print("=" * 65)
    status = agent.get_status()
    print(f" • Local GestCaisse DB  : {'✅ Connected' if status['caisse_db_connected'] else '❌ Not Found'}")
    print(f" • Total Stock Variants : {status['total_articles']} articles")
    print(f" • Unique Parent Models : {status['unique_models']} products")
    print(f" • Image Coverage       : {status['models_with_images']}/{status['unique_models']} models ({status['image_coverage_pct']}%)")
    print(f" • Hardware Profile     : {'🟢 Low-Resource Mode (Low CPU/RAM Priority)' if LOW_RESOURCE_MODE else '⚡ Standard Mode'}")
    print(f" • WooCommerce Sync     : {'✅ Configured' if status['ecommerce_configured'] else '⚠️ Not Configured in .env'}")
    print(f"   └ API Status         : {status['ecommerce_status']['message']}")
    print(f" • Pending Sync Queue   : {status['pending_queue_count']} updates")
    print("=" * 65)

def main():
    sync_agent = LocalSyncAgent()

    if "--status" in sys.argv or "-i" in sys.argv:
        print_status(sync_agent)
        return

    if "--sync-ai" in sys.argv or "-ai" in sys.argv:
        print("=== 🤖 Gemini AI Catalog Synchronization Mode ===")
        # Check if user specified a limit
        limit = None
        for arg in sys.argv[1:]:
            if arg.isdigit():
                limit = int(arg)
                break
        sync_agent.sync_catalog_ai(limit=limit, only_with_images=True)
        return

    if "--sync-web" in sys.argv or "-w" in sys.argv:
        print("=== 🌐 Full Web Catalog Sync Mode ===")
        sync_agent.sync_all_catalog()
        return

    if "--sync-images" in sys.argv or "--sync" in sys.argv or "-s" in sys.argv:
        print("=== 📦 Batch Image Sync Mode ===")
        sync_missing_images()
        return

    # Default Mode: Runs Image Assistant Daemon + Real-Time Sync Agent
    print_status(sync_agent)
    
    sync_agent.start()
    daemon = BackgroundListenerDaemon(cooldown_seconds=30)
    daemon.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down SMART GestCaisse Bridge & Sync daemon...")
        daemon.stop()
        sync_agent.stop()

if __name__ == "__main__":
    main()
