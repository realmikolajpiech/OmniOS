import sys
import os
import subprocess
import requests
import threading
from urllib.parse import urlparse
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QListWidget, QListWidgetItem, QFrame, QAbstractItemView,
                             QGraphicsDropShadowEffect, QLabel, QScrollArea, QProgressBar, QMessageBox)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve, QPoint, QRect, QEvent, QTimer, QUrl
from PyQt6.QtGui import QColor, QFont, QIcon, QPixmap, QPainter, QPainterPath, QBrush, QDesktopServices, QCursor, QGuiApplication
import traceback
import json
import re
import logging
import random

# --- LOGGING SETUP ---
logging.basicConfig(
    filename="/tmp/omni_debug.log",
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def exception_hook(exctype, value, tb):
    logging.critical("Uncaught exception:", exc_info=(exctype, value, tb))
    sys.__excepthook__(exctype, value, tb)
    
sys.excepthook = exception_hook

import atexit
import signal

# --- INSTANCE LOCK ---
LOCK_FILE = "/tmp/omni_app.lock"

def check_and_handle_existing_instance():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                pid = int(f.read().strip())
            
            # Check if process is running
            os.kill(pid, 0)
            
            # If we get here, process exists. Kill it (Toggle OFF)
            print(f"Omni is already running (PID {pid}). Stopping it...")
            os.kill(pid, signal.SIGTERM)
            sys.exit(0)
            
        except (ValueError, ProcessLookupError, FileNotFoundError):
            # Stale lock or process not running
            pass
        except Exception as e:
            print(f"Error checking lock: {e}")

    # Register cleanup
    def cleanup():
        if os.path.exists(LOCK_FILE):
            try:
                os.remove(LOCK_FILE)
            except: pass

    atexit.register(cleanup)
    
    # Write new PID
    with open(LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))

check_and_handle_existing_instance()

# CONFIG
BRAIN_URL = "http://127.0.0.1:5500/ask"
LOGO_PATH = os.environ.get("OMNI_LOGO", "/home/miki/OmniOS/assets/omni-logo.png")

# --- DESIGN SYSTEM ---
# Default to local omni.css if env is not set
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STYLE_SHEET_PATH = os.environ.get("OMNI_STYLE", os.path.join(SCRIPT_DIR, "omni.css"))

STYLE_SHEET = ""
if STYLE_SHEET_PATH and os.path.exists(STYLE_SHEET_PATH):
    with open(STYLE_SHEET_PATH, "r") as f:
        STYLE_SHEET = f.read()

class AIWorker(QThread):
    finished = pyqtSignal(str)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        try:
            r = requests.post(BRAIN_URL, json={"query": self.query}, timeout=120)
            answer = r.json().get("answer", "No answer received.")
            self.finished.emit(answer)
        except requests.exceptions.ConnectionError:
            self.finished.emit("The Omni AI hasn't loaded yet. Please try again in a moment.")
        except Exception as e:
            self.finished.emit(f"System Error: {str(e)}")

class SearchWorker(QThread):
    results_found = pyqtSignal(list, str) # results, query_at_start

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        try:
            # Semantic Search
            r = requests.post("http://127.0.0.1:5500/search", json={"query": self.query}, timeout=5)
            results = r.json().get("results", [])
            self.results_found.emit(results, self.query)
        except:
            self.results_found.emit([], self.query)

