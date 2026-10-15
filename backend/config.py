import os
import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# GestCaisse Path Discovery (Env -> Dev Relative Path -> Production C:\)
GESTCAISSE_ENV = os.getenv("GESTCAISSE_DIR")
if GESTCAISSE_ENV and (Path(GESTCAISSE_ENV) / "SMARTBASE-2026").exists():
    APP_DIR = Path(GESTCAISSE_ENV)
elif (BASE_DIR.parent / "SMART gestcaisse" / "SMARTBASE-2026").exists():
    APP_DIR = BASE_DIR.parent / "SMART gestcaisse"
elif (Path(r"C:\SMART gestcaisse") / "SMARTBASE-2026").exists():
    APP_DIR = Path(r"C:\SMART gestcaisse")
elif Path(r"C:\SMART gestcaisse").exists():
    APP_DIR = Path(r"C:\SMART gestcaisse")
else:
    APP_DIR = BASE_DIR.parent / "SMART gestcaisse"

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

# Performance Tuning (Low-Resource Mode for older POS hardware)
LOW_RESOURCE_MODE = os.getenv("LOW_RESOURCE_MODE", "true").lower() in ("true", "1", "yes")

# Auto-lower process priority on Windows so GestCaisse always has 100% CPU priority
if LOW_RESOURCE_MODE:
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetCurrentProcess()
        # 0x00004000 = BELOW_NORMAL_PRIORITY_CLASS
        kernel32.SetPriorityClass(handle, 0x00004000)
    except Exception:
        pass

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


