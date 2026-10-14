import os
import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# GestCaisse Path Discovery (Env -> Production C:\ -> Relative Dev Path)
GESTCAISSE_ENV = os.getenv("GESTCAISSE_DIR")
if GESTCAISSE_ENV and Path(GESTCAISSE_ENV).exists():
    APP_DIR = Path(GESTCAISSE_ENV)
elif Path(r"C:\SMART gestcaisse").exists():
    APP_DIR = Path(r"C:\SMART gestcaisse")
elif (BASE_DIR.parent / "SMART gestcaisse").exists():
    APP_DIR = BASE_DIR.parent / "SMART gestcaisse"
else:
    APP_DIR = Path(r"C:\SMART gestcaisse")

DATA_DIR = APP_DIR / "SMARTBASE-2026"
IMAGES_DIR = APP_DIR / "Images"
LOG_FILE = BASE_DIR / "@AutomationLog.txt"
STATE_FILE = BASE_DIR / ".sync_state.json"

# Ensure image directory exists
try:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

# Web API Settings (WooCommerce REST API)
WEB_API_URL = os.getenv("WEB_API_URL", "https://yourwebsite.com/wp-json/wc/v3").rstrip("/")
API_KEY = os.getenv("API_KEY", "")
API_SECRET = os.getenv("API_SECRET", "")
SYNC_INTERVAL_SECONDS = int(os.getenv("SYNC_INTERVAL_SECONDS", "30"))
ENABLE_AUTO_IMAGE_UPLOAD = os.getenv("ENABLE_AUTO_IMAGE_UPLOAD", "true").lower() in ("true", "1", "yes")

# Serper.dev Image Scraping API Key
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "403cba5715e01a9c9b102862b0c8eb498d5da3bf")

def log(msg: str):
    """Prints formatted message and appends to @AutomationLog.txt."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass


