import sys
import os
import re
import time

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import ctypes
import threading
import winsound
import datetime
import pyperclip
from pathlib import Path
from pynput import keyboard
from pynput.keyboard import Key, Controller as KeyboardController
from pynput.mouse import Button, Controller as MouseController
from backend.config import DATA_DIR, IMAGES_DIR, BASE_DIR, LOW_RESOURCE_MODE, log
from backend.scraper import fetch_product_images
from backend.hfsql_reader import extract_skus_from_db

ARTICLE_FIC_PATH = DATA_DIR / "Article.FIC"
SKU_PATTERN = re.compile(r'\b([A-Z0-9]{4,8}[- ][A-Z0-9]{3,5}(?:\s+[A-Z0-9]{1,4})?)\b', re.IGNORECASE)

kb_controller = KeyboardController()
mouse_controller = MouseController()


class RECT(ctypes.Structure):
    _fields_ = [
        ('left', ctypes.c_long),
        ('top', ctypes.c_long),
        ('right', ctypes.c_long),
        ('bottom', ctypes.c_long)
    ]

def navigate_file_dialog_to_folder(hwnd, target_folder: str) -> bool:
    """
    Navigates the Windows Open File Dialog into the SKU's folder.
    This shows the 3 downloaded candidate images so the user can easily choose their preferred one.
    Does NOT auto-submit or pick a file.
    """
    user32 = ctypes.windll.user32
    log(f"📁 Opening reference folder in File Dialog: {target_folder}")
    
    time.sleep(0.3)
    
    for attempt in range(3):
        if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
            return False
            
        user32.SetForegroundWindow(hwnd)
        
        dialog_rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(dialog_rect))
        d_mid_y = (dialog_rect.top + dialog_rect.bottom) // 2
        
        edit_controls = []
        open_button = 0
        
        def enum_cb(c_hwnd, _):
            nonlocal open_button
            c_cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(c_hwnd, c_cls, 256)
            cls_name = c_cls.value.lower()
            
            c_len = user32.GetWindowTextLengthW(c_hwnd)
            c_txt = ctypes.create_unicode_buffer(c_len + 1)
            user32.GetWindowTextW(c_hwnd, c_txt, c_len + 1)
            txt = c_txt.value.lower()
            
            c_id = user32.GetDlgCtrlID(c_hwnd)
            c_rect = RECT()
            user32.GetWindowRect(c_hwnd, ctypes.byref(c_rect))
            
            if "edit" in cls_name:
                edit_controls.append((c_hwnd, c_rect))
            elif "button" in cls_name:
                if c_id == 1 or any(k in txt for k in ["open", "ouvrir", "&open", "&ouvrir"]):
                    open_button = c_hwnd
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        user32.EnumChildWindows(hwnd, WNDENUMPROC(enum_cb), 0)
        
        target_edit = 0
        for eh, er in edit_controls:
            if er.top > d_mid_y:
                target_edit = eh
                break
                
        if not target_edit and edit_controls:
            target_edit = edit_controls[-1][0]
            
        if target_edit:
            # Set target folder path into File Name field
            user32.SendMessageW(target_edit, 0x000C, 0, target_folder)
            time.sleep(0.12)
            
            # Press Open or Enter to navigate INSIDE the folder
            if open_button and user32.IsWindow(hwnd):
                user32.SendMessageW(open_button, 0x00F5, 0, 0)
                user32.SendMessageW(hwnd, 0x0111, 1, open_button)
            else:
                if user32.GetForegroundWindow() == hwnd:
                    kb_controller.press(Key.enter)
                    kb_controller.release(Key.enter)
                    
            log("  🎯 Dialog entered SKU folder! 3 images are displayed for selection.")
            return True
        else:
            # Fallback using Alt+N / Ctrl+V
            pyperclip.copy(target_folder)
            kb_controller.press(Key.alt)
            kb_controller.press('n')
            kb_controller.release('n')
            kb_controller.release(Key.alt)
            time.sleep(0.1)
            kb_controller.press(Key.ctrl)
            kb_controller.press('v')
            kb_controller.release('v')
            kb_controller.release(Key.ctrl)
            time.sleep(0.1)
            kb_controller.press(Key.enter)
            kb_controller.release(Key.enter)
            time.sleep(0.2)
            log("  🎯 Fallback folder navigation completed. Choose your preferred image.")
            return True
            
        time.sleep(0.2)
        
    return False