class LinkActionWidget(QWidget):
    icon_downloaded = pyqtSignal(object) # Use object for safer passing of bytes

    def __init__(self, title, url, description, parent=None):
        super().__init__(parent)
        self.url = url
        self.icon_thread = None # Keep reference
        
        # Connect signal
        self.icon_downloaded.connect(self.update_icon)
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)
        
        # 1. Top Row: Icon + Action Text
        top_row = QWidget()
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)
        
        # Icon Label
        self.icon_label = QLabel("🌐") 
        self.icon_label.setFixedSize(16, 16)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("color: #007AFF; font-size: 12px;")
        
        # Action Label ("Open Link")
        self.action_label = QLabel(f"Open {url}")
        self.action_label.setStyleSheet("color: #007AFF; font-size: 13px; font-weight: 600;")
        
        top_layout.addWidget(self.icon_label)
        top_layout.addWidget(self.action_label)
        top_layout.addStretch() 
        
        # Main Title
        self.title_label = QLabel(title)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("color: #1d1d1f; font-size: 16px; font-weight: 700;")
        
        # Description
        self.desc_label = QLabel(description)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #8E8E93; font-size: 13px; font-weight: 400;")
        
        layout.addWidget(top_row)
        layout.addWidget(self.title_label)
        layout.addWidget(self.desc_label)
        
        self.fetch_icon()

    def fetch_icon(self):
        try:
            # print(f"DEBUG: Fetching icon for URL: {self.url}")
            if not self.url: return
            
            # 1. Clean URL
            clean_url = self.url.strip().strip('<>').strip('"').strip("'")
            
            # 2. Add schema if missing for parsing
            if not clean_url.startswith("http") and not clean_url.startswith("//"):
                clean_url = "https://" + clean_url
                
            parsed = urlparse(clean_url)
            domain = parsed.netloc
            
            # Fallback for simple strings like "google.com" passed through logic
            if not domain and parsed.path:
                possible = parsed.path.split('/')[0]
                if '.' in possible: domain = possible

            if not domain: return

            # Normalize domain (strip www.) for better favicon hit rate
            if domain.startswith("www."):
                domain = domain[4:]
            
            # 3. Fetch
            icon_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
            
            self.icon_thread = threading.Thread(target=self._download_icon, args=(icon_url,), daemon=True)
            self.icon_thread.start()
        except Exception as e:
            print(f"Error starting icon thread: {e}")

    def _download_icon(self, url):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            r = requests.get(url, headers=headers, timeout=3)
            if r.status_code == 200:
                self.icon_downloaded.emit(r.content)
        except: pass

    def update_icon(self, data):
        try:
            # Check if C++ object is still alive
            if not self.icon_label: return
        except RuntimeError:
            return # C++ object deleted

        try:
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            if not pixmap.isNull():
                self.icon_label.setText("") 
                self.icon_label.setPixmap(pixmap.scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        except RuntimeError: return # Catch underlying C++ deletion during operation
        except Exception: pass

    def sizeHint(self):
        w = 520 
        header_h = 32
        title_h = self.title_label.heightForWidth(w)
        desc_h = self.desc_label.heightForWidth(w)
        h = 32 + 12 + header_h + title_h + desc_h + 20 
        return QSize(600, h)

class InstallActionWidget(LinkActionWidget):
    def __init__(self, name, website_url, parent=None):
        # Use website URL for icon fetching, or fallback
        url_for_icon = website_url if website_url else f"https://google.com/search?q={name}"
        
        super().__init__(f"Install {name}", url_for_icon, "Click to install via apt/flatpak", parent)
        
        # Override Styling for Install context
        self.action_label.setText("")
        self.action_label.setStyleSheet("background: transparent;")
        
        # Create a layout for the "action_label" container
        layout = QHBoxLayout(self.action_label)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # --- Helper for Key Badge ---
        def create_key(text):
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("""
                background-color: #FFFFFF;
                border: 1px solid #D1D1D6;
                border-bottom: 2px solid #C7C7CC;
                border-radius: 5px;
                color: #1d1d1f;
                padding: 3px 6px;
                font-family: "Manrope";
                font-size: 10px;
                font-weight: 800;
            """)
            return lbl

        # [TAB]
        layout.addWidget(create_key("TAB"))
        
        # "Install"
        lbl_install = QLabel("Install")
        lbl_install.setStyleSheet("color: #34C759; font-weight: 700; font-size: 13px; font-family: 'Manrope';")
        layout.addWidget(lbl_install)
        
        # Spacer
        layout.addSpacing(12)
        
        # [ENTER]
        layout.addWidget(create_key("ENTER"))
        
        # "Website"
        lbl_web = QLabel("Website")
        lbl_web.setStyleSheet("color: #8E8E93; font-weight: 600; font-size: 13px; font-family: 'Manrope';")
        layout.addWidget(lbl_web)
        
        layout.addStretch() # Push left
        
        self.icon_label.setText("⬇")
        self.icon_label.setStyleSheet("color: #34C759; font-size: 14px;")
        
        # Specific overrides
        self.title_label.setStyleSheet("color: #1d1d1f; font-size: 18px; font-weight: 700;")
        self.desc_label.setText("Available via apt/flatpak")
        self.desc_label.setStyleSheet("color: #8E8E93; font-size: 13px;")

class PersonActionWidget(QWidget):
    image_downloaded = pyqtSignal(object)

    def __init__(self, name, description, image_url, url, parent=None):
        super().__init__(parent)
        self.image_url = image_url
        self.url = url or ""
        
        self.image_downloaded.connect(self.update_image)
        
        # Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)
        
        # 1. Avatar (Vertical Portrait)
        self.avatar = QLabel()
        self.avatar.setFixedSize(100, 150)
        self.avatar.setStyleSheet("background-color: #E5E5EA; border-radius: 12px; border: 1px solid rgba(0,0,0,0.05);")
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 2. Info (Right)
        info_layout = QVBoxLayout()
        info_layout.setSpacing(6)
        info_layout.setContentsMargins(0, 4, 0, 0) 
        
        # Clean Name
        display_name = name.replace(" - Wikipedia", "").strip()
        
        self.name_label = QLabel(display_name)
        self.name_label.setFont(QFont("Manrope", 24, QFont.Weight.Bold))
        self.name_label.setStyleSheet("color: #1d1d1f; letter-spacing: -0.5px;")
        self.name_label.setWordWrap(True)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        self.desc_label = QLabel(description)
        self.desc_label.setFont(QFont("Manrope", 15, QFont.Weight.Normal))
        self.desc_label.setStyleSheet("color: #3A3A3C; line-height: 1.4;")
        self.desc_label.setWordWrap(True)
        self.desc_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        # Small link indicator
        domain = urlparse(url).netloc.replace("www.", "")
        self.link_label = QLabel(f"Source: {domain}" if url else "Unknown Source")
        self.link_label.setFont(QFont("Manrope", 12, QFont.Weight.DemiBold))
        self.link_label.setStyleSheet("color: #007AFF; margin-top: 8px;")
        
        info_layout.addWidget(self.name_label)
        info_layout.addWidget(self.desc_label)
        info_layout.addWidget(self.link_label)
        info_layout.addStretch()
        
        layout.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(info_layout)
        
        # Default to Initials
        self.avatar.setText(display_name[0])
        self.avatar.setStyleSheet("background-color: #007AFF; color: white; font-size: 48px; font-weight: bold; border-radius: 12px;")
        
        if self.image_url:
            threading.Thread(target=self._download_image, daemon=True).start()

    def _download_image(self):
        try:
            # 0. Handle Data URIs (Base64)
            if self.image_url.startswith("data:"):
                try:
                    import base64
                    header, encoded = self.image_url.split(",", 1)
                    data = base64.b64decode(encoded)
                    self.image_downloaded.emit(data)
                    return
                except: pass

            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
            }
            
            # verify=False to avoid SSL issues
            r = requests.get(self.image_url, headers=headers, timeout=10, verify=False)
            if r.status_code == 200:
                self.image_downloaded.emit(r.content)
        except Exception as e:
            print(f"Image download error: {e}")

    def update_image(self, data):
        # 1. Safety Check
        try:
            if not self.avatar: return 
        except RuntimeError:
            return

        try:
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            if not pixmap.isNull():
                # Target Size
                w, h = 100, 150
                rounded = QPixmap(w, h)
                rounded.fill(Qt.GlobalColor.transparent)
                
                painter = QPainter(rounded)
                try:
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    path = QPainterPath()
                    # Rounded Rect
                    path.addRoundedRect(0, 0, w, h, 12, 12)
                    painter.setClipPath(path)
                    
                    # Scale to cover (KeepAspectRatioByExpanding)
                    scaled = pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                    
                    # Center crop
                    x = (scaled.width() - w) // 2
                    y = (scaled.height() - h) // 2
                    
                    painter.drawPixmap(-x, -y, scaled)
                finally:
                    painter.end()
                
                self.avatar.setPixmap(rounded)
                self.avatar.setStyleSheet("background-color: transparent;")
                self.avatar.repaint()
        except Exception as e:
            print(f"Error updating person image: {e}")

    def sizeHint(self):
        # Dynamic Height Calculation
        w_text = 440
        
        name_h = self.name_label.heightForWidth(w_text)
        desc_h_raw = self.desc_label.heightForWidth(w_text)
        desc_h = int(desc_h_raw * 1.5) 
        name_h = int(name_h * 1.3)
        
        link_h = self.link_label.heightForWidth(w_text) + 8
        
        text_total_h = name_h + desc_h + link_h + 12 
        
        img_min_h = 150 + 48
        
        final_h = max(img_min_h, text_total_h + 24)
        
        return QSize(600, final_h)

