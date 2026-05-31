"""
PopRemind - Interval Reminder App for Windows 11
Features: interval + datetime reminders, presets, countdown timers, save notification.
"""

import sys, json, os, threading, shutil, subprocess
from pathlib import Path
from datetime import datetime, timedelta

# ── Version & Auto-Update ──────────────────────────────────────────────────────
APP_VERSION   = "1.3.0"
GITHUB_USER   = "Aboss2130"
GITHUB_REPO   = "popremind"
RAW_URL       = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/reminder.py"
VERSION_URL   = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/version.txt"

def _check_and_update():
    """Runs in a background thread on startup. Downloads update if version is newer."""
    try:
        import urllib.request
        # Fetch latest version string from version.txt
        with urllib.request.urlopen(VERSION_URL, timeout=5) as r:
            latest = r.read().decode().strip()
        if latest == APP_VERSION:
            return  # already up to date
        # Version is different — download new reminder.py
        this_file = Path(__file__).resolve()
        backup    = this_file.with_suffix(".py.bak")
        new_file  = this_file.with_suffix(".py.new")
        with urllib.request.urlopen(RAW_URL, timeout=10) as r:
            new_code = r.read()
        # Write to .new first, then atomically replace
        new_file.write_bytes(new_code)
        shutil.copy2(this_file, backup)   # keep backup
        shutil.move(str(new_file), str(this_file))
        # Schedule restart on main thread via a flag
        _update_state["updated"] = True
        _update_state["new_version"] = latest
    except Exception:
        pass  # silently skip if offline or repo missing

_update_state = {"updated": False, "new_version": ""}

def start_updater():
    t = threading.Thread(target=_check_and_update, daemon=True)
    t.start()
    return t
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QSpinBox, QPushButton, QSystemTrayIcon,
    QMenu, QFrame, QScrollArea, QMessageBox, QCheckBox,
    QToolButton, QFileDialog, QSlider, QComboBox, QDateTimeEdit,
    QButtonGroup, QRadioButton, QSizePolicy, QStackedWidget
)
from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, Signal,
    QUrl, QDateTime, QDate, QTime
)
from PySide6.QtGui import (
    QIcon, QColor, QFont, QPixmap, QPainter, QBrush,
    QPen, QAction, QGuiApplication
)
# pygame used for audio — no clipping on playback start
try:
    import pygame as _pygame
    _pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
    _pygame.mixer.init()
    _PYGAME_OK = True
except Exception:
    _PYGAME_OK = False

# ── Config ─────────────────────────────────────────────────────────────────────
APP_NAME  = "PopRemind"
CONFIG_PATH = Path(os.getenv("APPDATA", Path.home())) / APP_NAME / "config.json"
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

PRESETS = {
    "Default (Dark Purple)": {
        "accent": "#6C63FF", "bg": "#0d1117", "card_bg": "#1e2235",
        "card_border": "#2d3450", "text": "#e2e8f0", "subtext": "#94a3b8",
        "popup_grad1": "#1e1b4b", "popup_grad2": "#312e81",
    },
    "Midnight Blue": {
        "accent": "#3b82f6", "bg": "#0a0f1e", "card_bg": "#111827",
        "card_border": "#1e3a5f", "text": "#e2e8f0", "subtext": "#93c5fd",
        "popup_grad1": "#0f172a", "popup_grad2": "#1e3a5f",
    },
    "Forest Green": {
        "accent": "#22c55e", "bg": "#0a1a0f", "card_bg": "#0f2418",
        "card_border": "#14532d", "text": "#dcfce7", "subtext": "#86efac",
        "popup_grad1": "#052e16", "popup_grad2": "#14532d",
    },
    "Sunset Orange": {
        "accent": "#f97316", "bg": "#1a0a00", "card_bg": "#1f1208",
        "card_border": "#7c2d12", "text": "#ffedd5", "subtext": "#fdba74",
        "popup_grad1": "#431407", "popup_grad2": "#7c2d12",
    },
    "Rose Pink": {
        "accent": "#ec4899", "bg": "#1a0010", "card_bg": "#1f0818",
        "card_border": "#831843", "text": "#fce7f3", "subtext": "#f9a8d4",
        "popup_grad1": "#500724", "popup_grad2": "#831843",
    },
    "Light Mode": {
        "accent": "#6C63FF", "bg": "#f1f5f9", "card_bg": "#ffffff",
        "card_border": "#cbd5e1", "text": "#0f172a", "subtext": "#475569",
        "popup_grad1": "#e0e7ff", "popup_grad2": "#c7d2fe",
    },
}

DEFAULT_CONFIG = {
    "reminders": [
        {"id": 1, "message": "💧 Drink some water!", "type": "interval",
         "interval_min": 30, "datetime": "", "enabled": True,
         "sound_enabled": False, "sound_path": ""},
        {"id": 2, "message": "🧘 Stand up and stretch!", "type": "interval",
         "interval_min": 60, "datetime": "", "enabled": True,
         "sound_enabled": False, "sound_path": ""},
    ],
    "popup_duration": 6,
    "startup": False,
    "volume": 80,
    "preset": "Default (Dark Purple)",
    "next_id": 3,
}

