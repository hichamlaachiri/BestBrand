# 📘 BestBrand Architecture & Implementation Guide
### SMART GestCaisse Bridge & Real-Time Local Sync Agent

---

## 📑 Table of Contents
1. [Executive Summary & Problem Statement](#1-executive-summary--problem-statement)
2. [System Architecture & Workflow](#2-system-architecture--workflow)
3. [HyperFileSQL (HFSQL) Reverse-Engineering Details](#3-hyperfilesql-hfsql-reverse-engineering-details)
4. [External Hardware & Material Requirements](#4-external-hardware--material-requirements)
5. [Cloud Services & External APIs](#5-cloud-services--external-apis)
6. [Future Roadmap & Recommended Features](#6-future-roadmap--recommended-features)
7. [CLI Commands & Operations Cheat Sheet](#7-cli-commands--operations-cheat-sheet)

---

## 1. Executive Summary & Problem Statement

**BestBrand** is a high-performance Python-based **Local Sync Agent (Bridge)** designed for retail businesses using **SMART GestCaisse** (a Point of Sale system built with PC SOFT WinDev and proprietary HyperFileSQL database files). 

It bridges the offline physical POS counter with modern online e-commerce infrastructure (**WooCommerce / WordPress**) while automating product asset enrichment.

### Core Problems Solved:
1. **Catalog Data Entry Bottleneck**:
   - Manually searching Google for product imagery across thousands of footwear and apparel references is tedious and slow.
   - **Solution**: 1-touch hotkey (`F2`) inside GestCaisse automatically queries search engines, downloads the top 3 high-resolution candidate images, and navigates the Windows file dialog directly into the product folder for instant 1-click selection.
2. **Duplicate Image Waste & Quota Exhaustion**:
   - In clothing and shoe retail, each size variation (e.g. `6007640-110 40`, `6007640-110 42`, `6007640-110 44`) previously triggered separate image downloads.
   - **Solution**: The engine normalizes references into clean parent models (e.g., `6007640_110`), sharing a single image set across all sizes.
3. **Double Inventory Entry**:
   - Stock and price changes had to be manually entered twice (once in GestCaisse and once on the website).
   - **Solution**: The Real-Time Sync Agent watches local database files and pushes catalog and stock updates automatically to WooCommerce.
4. **Internet Disruption Resilience (Offline Queueing)**:
   - If store internet disconnects, updates are safely stored in a local `.sync_state.json` queue and automatically replayed once connection is restored.

---

## 2. System Architecture & Workflow

### 🏗️ Project Layout:
```text
BestBrand/
├── main.py                     # CLI entrypoint & daemon lifecycle manager
├── run_bridge.bat              # 1-click Windows launcher
├── requirements.txt            # Python dependencies
├── .env.example                # Configuration template
├── PROJECT_GUIDE.md            # Comprehensive documentation
├── backend/
│   ├── config.py               # Auto-discovery of GestCaisse paths & settings
│   ├── scraper.py              # Multi-engine image search & size normalization
│   ├── hfsql_reader.py         # Batch image synchronizer
│   └── sync/
│       ├── local_reader.py     # Binary HFSQL reader (Article.FIC, prix.FIC)
│       ├── ecommerce_client.py # WooCommerce REST API client (Batch & Media upload)
│       └── sync_manager.py     # Real-time state watcher & offline queue
└── services/
    └── background_worker.py    # Windows automation (Win32 dialog, F2 hotkey, clipboard)
```

### 🔄 End-to-End Workflow:
```text
[ Cashier in GestCaisse ]
       │
       ▼ (Press F2 Hotkey)
[ services/background_worker.py ] ──► Auto-captures active reference (Ctrl+A / Ctrl+C)
       │
       ▼
[ backend/scraper.py ] ──────────────► Normalizes SKU (strips shoe & apparel sizes)
       │                              Queries Serper (Google) with Bing fallback
       ▼                              Downloads 3 JPEG candidate images
[ C:\SMART gestcaisse\Images\<SKU> ]
       │
       ▼
[ Win32 Dialog Controller ] ─────────► Injects path into Windows Open File Dialog
       │                              Cashier selects preferred image with 1 click
       ▼
[ backend/sync/sync_manager.py ] ────► Detects local changes, extracts price & barcode
       │                              Uploads images to WordPress Media Library
       ▼                              Pushes/Updates Product on WooCommerce
[ Online WooCommerce Store ]
```

---

## 3. HyperFileSQL (HFSQL) Reverse-Engineering Details

Because compiled WinDev applications embed database analysis structures internally, we developed a high-speed, zero-dependency direct binary parser:

| File | Structure & Record Stride | Decoded Fields |
| :--- | :--- | :--- |
| **`Article.FIC`** | **Fixed 532 Bytes** per record | • `Code Article`: Internal ID (e.g., `AR0000002` at offset +97)<br>• `Designation`: Full reference with size (offset +12)<br>• `Barcode`: EAN-13 / UPC barcode (offset +148) |
| **`prix.FIC`** | **Fixed 360 Bytes** per record | • `SKU`: Product model reference<br>• `Price`: Retail price in MAD (byte offset 322) |
| **`Factures.FIC`** | Dynamic sales ledger | Records all completed cashier checkout transactions |

### Data Summary from Active Store:
- **Total Stock Variants**: 1,925 individual size items.
- **Unique Parent Models**: 1,314 grouped product models.
- **Parsing Performance**: Under 35 milliseconds for the entire catalog.

---

## 4. External Hardware & Material Requirements

To operate the POS counter and the sync bridge reliably in a retail store, the following hardware equipment is required:

### 1. POS Counter Computer (PC Caisse)
- **Processor**: Intel Core i3 / i5 (6th Gen or newer) or AMD Ryzen equivalent.
- **RAM**: Minimum **8 GB DDR4**.
- **Storage**: **SSD (Solid State Drive)** is mandatory. HFSQL files perform frequent read/write cycles; an HDD causes severe UI stutter.
- **Operating System**: **Windows 10 or Windows 11 (64-bit)**.

### 2. Barcode Scanner (Douchette Code-Barres)
- **Type**: **1D/2D Barcode & QR Code Scanner** (Wireless 2.4GHz / Bluetooth preferred for mobility, or USB wired).
- **Configuration**: Must operate in **Keyboard Emulation (HID Mode)** so scanning a shoe box or tag instantly inputs text into the active field.
- **Recommended Models**: Zebra DS2208, Honeywell Voyager 1400g, Netum Wireless 2D.

### 3. Thermal Receipt Printer (Imprimante Ticket de Caisse - 80mm)
- **Role**: Customer receipt generation.
- **Specifications**: **80mm thermal paper width**, Auto-Cutter, USB interface, and RJ11 port to trigger the cash drawer.
- **Recommended Models**: Epson TM-T20III, Xprinter XP-N160M / XP-Q200.

### 4. Barcode Label Printer (Imprimante d'Étiquettes Code-Barres)
- **Role**: Printing price, size, and barcode tags for display items and shoe boxes.
- **Type**: Direct Thermal or Thermal Transfer.
- **Label Standard**: 50x30 mm or 40x25 mm.
- **Recommended Models**: Xprinter XP-365B / XP-370B, Zebra ZD220.

### 5. Electronic Cash Drawer (Tiroir-Caisse Automatique)
- **Specifications**: Metal cash drawer with 4/5 bill compartments and 8 coin slots, connected via **RJ11** to the receipt printer for automatic opening on sale completion.

### 6. Uninterruptible Power Supply (UPS / Onduleur) ⚠️ **CRITICAL**
- **Why it matters**: PC SOFT HyperFileSQL (`.FIC` and `.ndx`) files are highly vulnerable to corruption if power cuts during an active database write transaction.
- **Recommended**: **650VA to 850VA UPS** (e.g., APC Back-UPS 650VA or Eaton 650). Provides 15–20 minutes of battery backup to safely close transactions.

### 7. Reliable Network Infrastructure
- **Connection**: Wired **Ethernet RJ45 Cable** from the store router to the POS PC (preferred over Wi-Fi for uninterrupted sync).

---

## 5. Cloud Services & External APIs

| Service | Function | Cost / Plan |
| :--- | :--- | :--- |
| **WooCommerce REST API** | Receiving catalog data, stock levels, and prices from GestCaisse. | **Free** (Built into WordPress & WooCommerce). |
| **WordPress Web Hosting** | Hosting the e-commerce store with valid SSL (HTTPS is strictly required by WooCommerce API). | Standard VPS or managed hosting (Hostinger, Cloudways, etc.). |
| **Serper.dev API** | Querying Google Images API to retrieve pristine product imagery. | **Free tier (2,500 queries)**, then $5 for 50,000 queries. |
| **Bing Images Scraper** | Automatic fallback scraper when Serper quota is exhausted. | **100% Free** (No API keys needed, built into code). |
| **Automated Cloud Backup** | Daily backup of `SMARTBASE-2026` database files. | Google Drive, OneDrive, or local NAS. |

---

## 6. Future Roadmap & Recommended Features

### 💡 1. System Tray Desktop Applet
- Package the daemon into a Windows System Tray icon using `pystray`.
- Displays real-time green/red sync status, quick Pause/Resume toggles, and recent activity logs without keeping a CMD console open.

### 💡 2. Two-Way Inventory & Order Notifications
- Periodically poll WooCommerce for new orders (`status: processing`).
- Trigger an audible chime and popup alert on the POS screen notifying the cashier of an online purchase, while automatically deducting local inventory.

### 💡 3. WhatsApp Digital Receipts
- Connect with WhatsApp Business API to offer customers digital receipts sent directly to their phone, building an opt-in phone database for SMS/WhatsApp marketing.

### 💡 4. 1-Click Barcode Tag Printing (`F4` Hotkey)
- Map an `F4` hotkey inside GestCaisse to instantly generate and print a 50x30mm thermal label (with model name, barcode, and price) on the Xprinter/Zebra label printer.

### 💡 5. Multi-Store Centralized Inventory
- If the merchant opens multiple retail branches, deploy a Local Sync Agent in each store pointing to a centralized cloud sync controller to balance inventory across locations.

### 💡 6. Automated Encrypted Nightly HFSQL Backup
- Script a scheduled background task that creates a compressed, encrypted `.zip` archive of `SMARTBASE-2026` every evening at store closing and uploads it to cloud storage.

---

## 7. CLI Commands & Operations Cheat Sheet

| Command | Action |
| :--- | :--- |
| `python main.py --status` | Check GestCaisse DB connection, total products, image coverage, and WooCommerce status |
| `python main.py` | Start full background service (F2 image assistant + real-time web sync agent) |
| `run_bridge.bat` | 1-click Windows shortcut to launch the daemon without touching the terminal |
| `python main.py --sync-web` | Perform a full batch sync of all GestCaisse products to WooCommerce |
| `python main.py --sync-images` | Scan database and bulk download missing images for all products |

---

> 🔒 **Security Notice**: Keep `.env` out of public repositories. Use `.env.example` as a template for new deployments.