class PlaceActionWidget(PersonActionWidget):
    def __init__(self, name, description, image_url, url, lat, lon, parent=None):
        super().__init__(name, description, image_url, url, parent)
        
        # If no image provided, try to generate a Static Map
        if not image_url and lat and lon:
            # Use a free static map service (e.g. OSM based)
            # This is a fallback to ensure a map is displayed
            self.image_url = f"https://staticmap.openstreetmap.de/staticmap.php?center={lat},{lon}&zoom=13&size=200x300&markers={lat},{lon},red-pushpin"
            threading.Thread(target=self._download_image, daemon=True).start()
            
        # Customize Styling for Place
        self.avatar.setStyleSheet("background-color: #F2F2F7; border-radius: 12px; border: 1px solid rgba(0,0,0,0.1);")
        if not image_url and not (lat and lon):
            self.avatar.setText("📍") # Generic Pin if all else fails
            self.avatar.setStyleSheet("background-color: #E5E5EA; color: #FF3B30; font-size: 48px; border-radius: 12px;")

class ActionWorker(QThread):
    action_found = pyqtSignal(object, str) # action_data (dict), query

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        try:
            # Fast Action Inference
            r = requests.post("http://127.0.0.1:5500/action", json={"query": self.query}, timeout=60)
            data = r.json()
            actions = data.get("actions", [])
            if not actions and data.get("action"):
                actions = [data.get("action")]
                
            self.action_found.emit(actions, self.query)
        except:
            self.action_found.emit([], self.query)

class InstallWorker(QThread):
    progress_update = pyqtSignal(str) # Status text
    finished = pyqtSignal(bool, str) # Success, Message

    def __init__(self, app_name):
        super().__init__()
        self.app_name = app_name

    def run(self):
        try:
            # 1. Get Plan
            self.progress_update.emit(f"Checking Packages for '{self.app_name}'...")
            r = requests.post(f"{BRAIN_URL.replace('/ask', '')}/install_plan", json={"app_name": self.app_name}, timeout=30)
            if r.status_code != 200:
                self.finished.emit(False, "Brain connection failed.")
                return
            
            plan = r.json()
            method = plan.get("method")
            desc = plan.get("description", "Installing...")
            commands = plan.get("commands", [])
            
            if method == "failed" or not commands:
                self.finished.emit(False, "Could not find a way to install this app.")
                return

            self.progress_update.emit(f"{desc}...")
            
            # 2. Execute Commands
            for cmd in commands:
                self.progress_update.emit("Installing (check popup)...")
                print(f"DEBUG: Executing command: '{cmd}'")
                logging.info(f"DEBUG: Executing command: '{cmd}'")
                
                # Run command (blocking)
                # Note: apt commands likely use pkexec for gui prompt
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if res.returncode != 0:
                     self.finished.emit(False, f"Command failed: {cmd}\n{res.stderr}")
                     return
            
            self.finished.emit(True, f"Successfully installed {self.app_name}!")
            
        except Exception as e:
            self.finished.emit(False, f"Installation Error: {str(e)}")

