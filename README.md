# 🚀 BestBrand - SMART GestCaisse Local Sync Agent & Automation Bridge

**BestBrand** is a high-performance Python bridge that connects local **SMART GestCaisse** POS software (WinDev / HyperFileSQL `.FIC` database) with modern E-Commerce platforms (WooCommerce / WordPress) and automates catalog asset enrichment.

---

## 🌟 Key Features

1. **⚡ Real-Time Local Sync Agent (Bridge Architecture)**
   - Monitors local WinDev/HFSQL database (`Article.FIC`, `prix.FIC`) for changes.
   - Automatically synchronizes new products, price updates, barcodes, and stock levels to WooCommerce.
   - **Offline-Resilient**: Queues changes locally during internet disruptions and auto-replays upon reconnection.
   - **Batch Optimization**: Pushes up to 100 products per request via `/wp-json/wc/v3/products/batch`.

2. **📸 1-Touch Image Assistant (F2 Hotkey)**
   - Press **F2** on any reference inside GestCaisse:
     - Automatically cleans size tags (both apparel `XS-3XL` and shoes `36-46`).
     - Downloads the 3 best high-resolution candidate images using Serper (Google Images) + Bing fallback.
     - Automatically navigates the Windows Open File Dialog into the SKU folder for 1-click selection.
   - Automatically uploads product photos to WordPress Media Library when syncing.

3. **🔍 Zero-Dependency HFSQL Binary Engine**
   - High-speed direct binary decoding of HyperFileSQL files (532-byte stride for articles, 360-byte stride for prices).
   - Groups individual size variations into clean parent product models.

---

## 📁 Project Structure

```text
├── main.py                     # CLI entrypoint & background daemon manager
├── run_bridge.bat              # 1-click Windows launcher
├── requirements.txt            # Python dependencies
├── .env.example                # Configuration template
├── backend/
│   ├── config.py               # Paths & environment discovery
│   ├── scraper.py              # Multi-engine image scraper & SKU size normalization
│   ├── hfsql_reader.py         # Batch image sync routines
│   └── sync/
│       ├── local_reader.py     # Binary HFSQL reader (Article.FIC, prix.FIC)
│       ├── ecommerce_client.py # WooCommerce REST API client (Single, Batch & Media)
│       └── sync_manager.py     # Real-time state watcher & offline queue
└── services/
    └── background_worker.py    # Windows automation (Win32 dialog, F2 hotkey, clipboard)
```

---

## 🛠️ Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/hichamlaachiri/BestBrand.git
   cd BestBrand
   ```

2. **Create and activate virtual environment:**
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure `.env`:**
   Copy `.env.example` to `.env` and fill in your WooCommerce API keys and Serper API key:
   ```env
   WEB_API_URL=https://yourstore.com/wp-json/wc/v3
   API_KEY=ck_xxxxxxxxxxxxxxxxxxxxxxxx
   API_SECRET=cs_xxxxxxxxxxxxxxxxxxxxxxxx
   SERPER_API_KEY=your_serper_key
   ```

---

## 💻 Usage

### 1. Check System & Sync Status:
```bash
python main.py --status
```

### 2. Run Background Daemon (Automation + Real-Time Sync):
Double-click `run_bridge.bat` or run:
```bash
python main.py
```

### 3. Full Web Catalog Sync:
Push all local GestCaisse products to WooCommerce in batches:
```bash
python main.py --sync-web
```

### 4. Batch Download Product Images:
Scan all missing images and download in bulk:
```bash
python main.py --sync-images
```

---

## 🔒 Security
- `.env` and local database files are excluded from Git version control.
- Passwords and consumer secrets must never be committed.