class BackgroundListenerDaemon:
    def __init__(self, cooldown_seconds: int = 10):
        self.cooldown_seconds = cooldown_seconds
        self.recent_refs = {}
        self.lock = threading.Lock()
        self.running = False
        self.last_fic_mtime = 0
        self.last_fic_size = 0
        self.keyboard_listener = None
        self.latest_folder_path = ""
        self.current_gestcaisse_hwnd = None

    def is_debounced(self, ref: str) -> bool:
        now = time.time()
        with self.lock:
            self.recent_refs = {r: t for r, t in self.recent_refs.items() if now - t < self.cooldown_seconds}
            if ref in self.recent_refs:
                return True
            self.recent_refs[ref] = now
            return False

    def trigger_image_upload_click(self):
        """Auto-clicks the GestCaisse image frame (top right) to open the file picker dialog."""
        try:
            if not self.current_gestcaisse_hwnd:
                self.current_gestcaisse_hwnd = ctypes.windll.user32.GetForegroundWindow()
            
            hwnd = self.current_gestcaisse_hwnd
            if hwnd:
                rect = RECT()
                ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                
                if width > 300 and height > 200:
                    target_x = rect.right - 115
                    target_y = rect.top + 175
                    log(f"🖱 Auto-clicking GestCaisse image frame at X:{target_x}, Y:{target_y}...")
                    
                    time.sleep(0.15)
                    mouse_controller.position = (target_x, target_y)
                    time.sleep(0.1)
                    mouse_controller.click(Button.left, 1)
        except Exception as e:
            log(f"  ⚠️ Auto-click error: {e}")

    def wait_and_navigate_dialog(self, target_folder: str):
        """Actively waits for the file dialog to appear and navigates inside the SKU folder."""
        user32 = ctypes.windll.user32
        start_time = time.time()
        
        while time.time() - start_time < 3.5:
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value.lower()
                    
                    cls_buff = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd, cls_buff, 256)
                    
                    if any(kw in title for kw in ["sélectionnez", "select", "ouvrir", "open", "parcourir"]) or cls_buff.value == "#32770":
                        navigate_file_dialog_to_folder(hwnd, target_folder)
                        return True
            time.sleep(0.1)
        return False

    def process_detected_sku(self, ref: str, source: str):
        ref_upper = ref.strip().upper()
        if self.is_debounced(ref_upper):
            return

        log(f"\n⚡ SKU Detected [{source}]: '{ref_upper}'")
        
        def worker():
            res = fetch_product_images(ref_upper, max_images=3)
            folder_path = res.get("folder", "")
            downloaded = res.get("images", [])
            
            if downloaded:
                log(f"✨ Downloaded {len(downloaded)} candidate image(s) to folder: {folder_path}")
                for idx, p in enumerate(downloaded, 1):
                    log(f"   [{idx}] {Path(p).name}")
                    
                self.latest_folder_path = folder_path
                try:
                    pyperclip.copy(folder_path)
                    log("📋 Folder path copied to clipboard!")
                except Exception as e:
                    log(f"  ⚠️ Clipboard copy error: {e}")
                
                # Audio Notification 🎵
                try:
                    winsound.Beep(1200, 100)
                    winsound.Beep(1800, 150)
                except Exception:
                    pass

                # If triggered by F2 Hotkey, auto-click GestCaisse image frame and open the folder in dialog
                if "F2" in source:
                    time.sleep(0.2)
                    self.trigger_image_upload_click()
                    self.wait_and_navigate_dialog(folder_path)

            else:
                log(f"❌ Could not fetch any image for SKU: '{ref_upper}'")
                try:
                    winsound.Beep(400, 250)
                except Exception:
                    pass

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    # --- 1. Background File Dialog Watcher Loop ---
    def _file_dialog_watcher_loop(self):
        """Watches for any open File Dialog & automatically navigates it to the latest SKU folder."""
        last_dialog_hwnd = None
        user32 = ctypes.windll.user32

        while self.running:
            try:
                hwnd = user32.GetForegroundWindow()
                if hwnd and hwnd != last_dialog_hwnd:
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value.lower()
                        
                        cls_buff = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(hwnd, cls_buff, 256)
                        
                        if any(kw in title for kw in ["sélectionnez", "select", "ouvrir", "open", "parcourir", "browse"]) or cls_buff.value == "#32770":
                            last_dialog_hwnd = hwnd
                            target = self.latest_folder_path
                            if target and os.path.exists(target):
                                navigate_file_dialog_to_folder(hwnd, target)
                time.sleep(0.5 if LOW_RESOURCE_MODE else 0.2)
            except Exception:
                time.sleep(0.8 if LOW_RESOURCE_MODE else 0.3)

    # --- 2. HFSQL DB File Watcher ---
    def _hfsql_watcher_loop(self):
        if ARTICLE_FIC_PATH.exists():
            self.last_fic_mtime = ARTICLE_FIC_PATH.stat().st_mtime
            self.last_fic_size = ARTICLE_FIC_PATH.stat().st_size

        while self.running:
            try:
                if ARTICLE_FIC_PATH.exists():
                    current_mtime = ARTICLE_FIC_PATH.stat().st_mtime
                    current_size = ARTICLE_FIC_PATH.stat().st_size
                    
                    if current_mtime != self.last_fic_mtime or current_size != self.last_fic_size:
                        log("\n💾 GestCaisse Database (Article.FIC) update detected!")
                        self.last_fic_mtime = current_mtime
                        self.last_fic_size = current_size
                        
                        skus = extract_skus_from_db()
                        if skus:
                            for sku in skus[-3:]:
                                self.process_detected_sku(sku, "HFSQL Database (Article.FIC)")

                time.sleep(15 if LOW_RESOURCE_MODE else 2)
            except Exception:
                time.sleep(15 if LOW_RESOURCE_MODE else 2)

    # --- 3. Clipboard Monitor ---
    def _clipboard_monitor_loop(self):
        last_clip = ""
        try:
            last_clip = pyperclip.paste().strip()
        except Exception:
            pass

        while self.running:
            try:
                clip = pyperclip.paste().strip()
                if clip and clip != last_clip:
                    if not re.match(r'^[a-zA-Z]:[\\/]', clip) and not clip.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                        match = SKU_PATTERN.search(clip)
                        if match:
                            sku = match.group(1)
                            last_clip = clip
                            self.process_detected_sku(sku, "Clipboard")
                time.sleep(2 if LOW_RESOURCE_MODE else 1)
            except Exception:
                time.sleep(2 if LOW_RESOURCE_MODE else 1)

    # --- 4. 1-Touch Hotkey Assistant (F2) ---
    def _on_key_release(self, key):
        if key == keyboard.Key.f2:
            log("\n⚡ Hotkey [F2] pressed! Auto-selecting reference & downloading 3 candidate images...")
            self.current_gestcaisse_hwnd = ctypes.windll.user32.GetForegroundWindow()
            
            # Simulate Ctrl+A to select text in field
            kb_controller.press(Key.ctrl)
            kb_controller.press('a')
            kb_controller.release('a')
            kb_controller.release(Key.ctrl)
            time.sleep(0.08)
            
            # Simulate Ctrl+C to copy text
            kb_controller.press(Key.ctrl)
            kb_controller.press('c')
            kb_controller.release('c')
            kb_controller.release(Key.ctrl)
            time.sleep(0.12)

            try:
                clip = pyperclip.paste().strip()
                match = SKU_PATTERN.search(clip)
                if match:
                    self.process_detected_sku(match.group(1), "Hotkey F2")
                else:
                    try:
                        winsound.Beep(400, 150)
                    except Exception:
                        pass
                    log(f"  ⚠️ Text in active field ('{clip[:30]}') does not match SKU pattern.")
            except Exception as e:
                log(f"  ⚠️ Hotkey error: {e}")

    def start(self):
        self.running = True
        log("=========================================================")
        log("🤖 SMART GestCaisse Bridge - MULTI-IMAGE SELECTOR (F2)")
        log("   👉 Press [F2] in GestCaisse:")
        log("   1. Downloads 3 best candidate images into a dedicated SKU folder")
        log("   2. Opens GestCaisse File Dialog navigated directly into that folder")
        log("   3. YOU choose the exact image you want with 1 click!")
        log("=========================================================\n")

        dialog_thread = threading.Thread(target=self._file_dialog_watcher_loop, daemon=True)
        dialog_thread.start()

        db_thread = threading.Thread(target=self._hfsql_watcher_loop, daemon=True)
        db_thread.start()

        clip_thread = threading.Thread(target=self._clipboard_monitor_loop, daemon=True)
        clip_thread.start()

        try:
            self.keyboard_listener = keyboard.Listener(on_release=self._on_key_release)
            self.keyboard_listener.start()
        except Exception as e:
            log(f"  ⚠️ Keyboard listener notice: {e}")

    def stop(self):
        self.running = False
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        log("Daemon stopped.")