class ThinkingWidget(QWidget):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.full_text = text
        self.is_expanded = False
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 4, 0, 4)
        self.main_layout.setSpacing(0)
        
        # Header
        self.header = QLabel("▾  Thinking")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setFixedHeight(34)
        self.header.setMinimumWidth(120)
        self.header.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0.05);
                border-radius: 8px;
                padding: 0px 14px;
                font-size: 13px;
                font-weight: 600;
                color: rgba(60, 60, 67, 0.5);
            }
            QLabel:hover {
                background-color: rgba(0, 0, 0, 0.08);
            }
        """)
        self.header.mousePressEvent = self.toggle_expand
        
        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setHidden(True)
        self.scroll_area.setMaximumHeight(200)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
                margin-top: 6px;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 0, 0, 0.1);
                border-radius: 2px;
            }
        """)
        
        self.content_label = QLabel(text)
        self.content_label.setWordWrap(True)
        self.content_label.setStyleSheet("""
            QLabel {
                background-color: transparent;
                padding: 8px 12px 12px 12px;
                font-size: 14px;
                line-height: 1.5;
                color: rgba(60, 60, 67, 0.7);
                font-style: italic;
            }
        """)
        self.scroll_area.setWidget(self.content_label)
        
        self.main_layout.addWidget(self.header)
        self.main_layout.addWidget(self.scroll_area)
        
        self.setMinimumHeight(42)

    def sizeHint(self):
        w = 616
        h = 42 
        if self.is_expanded:
            content_h = self.content_label.heightForWidth(w) + 20
            h += min(content_h, 200) + 6
        return QSize(w, h)

    def toggle_expand(self, event):
        self.is_expanded = not self.is_expanded
        self.scroll_area.setHidden(not self.is_expanded)
        self.header.setText("▴ Thinking" if self.is_expanded else "▾ Thinking")
        
        self.setMinimumHeight(self.sizeHint().height())
        self.update_item_size()

    def update_item_size(self):
        list_widget = self.window().findChild(QListWidget)
        if list_widget:
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if list_widget.itemWidget(item) == self:
                    item.setSizeHint(self.sizeHint())
                    break
            if hasattr(self.window(), "adjust_window_height"):
                self.window().adjust_window_height()

class AnswerWidget(QWidget):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 5, 15, 5)
        self.layout.setSpacing(0)
        
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setFont(QFont("Manrope", 20, QFont.Weight.Medium))
        self.label.setStyleSheet("color: #1d1d1f; line-height: 1.3;")
        
        self.layout.addWidget(self.label)
        
    def sizeHint(self):
        w = 550
        h = self.label.heightForWidth(w) + 60
        return QSize(w, h)