def load_config():
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                data = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in data:
                    data[k] = v
            for r in data.get("reminders", []):
                r.setdefault("sound_enabled", False)
                r.setdefault("sound_path", "")
                r.setdefault("type", "interval")
                r.setdefault("datetime", "")
                r.setdefault("interval_min", 30)
            return data
    except Exception:
        pass
    return dict(DEFAULT_CONFIG)

def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print("Save error:", e)

# ── Theme helpers ──────────────────────────────────────────────────────────────
def get_preset(cfg):
    return PRESETS.get(cfg.get("preset", "Default (Dark Purple)"), PRESETS["Default (Dark Purple)"])

def make_tray_icon(accent="#6C63FF"):
    px = QPixmap(64, 64)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QBrush(QColor(accent)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(4, 4, 56, 56)
    p.setPen(QPen(QColor("white"), 4, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(32, 18, 32, 36)
    p.drawEllipse(27, 42, 10, 10)
    p.end()
    return QIcon(px)

# ── Sound ──────────────────────────────────────────────────────────────────────
class SoundPlayer:
    """Plays audio via pygame mixer — loads fully before playing so no clipping."""
    @staticmethod
    def play(path: str, volume: int):
        if not path or not Path(path).exists():
            return
        if _PYGAME_OK:
            def _play():
                try:
                    _pygame.mixer.music.load(path)
                    _pygame.mixer.music.set_volume(volume / 100.0)
                    _pygame.mixer.music.play()
                except Exception as e:
                    print("pygame play error:", e)
            threading.Thread(target=_play, daemon=True).start()
        else:
            # Fallback: QMediaPlayer (may clip start)
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtCore import QUrl
            player = QMediaPlayer()
            audio  = QAudioOutput()
            player.setAudioOutput(audio)
            audio.setVolume(volume / 100.0)
            player.setSource(QUrl.fromLocalFile(path))
            SoundPlayer._instances.append((player, audio))
            def cleanup():
                pair = (player, audio)
                if pair in SoundPlayer._instances:
                    SoundPlayer._instances.remove(pair)
            player.playbackStateChanged.connect(
                lambda s: cleanup() if s == QMediaPlayer.StoppedState else None
            )
            player.play()
    _instances = []

# ── Popup ──────────────────────────────────────────────────────────────────────
class PopupWindow(QWidget):
    def __init__(self, message: str, duration_sec: int, theme: dict):
        super().__init__()
        self.duration = duration_sec * 1000
        self.theme = theme
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
            Qt.Tool | Qt.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._build_ui(message)
        self._position()
        self._animate_in()
        QTimer.singleShot(self.duration, self._animate_out)

    def _build_ui(self, message):
        t = self.theme
        self.setFixedWidth(360)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        card = QFrame(); card.setObjectName("card")
        card.setStyleSheet(f"""
            #card {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 {t['popup_grad1']}, stop:1 {t['popup_grad2']});
                border-radius:16px; border:1px solid {t['accent']};
            }}
        """)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(20, 16, 20, 16); inner.setSpacing(10)

        hdr = QHBoxLayout()
        icon_lbl = QLabel("🔔"); icon_lbl.setFont(QFont("Segoe UI Emoji", 20))
        title_lbl = QLabel(APP_NAME)
        title_lbl.setStyleSheet(f"color:{t['accent']};font:bold 11px 'Segoe UI';letter-spacing:2px;")
        close_btn = QToolButton(); close_btn.setText("✕"); close_btn.setFixedSize(24,24)
        close_btn.setStyleSheet(f"""
            QToolButton{{color:{t['subtext']};border:none;font-size:14px;border-radius:12px;background:transparent;}}
            QToolButton:hover{{color:{t['text']};background:{t['card_border']};}}
        """)
        close_btn.clicked.connect(self.close)
        hdr.addWidget(icon_lbl); hdr.addWidget(title_lbl); hdr.addStretch(); hdr.addWidget(close_btn)

        msg_lbl = QLabel(message); msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(f"color:{t['text']};font:15px 'Segoe UI';")
        msg_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.progress = QFrame(); self.progress.setFixedHeight(3)
        self.progress.setStyleSheet(f"background:{t['accent']};border-radius:2px;")

        inner.addLayout(hdr); inner.addWidget(msg_lbl); inner.addWidget(self.progress)
        outer.addWidget(card)

        self._prog_timer = QTimer(self); self._prog_timer.setInterval(50)
        self._elapsed = 0
        self._prog_timer.timeout.connect(self._tick); self._prog_timer.start()

    def _tick(self):
        self._elapsed += 50
        ratio = max(0, 1 - self._elapsed / self.duration)
        self.progress.setFixedWidth(int(320 * ratio))

    def _position(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(screen.right() - self.width() - 20, screen.bottom() - self.height() - 20)

    def _animate_in(self):
        self.setWindowOpacity(0); self.show()
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(300); a.setStartValue(0.0); a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic); a.start(); self._ain = a

    def _animate_out(self):
        self._prog_timer.stop()
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(400); a.setStartValue(1.0); a.setEndValue(0.0)
        a.setEasingCurve(QEasingCurve.InCubic)
        a.finished.connect(self.close); a.start(); self._aout = a

# ── Save toast notification ────────────────────────────────────────────────────
class SaveToast(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(8)
        check = QLabel("✓"); check.setStyleSheet("color:#4ade80;font:bold 16px;")
        text  = QLabel("Saved & applied"); text.setStyleSheet("color:#e2e8f0;font:13px 'Segoe UI';")
        layout.addWidget(check); layout.addWidget(text)
        self.setStyleSheet("""
            #toast{background:#1a2e1a;border:1px solid #4ade80;border-radius:10px;}
        """)
        self.adjustSize()
        self.hide()

    def show_toast(self):
        self.adjustSize()
        p = self.parent()
        self.move(p.width()//2 - self.width()//2, p.height() - 80)
        self.show(); self.raise_()
        QTimer.singleShot(2200, self._fade_out)

    def _fade_out(self):
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(400); a.setStartValue(1.0); a.setEndValue(0.0)
        a.finished.connect(self.hide); a.start(); self._a = a

# ── Shared styles ──────────────────────────────────────────────────────────────
def chk_style(accent):
    return f"""
        QCheckBox::indicator{{width:18px;height:18px;border-radius:5px;
            border:2px solid #4f5b8a;background:#141728;}}
        QCheckBox::indicator:checked{{background:{accent};border:2px solid {accent};}}
    """

def spin_style(accent):
    return f"""
        QSpinBox{{background:#141728;color:#e2e8f0;border:1px solid #2d3450;
                 border-radius:8px;padding:5px 8px;font:13px 'Segoe UI';}}
        QSpinBox:focus{{border:1px solid {accent};}}
        QSpinBox::up-button,QSpinBox::down-button{{width:20px;background:#2d3450;border-radius:4px;}}
    """

def input_style(accent):
    return f"""
        QLineEdit{{background:#141728;color:#e2e8f0;border:1px solid #2d3450;
                  border-radius:8px;padding:6px 12px;font:13px 'Segoe UI';}}
        QLineEdit:focus{{border:1px solid {accent};}}
    """

BTN_GHOST_TPL = """
    QToolButton{{background:#2d3450;color:{accent};border-radius:8px;font-size:12px;}}
    QToolButton:hover{{background:{accent};color:white;}}
"""
BTN_RED = """
    QToolButton{background:#2d3450;color:#f87171;border-radius:8px;font-size:14px;}
    QToolButton:hover{background:#7f1d1d;color:white;}
"""

# ── Countdown label (live timer for interval reminders) ───────────────────────
def format_countdown(ms_left: int) -> str:
    if ms_left <= 0:
        return "firing…"
    s = ms_left // 1000
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {sec:02d}s"
    elif m:
        return f"{m}m {sec:02d}s"
    else:
        return f"{sec}s"

# ── Reminder Row ──────────────────────────────────────────────────────────────
class ReminderRow(QFrame):
    changed = Signal()
    deleted = Signal(int)
    preview = Signal(dict)

    def __init__(self, reminder: dict, accent: str):
        super().__init__()
        self.rid    = reminder["id"]
        self.accent = accent
        self._countdown_ms = 0
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._tick_countdown)

        self.setObjectName("row")
        self.setStyleSheet(f"""
            #row{{background:#1e2235;border-radius:12px;border:1px solid #2d3450;}}
            #row:hover{{border:1px solid {accent};}}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        # ── Top row ──────────────────────────────────────────────────────────
        top = QHBoxLayout(); top.setSpacing(10)

        self.toggle = QCheckBox()
        self.toggle.setChecked(reminder.get("enabled", True))
        self.toggle.setStyleSheet(chk_style(accent))
        self.toggle.stateChanged.connect(self.changed)

        self.msg_edit = QLineEdit(reminder.get("message", ""))
        self.msg_edit.setPlaceholderText("Reminder message…")
        self.msg_edit.setStyleSheet(input_style(accent))
        self.msg_edit.textChanged.connect(self.changed)

        prev_btn = QToolButton(); prev_btn.setText("▶")
        prev_btn.setToolTip("Preview now"); prev_btn.setFixedSize(32, 32)
        prev_btn.setStyleSheet(BTN_GHOST_TPL.format(accent=accent))
        prev_btn.clicked.connect(lambda: self.preview.emit(self.get_data()))

        del_btn = QToolButton(); del_btn.setText("🗑"); del_btn.setFixedSize(32, 32)
        del_btn.setStyleSheet(BTN_RED)
        del_btn.clicked.connect(lambda: self.deleted.emit(self.rid))

        top.addWidget(self.toggle)
        top.addWidget(self.msg_edit, stretch=3)
        top.addWidget(prev_btn); top.addWidget(del_btn)

        # ── Type selector row ─────────────────────────────────────────────────
        type_row = QHBoxLayout(); type_row.setSpacing(12)
        type_row.setContentsMargins(28, 0, 0, 0)

        radio_style = f"""
            QRadioButton{{color:#94a3b8;font:12px 'Segoe UI';spacing:6px;}}
            QRadioButton::indicator{{width:16px;height:16px;border-radius:8px;
                border:2px solid #4f5b8a;background:#141728;}}
            QRadioButton::indicator:checked{{background:{accent};border:2px solid {accent};}}
        """
        self.rb_interval = QRadioButton("Interval"); self.rb_interval.setStyleSheet(radio_style)
        self.rb_datetime = QRadioButton("Date & Time"); self.rb_datetime.setStyleSheet(radio_style)
        self._type_grp = QButtonGroup(self)
        self._type_grp.addButton(self.rb_interval, 0)
        self._type_grp.addButton(self.rb_datetime, 1)

        if reminder.get("type", "interval") == "datetime":
            self.rb_datetime.setChecked(True)
        else:
            self.rb_interval.setChecked(True)

        self._type_grp.idToggled.connect(self._on_type_change)

        # Stacked widget: interval controls vs datetime picker
        self.stack = QStackedWidget()
        self.stack.setFixedHeight(38)

        # Page 0 — interval
        interval_page = QWidget()
        ip = QHBoxLayout(interval_page); ip.setContentsMargins(0,0,0,0); ip.setSpacing(8)
        every_lbl = QLabel("every")
        every_lbl.setStyleSheet("color:#64748b;font:12px 'Segoe UI';")
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 1440)
        self.interval_spin.setValue(reminder.get("interval_min", 30))
        self.interval_spin.setSuffix(" min")
        self.interval_spin.setFixedWidth(100)
        self.interval_spin.setStyleSheet(spin_style(accent))
        self.interval_spin.valueChanged.connect(self.changed)

        self.countdown_lbl = QLabel("")
        self.countdown_lbl.setStyleSheet(f"color:{accent};font:bold 12px 'Segoe UI';min-width:80px;")

        ip.addWidget(every_lbl); ip.addWidget(self.interval_spin)
        ip.addSpacing(8); ip.addWidget(self.countdown_lbl); ip.addStretch()

        # Page 1 — datetime
        dt_page = QWidget()
        dp = QHBoxLayout(dt_page); dp.setContentsMargins(0,0,0,0); dp.setSpacing(8)
        at_lbl = QLabel("at")
        at_lbl.setStyleSheet("color:#64748b;font:12px 'Segoe UI';")
        self.dt_edit = QDateTimeEdit()
        self.dt_edit.setDisplayFormat("dd/MM/yyyy  hh:mm")
        self.dt_edit.setCalendarPopup(True)
        self.dt_edit.setStyleSheet(f"""
            QDateTimeEdit{{background:#141728;color:#e2e8f0;border:1px solid #2d3450;
                          border-radius:8px;padding:5px 10px;font:13px 'Segoe UI';}}
            QDateTimeEdit:focus{{border:1px solid {accent};}}
            QDateTimeEdit::drop-down{{width:22px;background:#2d3450;border-radius:4px;}}
        """)
        # Set saved value or default to now+1h
        saved_dt = reminder.get("datetime", "")
        if saved_dt:
            try:
                qdt = QDateTime.fromString(saved_dt, "yyyy-MM-dd HH:mm")
                self.dt_edit.setDateTime(qdt)
            except Exception:
                self.dt_edit.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        else:
            self.dt_edit.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        self.dt_edit.dateTimeChanged.connect(self.changed)
        dp.addWidget(at_lbl); dp.addWidget(self.dt_edit); dp.addStretch()

        self.stack.addWidget(interval_page)  # index 0
        self.stack.addWidget(dt_page)         # index 1
        self.stack.setCurrentIndex(1 if self.rb_datetime.isChecked() else 0)

        type_row.addWidget(self.rb_interval)
        type_row.addWidget(self.rb_datetime)
        type_row.addWidget(self.stack, stretch=1)

        # ── Sound row ─────────────────────────────────────────────────────────
        snd_row = QHBoxLayout(); snd_row.setSpacing(10)
        snd_row.setContentsMargins(28, 0, 0, 0)

        self.snd_chk = QCheckBox("🔊  Play sound")
        self.snd_chk.setChecked(reminder.get("sound_enabled", False))
        self.snd_chk.setStyleSheet(f"QCheckBox{{color:#94a3b8;font:12px 'Segoe UI';spacing:6px;}}" + chk_style(accent))
        self.snd_chk.stateChanged.connect(self._on_sound_toggle)

        self.snd_path = QLineEdit(reminder.get("sound_path", ""))
        self.snd_path.setPlaceholderText("No file — click Browse…")
        self.snd_path.setReadOnly(True)
        self.snd_path.setStyleSheet(input_style(accent) + "QLineEdit{color:#64748b;}")
        self.snd_path.setVisible(self.snd_chk.isChecked())

        browse_btn = QPushButton("Browse…"); browse_btn.setFixedHeight(30)
        browse_btn.setStyleSheet(f"""
            QPushButton{{background:#2d3450;color:{accent};border-radius:8px;
                         padding:0 12px;font:12px 'Segoe UI';border:none;}}
            QPushButton:hover{{background:{accent};color:white;}}
        """)
        browse_btn.clicked.connect(self._browse_sound)
        self._browse_btn = browse_btn
        browse_btn.setVisible(self.snd_chk.isChecked())

        test_btn = QToolButton(); test_btn.setText("▶"); test_btn.setFixedSize(30,30)
        test_btn.setStyleSheet(BTN_GHOST_TPL.format(accent=accent))
        test_btn.clicked.connect(self._test_sound)
        self._test_btn = test_btn
        test_btn.setVisible(self.snd_chk.isChecked())

        clr_btn = QToolButton(); clr_btn.setText("✕"); clr_btn.setFixedSize(30,30)
        clr_btn.setStyleSheet(BTN_RED)
        clr_btn.clicked.connect(self._clear_sound)
        self._clr_btn = clr_btn
        clr_btn.setVisible(self.snd_chk.isChecked())

        snd_row.addWidget(self.snd_chk)
        snd_row.addWidget(self.snd_path, stretch=1)
        snd_row.addWidget(browse_btn); snd_row.addWidget(test_btn); snd_row.addWidget(clr_btn)
        snd_row.addStretch()

        root.addLayout(top)
        root.addLayout(type_row)
        root.addLayout(snd_row)

        self._get_volume = lambda: 80

    # ── type switch ───────────────────────────────────────────────────────────
    def _on_type_change(self, btn_id, checked):
        if checked:
            self.stack.setCurrentIndex(btn_id)
            if btn_id == 0:
                pass  # countdown will be set by MainWindow
            else:
                self.countdown_lbl.setText("")
                self._countdown_timer.stop()
            self.changed.emit()

    # ── countdown (set externally by MainWindow) ──────────────────────────────
    def start_countdown(self, remaining_ms: int):
        self._countdown_ms = remaining_ms
        self.countdown_lbl.setText(format_countdown(self._countdown_ms))
        if not self._countdown_timer.isActive():
            self._countdown_timer.start()

    def _tick_countdown(self):
        self._countdown_ms -= 1000
        if self._countdown_ms < 0:
            self._countdown_ms = 0
        self.countdown_lbl.setText(format_countdown(self._countdown_ms))

    def stop_countdown(self):
        self._countdown_timer.stop()
        self.countdown_lbl.setText("")

    # ── sound helpers ─────────────────────────────────────────────────────────
    def _on_sound_toggle(self):
        v = self.snd_chk.isChecked()
        self.snd_path.setVisible(v); self._browse_btn.setVisible(v)
        self._test_btn.setVisible(v); self._clr_btn.setVisible(v)
        self.changed.emit()

    def _browse_sound(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Select audio file", str(Path.home()),
            "Audio files (*.mp3 *.wav *.ogg *.flac);;All files (*)"
        )
        if p: self.snd_path.setText(p); self.changed.emit()

    def _test_sound(self):
        p = self.snd_path.text()
        if p: SoundPlayer.play(p, self._get_volume())
        else: QMessageBox.information(self, "No sound", "Browse to an audio file first.")

    def _clear_sound(self):
        self.snd_path.setText(""); self.changed.emit()

    def get_data(self) -> dict:
        rtype = "datetime" if self.rb_datetime.isChecked() else "interval"
        dt_str = self.dt_edit.dateTime().toString("yyyy-MM-dd HH:mm") if rtype == "datetime" else ""
        return {
            "id": self.rid,
            "message": self.msg_edit.text(),
            "type": rtype,
            "interval_min": self.interval_spin.value(),
            "datetime": dt_str,
            "enabled": self.toggle.isChecked(),
            "sound_enabled": self.snd_chk.isChecked(),
            "sound_path": self.snd_path.text(),
        }

# ── Main Window ────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config  = load_config()
        self.timers: dict[int, QTimer]  = {}
        self.dt_timers: dict[int, QTimer] = {}  # single-shot datetime timers
        self.timer_start_ms: dict[int, int] = {}  # when interval timer started
        self.popups  = []
        self.rows:   list[ReminderRow] = []
        self._theme  = get_preset(self.config)
        self._setup_window()
        self._setup_tray()
        self._build_ui()
        self._start_all_timers()
        QTimer.singleShot(100, self.hide)

    # ── theme ──────────────────────────────────────────────────────────────────
    def _apply_theme(self):
        t = self._theme
        self.setStyleSheet(f"""
            QMainWindow,QWidget{{background:{t['bg']};color:{t['text']};}}
            QScrollArea{{border:none;background:transparent;}}
            QScrollBar:vertical{{background:{t['card_bg']};width:8px;border-radius:4px;}}
            QScrollBar::handle:vertical{{background:{t['card_border']};border-radius:4px;min-height:30px;}}
            QScrollBar::handle:vertical:hover{{background:{t['accent']};}}
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}
        """)

    # ── window ─────────────────────────────────────────────────────────────────
    def _setup_window(self):
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(820, 560)
        self.resize(920, 680)
        self.setWindowIcon(make_tray_icon(self._theme["accent"]))
        self._apply_theme()

    # ── tray ───────────────────────────────────────────────────────────────────
    def _setup_tray(self):
        t = self._theme
        self.tray = QSystemTrayIcon(make_tray_icon(t["accent"]), self)
        self.tray.setToolTip(APP_NAME + " — Running")
        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu{{background:{t['card_bg']};border:1px solid {t['accent']};
                  border-radius:8px;padding:4px;color:{t['text']};}}
            QMenu::item{{padding:6px 20px;border-radius:6px;}}
            QMenu::item:selected{{background:{t['accent']};}}
        """)
        for label, slot in [
            ("⚙  Open Settings", self._show_window),
            (None, None),
            ("⏸  Pause All",     self._pause_all),
            ("▶  Resume All",    self._resume_all),
            (None, None),
            ("✕  Quit",          QApplication.quit),
        ]:
            if label is None: menu.addSeparator()
            else:
                a = QAction(label, self); a.triggered.connect(slot); menu.addAction(a)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self._show_window() if r == QSystemTrayIcon.DoubleClick else None
        )
        self.tray.show()

    def _show_window(self):
        self.show(); self.raise_(); self.activateWindow()

    # ── UI ─────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        t = self._theme
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # Header
        header = QFrame(); header.setFixedHeight(80)
        header.setStyleSheet(f"""
            background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 {t['popup_grad1']},stop:1 {t['bg']});
            border-bottom:1px solid {t['card_border']};
        """)
        hl = QHBoxLayout(header); hl.setContentsMargins(28,0,28,0)
        logo = QLabel("🔔"); logo.setFont(QFont("Segoe UI Emoji", 28))
        title_l = QLabel(APP_NAME)
        title_l.setStyleSheet(f"color:{t['text']};font:bold 24px 'Segoe UI';letter-spacing:1px;")
        sub = QLabel("  interval & scheduled reminders")
        sub.setStyleSheet(f"color:{t['subtext']};font:13px 'Segoe UI';")
        min_btn = QPushButton("Minimize to Tray"); min_btn.setFixedHeight(34)
        min_btn.setStyleSheet(f"""
            QPushButton{{background:transparent;color:{t['subtext']};
                border:1px solid {t['card_border']};border-radius:8px;
                padding:0 16px;font:12px 'Segoe UI';}}
            QPushButton:hover{{color:{t['accent']};border-color:{t['accent']};}}
        """)
        min_btn.clicked.connect(self.hide)
        hl.addWidget(logo); hl.addWidget(title_l); hl.addWidget(sub)
        hl.addStretch(); hl.addWidget(min_btn)
        root.addWidget(header)

        # Body
        body = QWidget(); bl = QHBoxLayout(body)
        bl.setContentsMargins(24,24,24,24); bl.setSpacing(20)

        # Left: reminders
        left = QVBoxLayout(); left.setSpacing(12)
        rem_hdr = QHBoxLayout()
        rem_title = QLabel("Reminders")
        rem_title.setStyleSheet(f"color:{t['accent']};font:bold 13px 'Segoe UI';letter-spacing:1px;")
        add_btn = QPushButton("+ Add Reminder"); add_btn.setFixedHeight(32)
        add_btn.setStyleSheet(f"""
            QPushButton{{background:{t['accent']};color:white;border-radius:8px;
                         padding:0 16px;font:bold 12px 'Segoe UI';}}
            QPushButton:hover{{opacity:0.85;}}
        """)
        add_btn.clicked.connect(self._add_reminder)
        rem_hdr.addWidget(rem_title); rem_hdr.addStretch(); rem_hdr.addWidget(add_btn)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.rows_container = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setSpacing(8); self.rows_layout.setAlignment(Qt.AlignTop)
        self.rows_layout.setContentsMargins(0,0,8,0)
        scroll.setWidget(self.rows_container)

        left.addLayout(rem_hdr); left.addWidget(scroll, stretch=1)

        # Right: settings
        right = QVBoxLayout(); right.setSpacing(12); right.setAlignment(Qt.AlignTop)
        settings_title = QLabel("Settings")
        settings_title.setStyleSheet(f"color:{t['accent']};font:bold 13px 'Segoe UI';letter-spacing:1px;")

        card = QFrame(); card.setFixedWidth(240)
        card.setStyleSheet(f"QFrame{{background:{t['card_bg']};border-radius:12px;border:1px solid {t['card_border']};}}")
        sc = QVBoxLayout(card); sc.setContentsMargins(16,16,16,16); sc.setSpacing(14)

        def lbl(text):
            l = QLabel(text)
            l.setStyleSheet(f"color:{t['subtext']};font:11px 'Segoe UI';letter-spacing:1px;")
            return l

        # Theme preset
        sc.addWidget(lbl("THEME PRESET"))
        self.preset_combo = QComboBox()
        for name in PRESETS: self.preset_combo.addItem(name)
        self.preset_combo.setCurrentText(self.config.get("preset", "Default (Dark Purple)"))
        self.preset_combo.setStyleSheet(f"""
            QComboBox{{background:#141728;color:{t['text']};border:1px solid {t['card_border']};
                       border-radius:8px;padding:5px 10px;font:13px 'Segoe UI';}}
            QComboBox:focus{{border:1px solid {t['accent']};}}
            QComboBox::drop-down{{width:22px;background:#2d3450;border-radius:4px;}}
            QComboBox QAbstractItemView{{background:#141728;color:{t['text']};
                border:1px solid {t['accent']};selection-background-color:{t['accent']};}}
        """)
        self.preset_combo.currentTextChanged.connect(self._on_preset_change)
        sc.addWidget(self.preset_combo)

        # Popup duration
        sc.addWidget(lbl("POPUP DURATION"))
        self.dur_spin = QSpinBox(); self.dur_spin.setRange(2,30)
        self.dur_spin.setValue(self.config.get("popup_duration", 6))
        self.dur_spin.setSuffix(" sec")
        self.dur_spin.setStyleSheet(spin_style(t['accent']))
        self.dur_spin.valueChanged.connect(self._save)
        sc.addWidget(self.dur_spin)

        # Volume
        sc.addWidget(lbl("SOUND VOLUME"))
        vol_row = QHBoxLayout()
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0,100); self.vol_slider.setValue(self.config.get("volume",80))
        self.vol_slider.setStyleSheet(f"""
            QSlider::groove:horizontal{{height:4px;background:{t['card_border']};border-radius:2px;}}
            QSlider::handle:horizontal{{width:14px;height:14px;margin:-5px 0;
                background:{t['accent']};border-radius:7px;}}
            QSlider::sub-page:horizontal{{background:{t['accent']};border-radius:2px;}}
        """)
        self.vol_slider.valueChanged.connect(self._save)
        self.vol_lbl = QLabel(f"{self.vol_slider.value()}%")
        self.vol_lbl.setStyleSheet(f"color:{t['text']};font:12px 'Segoe UI';min-width:35px;")
        self.vol_slider.valueChanged.connect(lambda v: self.vol_lbl.setText(f"{v}%"))
        vol_row.addWidget(self.vol_slider); vol_row.addWidget(self.vol_lbl)
        sc.addLayout(vol_row)

        # Startup
        self.startup_chk = QCheckBox("Launch at Windows startup")
        self.startup_chk.setChecked(self.config.get("startup", False))
        self.startup_chk.setStyleSheet(
            f"QCheckBox{{color:{t['subtext']};font:12px 'Segoe UI';spacing:8px;}}" + chk_style(t['accent'])
        )
        self.startup_chk.stateChanged.connect(self._toggle_startup)
        sc.addWidget(self.startup_chk)

        sc.addSpacing(4)
        self.status_lbl = QLabel()
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet("color:#4ade80;font:11px 'Segoe UI';")
        self._update_status_label()
        sc.addWidget(self.status_lbl)
        sc.addStretch()

        save_btn = QPushButton("💾  Save & Apply"); save_btn.setFixedHeight(38)
        save_btn.setStyleSheet(f"""
            QPushButton{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 {t['accent']},stop:1 {t['popup_grad2']});color:white;
                border-radius:10px;font:bold 13px 'Segoe UI';}}
            QPushButton:hover{{opacity:0.9;}}
            QPushButton:pressed{{opacity:0.7;}}
        """)
        save_btn.clicked.connect(self._save_and_restart)
        sc.addWidget(save_btn)

        right.addWidget(settings_title); right.addWidget(card)
        bl.addLayout(left, stretch=1); bl.addLayout(right)
        root.addWidget(body, stretch=1)

        # Toast notification (overlay)
        self.toast = SaveToast(central)

        for r in self.config["reminders"]:
            self._add_row(r)

    # ── preset change ──────────────────────────────────────────────────────────
    def _on_preset_change(self, name):
        self.config["preset"] = name
        self._theme = get_preset(self.config)
        save_config(self.config)
        # Rebuild UI with new theme (simplest approach)
        QTimer.singleShot(50, self._rebuild_ui)

    def _rebuild_ui(self):
        self._stop_all_timers()
        self._stop_dt_timers()
        # Save current reminder data before destroying rows
        self.config["reminders"] = self._collect_reminders()
        save_config(self.config)
        # Clear central widget and rebuild
        self._theme = get_preset(self.config)
        self._apply_theme()
        self.rows.clear()
        central = QWidget(); self.setCentralWidget(central)
        self._build_ui()
        self.setWindowIcon(make_tray_icon(self._theme["accent"]))
        self._start_all_timers()

    # ── row management ─────────────────────────────────────────────────────────
    def _add_row(self, reminder: dict):
        row = ReminderRow(reminder, self._theme["accent"])
        row._get_volume = lambda: self.vol_slider.value()
        row.changed.connect(self._save)
        row.deleted.connect(self._delete_reminder)
        row.preview.connect(self._fire_reminder)
        self.rows.append(row)
        self.rows_layout.addWidget(row)

    def _add_reminder(self):
        nid = self.config.get("next_id", 10)
        self.config["next_id"] = nid + 1
        new = {"id": nid, "message": "New reminder", "type": "interval",
               "interval_min": 30, "datetime": "", "enabled": True,
               "sound_enabled": False, "sound_path": ""}
        self.config["reminders"].append(new)
        self._add_row(new)
        self._save_and_restart()

    def _delete_reminder(self, rid: int):
        self.config["reminders"] = [r for r in self.config["reminders"] if r["id"] != rid]
        for row in self.rows:
            if row.rid == rid:
                row.stop_countdown()
                self.rows_layout.removeWidget(row); row.deleteLater(); self.rows.remove(row)
                break
        if rid in self.timers:
            self.timers[rid].stop(); self.timers[rid].deleteLater(); del self.timers[rid]
        if rid in self.dt_timers:
            self.dt_timers[rid].stop(); self.dt_timers[rid].deleteLater(); del self.dt_timers[rid]
        self._save_and_restart()

    def _collect_reminders(self):
        return [row.get_data() for row in self.rows]

    def _save(self):
        self.config["reminders"]      = self._collect_reminders()
        self.config["popup_duration"] = self.dur_spin.value()
        self.config["volume"]         = self.vol_slider.value()
        save_config(self.config)

    def _save_and_restart(self):
        self._save()
        self._stop_all_timers()
        self._stop_dt_timers()
        self._start_all_timers()
        self._update_status_label()
        # Show save toast
        try: self.toast.show_toast()
        except Exception: pass

    def _update_status_label(self):
        n = sum(1 for r in self.config["reminders"] if r.get("enabled"))
        self.status_lbl.setText(f"✓ {n} active reminder{'s' if n!=1 else ''} running")

    # ── timers ─────────────────────────────────────────────────────────────────
    def _start_all_timers(self):
        now = datetime.now()
        for r in self.config["reminders"]:
            if not r.get("enabled"):
                continue
            rid = r["id"]
            if r.get("type") == "datetime":
                dt_str = r.get("datetime", "")
                if not dt_str:
                    continue
                try:
                    target = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                except Exception:
                    continue
                delay_ms = int((target - now).total_seconds() * 1000)
                if delay_ms <= 0:
                    continue  # already passed
                t = QTimer(self); t.setSingleShot(True); t.setInterval(delay_ms)
                t.timeout.connect(lambda rem=r: self._fire_reminder(rem))
                t.start()
                self.dt_timers[rid] = t
            else:
                interval_ms = r["interval_min"] * 60 * 1000
                t = QTimer(self); t.setInterval(interval_ms)
                t.timeout.connect(lambda rem=r: self._fire_and_reset_countdown(rem))
                t.start()
                self.timers[rid] = t
                self.timer_start_ms[rid] = interval_ms
                # attach countdown to row
                for row in self.rows:
                    if row.rid == rid:
                        row.start_countdown(interval_ms)
                        break

    def _fire_and_reset_countdown(self, rem: dict):
        self._fire_reminder(rem)
        # reset countdown
        for row in self.rows:
            if row.rid == rem["id"]:
                row.start_countdown(rem["interval_min"] * 60 * 1000)
                break

    def _stop_all_timers(self):
        for row in self.rows:
            row.stop_countdown()
        for t in self.timers.values():
            t.stop(); t.deleteLater()
        self.timers.clear(); self.timer_start_ms.clear()

    def _stop_dt_timers(self):
        for t in self.dt_timers.values():
            t.stop(); t.deleteLater()
        self.dt_timers.clear()

    def _pause_all(self):
        for t in self.timers.values(): t.stop()
        for t in self.dt_timers.values(): t.stop()
        for row in self.rows: row.stop_countdown()
        self.tray.setToolTip(APP_NAME + " — Paused")

    def _resume_all(self):
        self._stop_all_timers(); self._stop_dt_timers(); self._start_all_timers()
        self.tray.setToolTip(APP_NAME + " — Running")

    # ── fire ───────────────────────────────────────────────────────────────────
    def _fire_reminder(self, reminder: dict):
        msg = reminder.get("message", "").strip()
        if not msg: return
        duration = self.config.get("popup_duration", 6)
        popup = PopupWindow(msg, duration, self._theme)
        self.popups.append(popup)
        popup.destroyed.connect(
            lambda p=popup: self.popups.remove(p) if p in self.popups else None
        )
        if reminder.get("sound_enabled") and reminder.get("sound_path"):
            SoundPlayer.play(reminder["sound_path"], self.config.get("volume", 80))

    # ── startup ────────────────────────────────────────────────────────────────
    def _toggle_startup(self):
        enabled = self.startup_chk.isChecked()
        self.config["startup"] = enabled
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{sys.executable}"')
            else:
                try: winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError: pass
            winreg.CloseKey(key)
        except Exception: pass
        self._save()

    def closeEvent(self, event):
        event.ignore(); self.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            cw = self.centralWidget()
            if cw and hasattr(self, 'toast'):
                self.toast.move(cw.width()//2 - self.toast.width()//2, cw.height() - 80)
        except Exception: pass

# ── Entry ──────────────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "System tray not available.")
        sys.exit(1)

    # Start background update check
    update_thread = start_updater()

    win = MainWindow()

    # After 8 seconds, check if an update was downloaded and prompt restart
    def _check_update_result():
        if _update_state.get("updated"):
            new_v = _update_state.get("new_version", "")
            msg = QMessageBox(win)
            msg.setWindowTitle("Update Downloaded")
            msg.setText(
                f"PopRemind has been updated to v{new_v}.\n\n"
                "Restart now to apply the update?"
            )
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.Later)
            msg.setDefaultButton(QMessageBox.Yes)
            msg.setStyleSheet("""
                QMessageBox{background:#1e2235;color:#e2e8f0;}
                QMessageBox QLabel{color:#e2e8f0;font:13px 'Segoe UI';}
                QPushButton{background:#6C63FF;color:white;border-radius:8px;
                            padding:6px 20px;font:12px 'Segoe UI';}
                QPushButton:hover{background:#7c75ff;}
            """)
            if msg.exec() == QMessageBox.Yes:
                # Relaunch and exit
                subprocess.Popen([sys.executable, str(Path(__file__).resolve())])
                app.quit()

    QTimer.singleShot(8000, _check_update_result)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