class OmniWindow(QWidget):
    def __init__(self):
        super().__init__()
        # Frameless & Translucent
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowIcon(QIcon(LOGO_PATH))
        self.setWindowTitle("Omni Intelligence")
        self.resize(720, 140)
        self.center()
        self.initial_top = self.y()
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(300)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuart)
        
        # Main Layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 15, 40, 15)
        
        # The Content Frame
        self.frame = QFrame()
        self.frame.setObjectName("MainFrame")
        
        # Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0, 0, 0, 40)) 
        self.frame.setGraphicsEffect(shadow)
        
        # Inner Layout
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)
        
        # Input
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Search or ask Omni...")
        self.input_field.textChanged.connect(self.on_text_changed)
        self.input_field.returnPressed.connect(self.on_entered)
        self.input_field.installEventFilter(self)
        
        # Divider
        self.divider = QFrame()
        self.divider.setObjectName("Divider")
        
        # List
        self.list_widget = QListWidget()
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.itemClicked.connect(self.on_entered)
        self.list_widget.setWordWrap(True) 
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_widget.verticalScrollBar().setSingleStep(20)
        self.list_widget.setStyleSheet("QListWidget { outline: none; }")
        
        frame_layout.addWidget(self.input_field)
        frame_layout.addWidget(self.divider)
        frame_layout.addWidget(self.list_widget)
        main_layout.addWidget(self.frame)
        
        self.setStyleSheet(STYLE_SHEET)
        
        # Data
        self.apps = self.load_apps()
        self.refresh_list("")

        # Entry Animation
        self.animate_entry()
        self.adjust_window_height()

        # Workers
        self.search_worker = None
        self.action_worker = None
        self.ai_worker = None
        
        # Debounce Timer
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(400)
        self.debounce_timer.timeout.connect(self.trigger_async_searches)

    def adjust_window_height(self):
        list_h = 0
        has_ai_answer = False
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            widget = self.list_widget.itemWidget(item)
            if widget and widget.__class__.__name__ == "AnswerWidget":
                has_ai_answer = True
            list_h += item.sizeHint().height() + 6
        
        buffer = 20 if has_ai_answer else 4
        target_list_h = list_h + buffer if self.list_widget.count() > 0 else 0
        
        target_h = 87 + target_list_h
        target_h = min(target_h, 800)
        
        if self.list_widget.count() == 0:
            target_h = 76
            self.divider.hide()
        else:
            self.divider.show() 

        screen_geo = self.screen().availableGeometry()
        screen_center_y = screen_geo.center().y()
        
        # Target Geometry
        target_y = int(screen_center_y - 120 - (target_h / 2))
        target_x = screen_geo.x() + (screen_geo.width() - self.width()) // 2
        
        start_rect = self.geometry()
        end_rect = QRect(target_x, target_y, self.width(), int(target_h))
        
        if start_rect != end_rect:
            self.anim.stop()
            self.anim.setStartValue(start_rect)
            self.anim.setEndValue(end_rect)
            self.anim.start()

    def handle_semantic_results(self, results, original_query):
        current_text = self.input_field.text()
        if current_text != original_query: return 

        if not results: return

        existing_paths = set()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            d = item.data(Qt.ItemDataRole.UserRole)
            if d and 'path' in d: existing_paths.add(d['path'])

        for res in results:
            if res['path'] in existing_paths: continue
            
            item = QListWidgetItem(res['name'])
            item.setData(Qt.ItemDataRole.UserRole, res)
            item.setSizeHint(QSize(600, 50))
            self.list_widget.addItem(item)
        
            self.list_widget.scrollToBottom()
            self.adjust_window_height()

    def handle_action_result(self, actions_list, query):
        current_text = self.input_field.text()
        logging.info(f"Action found: {len(actions_list) if actions_list else 0}")
        
        if current_text.strip() != query.strip(): return

        if not actions_list: return
        
        if not isinstance(actions_list, list):
            actions_list = [actions_list]

        # FILTERING LOGIC: If we have a Person or Place, hide generic links to avoid clutter
        has_rich_card = any(x.get('type') in ['person', 'place'] for x in actions_list)
        if has_rich_card:
            # Keep only rich cards and critical actions (like install)
            actions_list = [x for x in actions_list if x.get('type') in ['person', 'place', 'install']]

        # Clear existing fast actions
        while True:
            first_item = self.list_widget.item(0)
            if not first_item: break
            data = first_item.data(Qt.ItemDataRole.UserRole)
            if data and isinstance(data, dict) and data.get('type') == 'fast_action':
                self.list_widget.takeItem(0)
            else:
                break
        
        # Insert New Actions
        for action_data in reversed(actions_list):
            item = QListWidgetItem()
            
            if isinstance(action_data, dict) and action_data.get('type') == 'link':
                widget = LinkActionWidget(
                    title=action_data.get('title', 'Link'),
                    url=action_data.get('url', ' '.strip()),
                    description=action_data.get('description', ' '.strip())
                )
                item.setSizeHint(widget.sizeHint())
                item.setData(Qt.ItemDataRole.UserRole, {"type": "fast_action", "action_data": action_data})
                self.list_widget.insertItem(0, item)
                self.list_widget.setItemWidget(item, widget)
                
            elif isinstance(action_data, dict) and action_data.get('type') == 'person':
                widget = PersonActionWidget(
                    name=action_data.get('name', 'Person'),
                    description=action_data.get('description', ' '),
                    image_url=action_data.get('image'),
                    url=action_data.get('url')
                )
                item.setSizeHint(widget.sizeHint())
                item.setData(Qt.ItemDataRole.UserRole, {"type": "fast_action", "action_data": action_data})
                self.list_widget.insertItem(0, item)
                self.list_widget.setItemWidget(item, widget)

            elif isinstance(action_data, dict) and action_data.get('type') == 'place':
                widget = PlaceActionWidget(
                    name=action_data.get('name', 'Place'),
                    description=action_data.get('description') or action_data.get('address', ' '),
                    image_url=action_data.get('image'),
                    url=action_data.get('url'),
                    lat=action_data.get('latitude'),
                    lon=action_data.get('longitude')
                )
                item.setSizeHint(widget.sizeHint())
                item.setData(Qt.ItemDataRole.UserRole, {"type": "fast_action", "action_data": action_data})
                self.list_widget.insertItem(0, item)
                self.list_widget.setItemWidget(item, widget)

            elif isinstance(action_data, dict) and action_data.get('type') == 'status':
                    text = f"⚡ {action_data.get('content')}"
                    item.setText(text)
                    item.setForeground(QColor("#8E8E93"))
                    font = item.font(); font.setItalic(True); item.setFont(font)
                    item.setData(Qt.ItemDataRole.UserRole, {"type": "fast_action", "action_data": action_data})
                    self.list_widget.insertItem(0, item)

            elif isinstance(action_data, dict) and action_data.get('type') == 'calc':
                    val = action_data.get('content')
                    item.setText(f"  {val}")
                    item.setForeground(QColor("#AF52DE"))
                    font = item.font(); font.setBold(True); font.setPointSize(22); item.setFont(font)
                    item.setData(Qt.ItemDataRole.UserRole, {"type": "fast_action", "action_data": action_data})
                    self.list_widget.insertItem(0, item)

            elif isinstance(action_data, dict) and action_data.get('type') == 'install':
                    app_name = action_data.get('name')
                    website = action_data.get('website')
                    
                    is_installed = False
                    for app in self.apps:
                        if app_name.lower() in app['name'].lower():
                            is_installed = True
                            break
                    
                    if not is_installed:
                        widget = InstallActionWidget(app_name, website)
                        item.setSizeHint(widget.sizeHint())
                        item.setData(Qt.ItemDataRole.UserRole, {"type": "fast_action", "action_data": action_data})
                        self.list_widget.insertItem(0, item)
                        self.list_widget.setItemWidget(item, widget)
                    
            else:
                if isinstance(action_data, str):
                        text = action_data
                else:
                        text = action_data.get('content', str(action_data))
                        
                item.setText(f"⚡ {text}")
                item.setForeground(QColor("#007AFF"))
                font = item.font(); font.setBold(True); item.setFont(font)
                item.setData(Qt.ItemDataRole.UserRole, {"type": "fast_action", "action_data": action_data})
                self.list_widget.insertItem(0, item)
            
        self.list_widget.setCurrentRow(0)
        self.adjust_window_height()

    def center(self):
        # Center on the screen containing the mouse cursor
        cursor_pos = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor_pos)
        
        if not screen:
            screen = QApplication.primaryScreen()
            
        if screen:
            geo = screen.availableGeometry()
            # Calculate center manually
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            
            # Apply visual offset (higher is better for launchers)
            y = y - 120
            if y < 20: y = 20
            
            # Explicit integer casting
            self.move(int(x), int(y))
            logging.info(f"Centering: Cursor={cursor_pos}, Screen={geo}, Target=({x},{y})")
        else:
            # Fallback
            qr = self.frameGeometry()
            cp = self.screen().availableGeometry().center()
            qr.moveCenter(cp)
            qr.moveTop(qr.top() - 100)
            self.move(qr.topLeft())

    def animate_entry(self):
        self.anim_geo = QPropertyAnimation(self, b"geometry")
        self.anim_geo.setDuration(600)
        self.anim_geo.setStartValue(QRect(self.x(), self.y() + 30, self.width(), self.height()))
        self.anim_geo.setEndValue(QRect(self.x(), self.y(), self.width(), self.height()))
        self.anim_geo.setEasingCurve(QEasingCurve.Type.OutBack)
        
        self.anim_opa = QPropertyAnimation(self, b"windowOpacity")
        self.anim_opa.setDuration(400)
        self.anim_opa.setStartValue(0)
        self.anim_opa.setEndValue(1)
        
        self.anim_geo.start()
        # self.anim_opa.start()
        
    def eventFilter(self, obj, event):
        if obj == self.input_field and event.type() == QEvent.Type.KeyPress:
            key = event.key()

            if key == Qt.Key.Key_Down:
                current = self.list_widget.currentRow()
                if current < self.list_widget.count() - 1:
                    self.list_widget.setCurrentRow(current + 1)
                return True
            elif key == Qt.Key.Key_Up:
                current = self.list_widget.currentRow()
                if current > 0:
                    self.list_widget.setCurrentRow(current - 1)
                return True
            elif key == Qt.Key.Key_Tab:
                item = self.list_widget.currentItem()
                if item:
                    data = item.data(Qt.ItemDataRole.UserRole)
                    if data and isinstance(data, dict):
                         if data.get('type') == 'fast_action':
                             action_data = data.get('action_data')
                             if action_data and action_data.get('type') == 'install':
                                 name = action_data.get('name')
                                 self.start_autonomous_install(name)
                                 return True
        return super().eventFilter(obj, event)

    def start_autonomous_install(self, app_name):
        self.list_widget.clear()
        
        self.input_field.blockSignals(True)
        self.input_field.setDisabled(True)
        self.input_field.setText(f"Installing {app_name}...")
        self.input_field.blockSignals(False)
        
        item = QListWidgetItem(f"Initializing...")
        item.setFont(QFont("Manrope", 16, QFont.Weight.Medium))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        item.setSizeHint(QSize(600, 40)) 
        self.list_widget.addItem(item)
        self.install_status_item = item
        
        pbar_item = QListWidgetItem(self.list_widget)
        pbar_item.setFlags(pbar_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        
        self.install_pbar = QProgressBar()
        self.install_pbar.setRange(0, 1000)
        self.install_pbar.setValue(0)
        self.install_pbar.setTextVisible(True)
        self.install_pbar.setFormat("%p%")
        self.install_pbar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.install_pbar.setFixedHeight(24) 
        
        self.install_pbar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: rgba(0, 0, 0, 0.05);
                border-radius: 12px;
                text-align: center;
                color: rgba(60, 60, 67, 0.6);
                font-family: "Manrope";
                font-weight: 700;
                font-size: 12px;
                margin-left: 40px;
                margin-right: 40px;
            }
            QProgressBar::chunk {
                background-color: #007AFF;
                border-radius: 12px;
            }
        """)
        
        pbar_item.setSizeHint(QSize(600, 60)) 
        self.list_widget.setItemWidget(pbar_item, self.install_pbar)
        
        self.adjust_window_height()
        
        self.install_progress_val = 0.0
        self.install_timer = QTimer()
        self.install_timer.setInterval(20)
        self.install_timer.timeout.connect(self.update_fake_progress)
        self.install_timer.start()
        
        self.install_worker = InstallWorker(app_name)
        self.install_worker.progress_update.connect(self.update_install_status)
        self.install_worker.finished.connect(self.finish_install)
        self.install_worker.start()

    def update_fake_progress(self):
        current = self.install_progress_val
        increment = 0.0
        if current < 30: increment = random.uniform(0.5, 1.5)
        elif current < 60:
            increment = random.uniform(0.1, 0.4)
            if random.random() < 0.1: increment = 0
        elif current < 85: increment = random.uniform(0.01, 0.15)
        elif current < 99: increment = random.uniform(0.001, 0.02)
             
        self.install_progress_val += increment
        if self.install_progress_val > 99: self.install_progress_val = 99
        self.install_pbar.setValue(int(self.install_progress_val * 10))

    def update_install_status(self, status):
        if self.install_status_item:
            self.install_status_item.setText(status)
            
    def finish_install(self, success, message):
        if hasattr(self, 'install_timer'):
            self.install_timer.stop()
            
        self.list_widget.clear()
        
        aw = AnswerWidget(message)
        if success:
             aw.label.setStyleSheet("color: #34C759; line-height: 1.3;")
        else:
             aw.label.setStyleSheet("color: #FF3B30; line-height: 1.3;")
             
        item = QListWidgetItem(self.list_widget)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        item.setSizeHint(aw.sizeHint())
        self.list_widget.setItemWidget(item, aw)
        
        self.input_field.blockSignals(True)
        self.input_field.setDisabled(False)
        self.input_field.setText("")
        self.input_field.setFocus()
        self.input_field.blockSignals(False)
        
        self.adjust_window_height()
        
        if success:
            self.apps = self.load_apps()

    def load_apps(self):
        apps = []
        # UPDATED: Standard Linux XDG Paths
        paths = ["/usr/share/applications", os.path.expanduser("~/.local/share/applications")]
        seen = set()
        for p in paths:
            if not os.path.exists(p): continue
            try:
                for f in os.listdir(p):
                    if f.endswith(".desktop"):
                        full_path = os.path.join(p, f)
                        
                        name = f.replace(".desktop", "").replace("-", " ").title()
                        icon = "application-x-executable"
                        no_display = False
                        
                        try:
                            with open(full_path, 'r', errors='ignore') as df:
                                for line in df:
                                    stripped = line.strip()
                                    if stripped.startswith("[") and stripped != "[Desktop Entry]":
                                        break

                                    if stripped.startswith("Name="):
                                        name = stripped.split("=", 1)[1]
                                    elif stripped.startswith("Icon="):
                                        icon = stripped.split("=", 1)[1]
                                    elif stripped.startswith("NoDisplay=true"):
                                        no_display = True
                        except: pass
                        
                        if no_display: continue
                        if name in seen: continue
                        seen.add(name)
                        apps.append({"name": name, "path": full_path, "icon": icon, "type": "app"})
            except: continue
        return sorted(apps, key=lambda x: x['name'])

    def search_files(self, query):
        if not query or len(query) < 2: return []
        try:
            cmd = ["fd", "--max-results", "5", "--type", "f", "--type", "d", "--exclude", ".*", query, os.path.expanduser("~")]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1)
            paths = result.stdout.strip().split('\n')
            items = []
            for p in paths:
                if not p: continue
                name = os.path.basename(p)
                if not name: name = p
                is_dir = os.path.isdir(p)
                icon = "folder" if is_dir else "text-x-generic"
                items.append({"name": name, "path": p, "icon": icon, "type": "file"})
            return items
        except:
            return []

    def on_text_changed(self, text):
        self.refresh_list(text)

    def refresh_list(self, query):
        self.list_widget.clear()
        
        if not query:
            self.adjust_window_height()
            return
        
        display_text = f"Ask Omni: {query}" if query else "Ask Omni..."
        ai_item = QListWidgetItem(display_text)
        ai_item.setData(Qt.ItemDataRole.UserRole, {"type": "ai", "query": query})
        ai_item.setSizeHint(QSize(600, 50)) 
        
        query_lower = query.lower()
        app_matches = []
        for app in self.apps:
            if query_lower in app['name'].lower():
                app_matches.append(app)
        
        file_matches = []
        if query:
            file_matches = self.search_files(query)

        final_items = []
        if app_matches:
            for app in app_matches[:9]:
                item = QListWidgetItem(app['name'])
                if app['icon']:
                    if os.path.isabs(app['icon']) and os.path.exists(app['icon']):
                            item.setIcon(QIcon(app['icon']))
                    else:
                            item.setIcon(QIcon.fromTheme(app['icon']))
                item.setData(Qt.ItemDataRole.UserRole, app)
                item.setSizeHint(QSize(600, 50))
                final_items.append(item)
            final_items.append(ai_item)
        else:
            final_items.append(ai_item)
        
        remaining_slots = 10 - len(final_items)
        for f in file_matches[:remaining_slots]:
                item = QListWidgetItem(f['name'])
                item.setIcon(QIcon.fromTheme(f['icon']))
                item.setToolTip(f['path'])
                item.setData(Qt.ItemDataRole.UserRole, f)
                item.setSizeHint(QSize(600, 50))
                final_items.append(item)
        
        for item in final_items:
            self.list_widget.addItem(item)

        self.list_widget.setCurrentRow(0)
        self.adjust_window_height()

        if len(query) >= 1:
            self.debounce_timer.start()

    def trigger_async_searches(self):
        query = self.input_field.text()
        if len(query) < 1: return

        if self.search_worker and self.search_worker.isRunning(): pass
        self.search_worker = SearchWorker(query)
        self.search_worker.results_found.connect(self.handle_semantic_results)
        self.search_worker.start()

        if self.action_worker and self.action_worker.isRunning(): pass
        self.action_worker = ActionWorker(query)
        self.action_worker.action_found.connect(self.handle_action_result)
        self.action_worker.start()

    def on_entered(self, item=None):
        if self.list_widget.currentRow() < 0: return
        
        item = item or self.list_widget.currentItem()
        if not item: return

        data = item.data(Qt.ItemDataRole.UserRole)
        
        if data['type'] == 'ai':
            query = data['query']
            if not query: return
            self.start_ai_inference(query)
            
        elif data['type'] == 'app':
            subprocess.Popen(["dex", data['path']], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.close()
            
        elif data['type'] == 'file':
            subprocess.Popen(["xdg-open", data['path']], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.close()

        elif data['type'] == 'fast_action':
            action_data = data['action_data']
            
            if isinstance(action_data, dict):
                if action_data.get('type') == 'link':
                    url = action_data.get('url')
                    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.close()
                elif action_data.get('type') == 'person':
                    url = action_data.get('url')
                    if url:
                        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        self.close()
                elif action_data.get('type') == 'calc':
                    val = action_data.get('content')
                    subprocess.run(["xclip", "-selection", "clipboard"], input=val.encode(), stderr=subprocess.DEVNULL)
                    self.close()
                elif action_data.get('type') == 'install':
                    website = action_data.get('website')
                    name = action_data.get('name')
                    
                    if website: subprocess.Popen(["xdg-open", website], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                         url = f"https://www.google.com/search?q={name}"
                         subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.close()
                elif action_data.get('type') == 'status':
                    pass
                else:
                    content = action_data.get('content', ' '.strip())
                    subprocess.run(["xclip", "-selection", "clipboard"], input=content.encode(), stderr=subprocess.DEVNULL)
                    self.close()
            else:
                action_text = str(action_data)
                if action_text.startswith("Open http"):
                    url = action_text.replace("Open ", "").strip()
                    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.close()
                else:
                        subprocess.run(["xclip", "-selection", "clipboard"], input=action_text.encode(), stderr=subprocess.DEVNULL)
                        self.close()

    def start_ai_inference(self, query):
        self.list_widget.clear()
        
        loading_item = QListWidgetItem("Thinking...")
        loading_item.setFlags(loading_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        loading_item.setFont(QFont("Manrope", 24, QFont.Weight.Medium))
        loading_item.setForeground(QColor(60, 60, 67, 120))
        self.list_widget.addItem(loading_item)
        
        self.input_field.setDisabled(True)
        self.input_field.setStyleSheet("color: rgba(60, 60, 67, 0.6);")
        
        self.ai_worker = AIWorker(query)
        self.ai_worker.finished.connect(self.display_ai_result)
        self.ai_worker.start()

    def display_ai_result(self, answer):
        try:
            self.input_field.setDisabled(False)
            self.input_field.setStyleSheet("")
            self.input_field.setFocus()
            self.list_widget.clear()
        except: pass
        
        display_text = answer
        action_data = None
        thinking_text = ""
        
        thinking_match = re.search(r'<think>(.*?)(?:</think>|$)', answer, re.DOTALL)
        if thinking_match:
            thinking_text = thinking_match.group(1).strip()
            full_match_text = re.search(r'<think>.*?(?:</think>|$)', answer, re.DOTALL).group(0)
            display_text = answer.replace(full_match_text, "").strip()
        
        try:
            if "```json" in display_text:
                parts = display_text.split("```json")
                display_text = parts[0].strip()
                json_str = parts[1].split("```")[0].strip()
                action_data = json.loads(json_str)
            else:
                match = re.search(r'(\{.*\})', display_text, re.DOTALL)
                if match:
                    json_str = match.group(1)
                    action_data = json.loads(json_str)
                    if display_text.strip() == json_str:
                        display_text = "Executing action..."
                    else:
                        display_text = display_text.replace(json_str, "").strip()
        except: pass
        
        display_text = display_text.rstrip(".… ")
        
        if thinking_text:
            tw = ThinkingWidget(thinking_text)
            item = QListWidgetItem(self.list_widget)
            item.setSizeHint(tw.sizeHint())
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.list_widget.setItemWidget(item, tw)

        if display_text:
            aw = AnswerWidget(display_text)
            answer_item = QListWidgetItem(self.list_widget)
            answer_item.setFlags(answer_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            answer_item.setSizeHint(aw.sizeHint())
            self.list_widget.setItemWidget(answer_item, aw)
            
            try:
                subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).communicate(input=display_text.encode())
            except: pass
        
        self.adjust_window_height()

        if action_data:
            action = action_data.get("action")
            info_msg = ""
            success = False
            
            try:
                if action == "browse":
                    url = action_data.get("url") or action_data.get("link")
                    if url:
                        info_msg = f"Opening {url}..."
                        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        success = True
                elif action == "search":
                    query = action_data.get("query") or action_data.get("url")
                    if query:
                        if not query.startswith("http"):
                            url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
                        else:
                            url = query
                        info_msg = f"Searching for '{query}'..."
                        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        success = True
                elif action in ["launch", "open"]:
                    name = action_data.get("name") or action_data.get("path") or action_data.get("app")
                    if name:
                        info_msg = f"Launching {name}..."
                        found = False
                        for app in self.apps:
                            if name.lower() in app['name'].lower():
                                subprocess.Popen(["dex", app['path']], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                found = True
                                break
                        if not found:
                                subprocess.Popen(["xdg-open", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        success = True
                
                if success:
                    if not display_text or display_text == "Executing action...":
                        self.list_widget.clear()
                        item = QListWidgetItem(info_msg)
                        item.setFont(QFont("Manrope", 20, QFont.Weight.Medium))
                        self.list_widget.addItem(item)
                    
                    QThread.msleep(800) 
                    self.close()
                else:
                    if not display_text or display_text == "Executing action...":
                            self.list_widget.clear()
                            err_item = QListWidgetItem(f"Could not execute '{action}'. Missing parameters.")
                            err_item.setForeground(QColor(200, 50, 50))
                            self.list_widget.addItem(err_item)

            except Exception as e:
                self.list_widget.clear()
                err_item = QListWidgetItem(f"System Error: {str(e)}")
                err_item.setForeground(QColor(200, 50, 50))
                self.list_widget.addItem(err_item)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("Omni")
        app.setApplicationDisplayName("Omni")
        app.setWindowIcon(QIcon(LOGO_PATH))
        app.setDesktopFileName("omni")
        window = OmniWindow()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        with open("/tmp/omni_crash.log", "w") as f:
            f.write(traceback.format_exc())
