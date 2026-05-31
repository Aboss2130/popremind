"""
PopRemind - Interval Reminder App for Windows 11
Pops up custom reminders at set intervals, with optional MP3 sound per reminder.
"""

import sys
import json
import os
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QSpinBox, QPushButton, QSystemTrayIcon,
    QMenu, QFrame, QScrollArea, QMessageBox, QCheckBox,
    QToolButton, QFileDialog, QSlider
)
from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, Signal, QUrl
)
from PySide6.QtGui import (
    QIcon, QColor, QFont, QPixmap, QPainter, QBrush, QPen, QAction, QGuiApplication
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

# ── Config ────────────────────────────────────────────────────────────────────
APP_NAME = "PopRemind"
CONFIG_PATH = Path(os.getenv("APPDATA", Path.home())) / APP_NAME / "config.json"
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "reminders": [
        {"id": 1, "message": "Time to drink some water!", "interval_min": 30, "enabled": True,
         "sound_enabled": False, "sound_path": ""},
        {"id": 2, "message": "Stand up and stretch!", "interval_min": 60, "enabled": True,
         "sound_enabled": False, "sound_path": ""},
    ],
    "popup_duration": 6,
    "startup": False,
    "volume": 80,
    "next_id": 3
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
                if "sound_enabled" not in r: r["sound_enabled"] = False
                if "sound_path" not in r: r["sound_path"] = ""
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

# ── Tray icon ─────────────────────────────────────────────────────────────────
def make_tray_icon():
    return QIcon("icon.ico")

# ── Sound Player ──────────────────────────────────────────────────────────────
class SoundPlayer:
    """Plays an MP3 file once at the given volume (0-100)."""
    _instances = []  # keep alive until done

    @staticmethod
    def play(path: str, volume: int):
        if not path or not Path(path).exists():
            return
        player = QMediaPlayer()
        audio  = QAudioOutput()
        player.setAudioOutput(audio)
        audio.setVolume(volume / 100.0)
        player.setSource(QUrl.fromLocalFile(path))
        # keep references alive
        SoundPlayer._instances.append((player, audio))
        def cleanup():
            pair = (player, audio)
            if pair in SoundPlayer._instances:
                SoundPlayer._instances.remove(pair)
        player.playbackStateChanged.connect(
            lambda state: cleanup() if state == QMediaPlayer.StoppedState else None
        )
        player.play()

# ── Popup Window ──────────────────────────────────────────────────────────────
class PopupWindow(QWidget):
    def __init__(self, message: str, duration_sec: int = 6):
        super().__init__()
        self.duration = duration_sec * 1000
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
        self.setFixedWidth(360)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet("""
            #card {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #1e1b4b, stop:1 #312e81);
                border-radius: 16px;
                border: 1px solid #6C63FF;
            }
        """)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(20, 16, 20, 16)
        inner.setSpacing(10)

        hdr = QHBoxLayout()
        icon_lbl = QLabel("🔔")
        icon_lbl.setFont(QFont("Segoe UI Emoji", 20))
        title = QLabel(APP_NAME)
        title.setStyleSheet("color:#a5b4fc;font:bold 11px 'Segoe UI';letter-spacing:2px;")
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet("""
            QToolButton{color:#6b7280;border:none;font-size:14px;
                        border-radius:12px;background:transparent;}
            QToolButton:hover{color:white;background:#374151;}
        """)
        close_btn.clicked.connect(self.close)
        hdr.addWidget(icon_lbl)
        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(close_btn)

        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet("color:#f1f5f9;font:15px 'Segoe UI';")
        msg_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.progress = QFrame()
        self.progress.setFixedHeight(3)
        self.progress.setStyleSheet("background:#6C63FF;border-radius:2px;")

        inner.addLayout(hdr)
        inner.addWidget(msg_lbl)
        inner.addWidget(self.progress)
        outer.addWidget(card)

        self._prog_timer = QTimer(self)
        self._prog_timer.setInterval(50)
        self._elapsed = 0
        self._prog_timer.timeout.connect(self._tick)
        self._prog_timer.start()

    def _tick(self):
        self._elapsed += 50
        ratio = max(0, 1 - self._elapsed / self.duration)
        self.progress.setFixedWidth(int(320 * ratio))

    def _position(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(screen.right() - self.width() - 20,
                  screen.bottom() - self.height() - 20)

    def _animate_in(self):
        self.setWindowOpacity(0)
        self.show()
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(300); a.setStartValue(0.0); a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic); a.start()
        self._anim_in = a

    def _animate_out(self):
        self._prog_timer.stop()
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(400); a.setStartValue(1.0); a.setEndValue(0.0)
        a.setEasingCurve(QEasingCurve.InCubic)
        a.finished.connect(self.close); a.start()
        self._anim_out = a

# ── Reminder Row ──────────────────────────────────────────────────────────────
CHK_STYLE = """
    QCheckBox::indicator{width:18px;height:18px;border-radius:5px;
        border:2px solid #4f5b8a;background:#141728;}
    QCheckBox::indicator:checked{background:#6C63FF;border:2px solid #6C63FF;}
"""
SPIN_STYLE = """
    QSpinBox{background:#141728;color:#e2e8f0;border:1px solid #2d3450;
             border-radius:8px;padding:5px 8px;font:13px 'Segoe UI';}
    QSpinBox:focus{border:1px solid #6C63FF;}
    QSpinBox::up-button,QSpinBox::down-button{width:20px;background:#2d3450;border-radius:4px;}
"""
INPUT_STYLE = """
    QLineEdit{background:#141728;color:#e2e8f0;border:1px solid #2d3450;
              border-radius:8px;padding:6px 12px;font:13px 'Segoe UI';}
    QLineEdit:focus{border:1px solid #6C63FF;}
"""
BTN_GHOST = """
    QToolButton{background:#2d3450;color:#a5b4fc;border-radius:8px;font-size:12px;}
    QToolButton:hover{background:#6C63FF;color:white;}
"""
BTN_RED = """
    QToolButton{background:#2d3450;color:#f87171;border-radius:8px;font-size:14px;}
    QToolButton:hover{background:#7f1d1d;color:white;}
"""

class ReminderRow(QFrame):
    changed = Signal()
    deleted = Signal(int)
    preview = Signal(dict)   # emits full reminder dict for preview

    def __init__(self, reminder: dict):
        super().__init__()
        self.rid = reminder["id"]
        self.setObjectName("row")
        self.setStyleSheet("""
            #row{background:#1e2235;border-radius:12px;border:1px solid #2d3450;}
            #row:hover{border:1px solid #6C63FF;}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        # ── Row 1: enable · message · interval · preview · delete ──
        top = QHBoxLayout()
        top.setSpacing(10)

        self.toggle = QCheckBox()
        self.toggle.setChecked(reminder.get("enabled", True))
        self.toggle.setStyleSheet(CHK_STYLE)
        self.toggle.stateChanged.connect(self.changed)

        self.msg_edit = QLineEdit(reminder.get("message", ""))
        self.msg_edit.setPlaceholderText("Reminder message…")
        self.msg_edit.setStyleSheet(INPUT_STYLE)
        self.msg_edit.textChanged.connect(self.changed)

        interval_lbl = QLabel("every")
        interval_lbl.setStyleSheet("color:#64748b;font:12px 'Segoe UI';")

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 1440)
        self.interval_spin.setValue(reminder.get("interval_min", 30))
        self.interval_spin.setSuffix(" min")
        self.interval_spin.setFixedWidth(90)
        self.interval_spin.setStyleSheet(SPIN_STYLE)
        self.interval_spin.valueChanged.connect(self.changed)

        prev_btn = QToolButton()
        prev_btn.setText("▶")
        prev_btn.setToolTip("Preview this reminder now")
        prev_btn.setFixedSize(32, 32)
        prev_btn.setStyleSheet(BTN_GHOST)
        prev_btn.clicked.connect(lambda: self.preview.emit(self.get_data()))

        del_btn = QToolButton()
        del_btn.setText("🗑")
        del_btn.setFixedSize(32, 32)
        del_btn.setStyleSheet(BTN_RED)
        del_btn.clicked.connect(lambda: self.deleted.emit(self.rid))

        top.addWidget(self.toggle)
        top.addWidget(self.msg_edit, stretch=3)
        top.addWidget(interval_lbl)
        top.addWidget(self.interval_spin)
        top.addWidget(prev_btn)
        top.addWidget(del_btn)

        # ── Row 2: sound controls ──
        snd = QHBoxLayout()
        snd.setSpacing(10)
        snd.setContentsMargins(28, 0, 0, 0)   # indent under checkbox

        self.snd_chk = QCheckBox("🔊  Play sound")
        self.snd_chk.setChecked(reminder.get("sound_enabled", False))
        self.snd_chk.setStyleSheet(
            "QCheckBox{color:#94a3b8;font:12px 'Segoe UI';spacing:6px;}" + CHK_STYLE
        )
        self.snd_chk.stateChanged.connect(self._on_sound_toggle)

        self.snd_path = QLineEdit(reminder.get("sound_path", ""))
        self.snd_path.setPlaceholderText("No file selected — click Browse…")
        self.snd_path.setReadOnly(True)
        self.snd_path.setStyleSheet(INPUT_STYLE + "QLineEdit{color:#64748b;}")
        self.snd_path.setVisible(self.snd_chk.isChecked())

        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedHeight(30)
        browse_btn.setStyleSheet("""
            QPushButton{background:#2d3450;color:#a5b4fc;border-radius:8px;
                        padding:0 12px;font:12px 'Segoe UI';border:none;}
            QPushButton:hover{background:#6C63FF;color:white;}
        """)
        browse_btn.clicked.connect(self._browse_sound)
        self._browse_btn = browse_btn
        browse_btn.setVisible(self.snd_chk.isChecked())

        test_snd_btn = QToolButton()
        test_snd_btn.setText("▶")
        test_snd_btn.setToolTip("Test sound")
        test_snd_btn.setFixedSize(30, 30)
        test_snd_btn.setStyleSheet(BTN_GHOST)
        test_snd_btn.clicked.connect(self._test_sound)
        self._test_snd_btn = test_snd_btn
        test_snd_btn.setVisible(self.snd_chk.isChecked())

        clear_snd_btn = QToolButton()
        clear_snd_btn.setText("✕")
        clear_snd_btn.setToolTip("Remove sound")
        clear_snd_btn.setFixedSize(30, 30)
        clear_snd_btn.setStyleSheet(BTN_RED)
        clear_snd_btn.clicked.connect(self._clear_sound)
        self._clear_snd_btn = clear_snd_btn
        clear_snd_btn.setVisible(self.snd_chk.isChecked())

        snd.addWidget(self.snd_chk)
        snd.addWidget(self.snd_path, stretch=1)
        snd.addWidget(browse_btn)
        snd.addWidget(test_snd_btn)
        snd.addWidget(clear_snd_btn)
        snd.addStretch()

        root.addLayout(top)
        root.addLayout(snd)

        # store volume ref (set by MainWindow after construction)
        self._get_volume = lambda: 80

    # ── sound helpers ─────────────────────────────────────────────────────────
    def _on_sound_toggle(self):
        visible = self.snd_chk.isChecked()
        self.snd_path.setVisible(visible)
        self._browse_btn.setVisible(visible)
        self._test_snd_btn.setVisible(visible)
        self._clear_snd_btn.setVisible(visible)
        self.changed.emit()

    def _browse_sound(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select MP3 file", str(Path.home()),
            "Audio files (*.mp3 *.wav *.ogg *.flac);;All files (*)"
        )
        if path:
            self.snd_path.setText(path)
            self.changed.emit()

    def _test_sound(self):
        p = self.snd_path.text()
        if p:
            SoundPlayer.play(p, self._get_volume())
        else:
            QMessageBox.information(self, "No sound", "Browse to an MP3 file first.")

    def _clear_sound(self):
        self.snd_path.setText("")
        self.changed.emit()

    def get_data(self) -> dict:
        return {
            "id": self.rid,
            "message": self.msg_edit.text(),
            "interval_min": self.interval_spin.value(),
            "enabled": self.toggle.isChecked(),
            "sound_enabled": self.snd_chk.isChecked(),
            "sound_path": self.snd_path.text(),
        }

# ── Main Window ───────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config  = load_config()
        self.timers: dict[int, QTimer] = {}
        self.popups  = []
        self.rows:   list[ReminderRow] = []
        self._setup_window()
        self._setup_tray()
        self._build_ui()
        self._start_all_timers()
        QTimer.singleShot(100, self.hide)

    # ── window ────────────────────────────────────────────────────────────────
    def _setup_window(self):
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(780, 540)
        self.resize(860, 640)
        self.setWindowIcon(make_tray_icon())
        self.setStyleSheet("""
            QMainWindow,QWidget{background:#0d1117;color:#e2e8f0;}
            QScrollArea{border:none;background:transparent;}
            QScrollBar:vertical{background:#1e2235;width:8px;border-radius:4px;}
            QScrollBar::handle:vertical{background:#374151;border-radius:4px;min-height:30px;}
            QScrollBar::handle:vertical:hover{background:#6C63FF;}
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}
        """)

    # ── tray ──────────────────────────────────────────────────────────────────
    def _setup_tray(self):
        self.tray = QSystemTrayIcon(make_tray_icon(), self)
        self.tray.setToolTip(APP_NAME + " — Running")
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu{background:#1e2235;border:1px solid #6C63FF;border-radius:8px;
                  padding:4px;color:#e2e8f0;}
            QMenu::item{padding:6px 20px;border-radius:6px;}
            QMenu::item:selected{background:#6C63FF;}
        """)
        for label, slot in [
            ("⚙  Open Settings", self._show_window),
            (None, None),
            ("⏸  Pause All",     self._pause_all),
            ("▶  Resume All",    self._resume_all),
            (None, None),
            ("✕  Quit",          QApplication.quit),
        ]:
            if label is None:
                menu.addSeparator()
            else:
                a = QAction(label, self); a.triggered.connect(slot); menu.addAction(a)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self._show_window() if r == QSystemTrayIcon.DoubleClick else None
        )
        self.tray.show()

    def _show_window(self):
        self.show(); self.raise_(); self.activateWindow()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setFixedHeight(80)
        header.setStyleSheet("""
            background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #1e1b4b,stop:1 #0d1117);
            border-bottom:1px solid #2d3450;
        """)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(28, 0, 28, 0)
        logo = QLabel("🔔"); logo.setFont(QFont("Segoe UI Emoji", 28))
        title = QLabel(APP_NAME)
        title.setStyleSheet("color:white;font:bold 24px 'Segoe UI';letter-spacing:1px;")
        sub = QLabel("  interval reminders, your way")
        sub.setStyleSheet("color:#6b7280;font:13px 'Segoe UI';")
        min_btn = QPushButton("Minimize to Tray")
        min_btn.setFixedHeight(34)
        min_btn.setStyleSheet("""
            QPushButton{background:transparent;color:#6b7280;border:1px solid #2d3450;
                        border-radius:8px;padding:0 16px;font:12px 'Segoe UI';}
            QPushButton:hover{color:#a5b4fc;border-color:#6C63FF;}
        """)
        min_btn.clicked.connect(self.hide)
        hl.addWidget(logo); hl.addWidget(title); hl.addWidget(sub)
        hl.addStretch(); hl.addWidget(min_btn)
        root.addWidget(header)

        # Body
        body = QWidget()
        bl = QHBoxLayout(body)
        bl.setContentsMargins(24, 24, 24, 24)
        bl.setSpacing(20)

        # Left: reminders list
        left = QVBoxLayout(); left.setSpacing(12)
        rem_hdr = QHBoxLayout()
        rem_title = QLabel("Reminders")
        rem_title.setStyleSheet("color:#a5b4fc;font:bold 13px 'Segoe UI';letter-spacing:1px;")
        add_btn = QPushButton("+ Add Reminder")
        add_btn.setFixedHeight(32)
        add_btn.setStyleSheet("""
            QPushButton{background:#6C63FF;color:white;border-radius:8px;
                        padding:0 16px;font:bold 12px 'Segoe UI';}
            QPushButton:hover{background:#7c75ff;}
            QPushButton:pressed{background:#5a52e0;}
        """)
        add_btn.clicked.connect(self._add_reminder)
        rem_hdr.addWidget(rem_title); rem_hdr.addStretch(); rem_hdr.addWidget(add_btn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.rows_container = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setSpacing(8)
        self.rows_layout.setAlignment(Qt.AlignTop)
        self.rows_layout.setContentsMargins(0, 0, 8, 0)
        scroll.setWidget(self.rows_container)

        left.addLayout(rem_hdr); left.addWidget(scroll, stretch=1)

        # Right: settings panel
        right = QVBoxLayout(); right.setSpacing(12); right.setAlignment(Qt.AlignTop)
        settings_title = QLabel("Settings")
        settings_title.setStyleSheet("color:#a5b4fc;font:bold 13px 'Segoe UI';letter-spacing:1px;")

        card = QFrame()
        card.setFixedWidth(230)
        card.setStyleSheet("""
            QFrame{background:#1e2235;border-radius:12px;border:1px solid #2d3450;}
        """)
        sc = QVBoxLayout(card)
        sc.setContentsMargins(16, 16, 16, 16)
        sc.setSpacing(14)

        def lbl(text):
            l = QLabel(text)
            l.setStyleSheet("color:#94a3b8;font:11px 'Segoe UI';letter-spacing:1px;")
            return l

        # Popup duration
        sc.addWidget(lbl("POPUP DURATION"))
        self.dur_spin = QSpinBox()
        self.dur_spin.setRange(2, 30)
        self.dur_spin.setValue(self.config.get("popup_duration", 6))
        self.dur_spin.setSuffix(" sec")
        self.dur_spin.setStyleSheet(SPIN_STYLE)
        self.dur_spin.valueChanged.connect(self._save)
        sc.addWidget(self.dur_spin)

        # Volume
        sc.addWidget(lbl("SOUND VOLUME"))
        vol_row = QHBoxLayout()
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(self.config.get("volume", 80))
        self.vol_slider.setStyleSheet("""
            QSlider::groove:horizontal{height:4px;background:#2d3450;border-radius:2px;}
            QSlider::handle:horizontal{width:14px;height:14px;margin:-5px 0;
                background:#6C63FF;border-radius:7px;}
            QSlider::sub-page:horizontal{background:#6C63FF;border-radius:2px;}
        """)
        self.vol_slider.valueChanged.connect(self._save)
        self.vol_lbl = QLabel(f"{self.vol_slider.value()}%")
        self.vol_lbl.setStyleSheet("color:#e2e8f0;font:12px 'Segoe UI';min-width:35px;")
        self.vol_slider.valueChanged.connect(lambda v: self.vol_lbl.setText(f"{v}%"))
        vol_row.addWidget(self.vol_slider); vol_row.addWidget(self.vol_lbl)
        sc.addLayout(vol_row)

        # Startup toggle
        self.startup_chk = QCheckBox("Launch at Windows startup")
        self.startup_chk.setChecked(self.config.get("startup", False))
        self.startup_chk.setStyleSheet(
            "QCheckBox{color:#94a3b8;font:12px 'Segoe UI';spacing:8px;}" + CHK_STYLE
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
        save_btn = QPushButton("💾  Save & Apply")
        save_btn.setFixedHeight(38)
        save_btn.setStyleSheet("""
            QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #6C63FF,stop:1 #8b5cf6);color:white;
                border-radius:10px;font:bold 13px 'Segoe UI';}
            QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #7c75ff,stop:1 #9b72f6);}
            QPushButton:pressed{background:#5a52e0;}
        """)
        save_btn.clicked.connect(self._save_and_restart)
        sc.addWidget(save_btn)

        right.addWidget(settings_title)
        right.addWidget(card)

        bl.addLayout(left, stretch=1)
        bl.addLayout(right)
        root.addWidget(body, stretch=1)

        for r in self.config["reminders"]:
            self._add_row(r)

    # ── row management ────────────────────────────────────────────────────────
    def _add_row(self, reminder: dict):
        row = ReminderRow(reminder)
        row._get_volume = lambda: self.vol_slider.value()
        row.changed.connect(self._save)
        row.deleted.connect(self._delete_reminder)
        row.preview.connect(self._fire_reminder)
        self.rows.append(row)
        self.rows_layout.addWidget(row)

    def _add_reminder(self):
        nid = self.config.get("next_id", 10)
        self.config["next_id"] = nid + 1
        new = {"id": nid, "message": "New reminder", "interval_min": 30,
               "enabled": True, "sound_enabled": False, "sound_path": ""}
        self.config["reminders"].append(new)
        self._add_row(new)
        self._save_and_restart()

    def _delete_reminder(self, rid: int):
        self.config["reminders"] = [r for r in self.config["reminders"] if r["id"] != rid]
        for row in self.rows:
            if row.rid == rid:
                self.rows_layout.removeWidget(row)
                row.deleteLater()
                self.rows.remove(row)
                break
        self._save_and_restart()

    def _collect_reminders(self):
        return [row.get_data() for row in self.rows]

    def _save(self):
        self.config["reminders"]    = self._collect_reminders()
        self.config["popup_duration"] = self.dur_spin.value()
        self.config["volume"]       = self.vol_slider.value()
        save_config(self.config)

    def _save_and_restart(self):
        self._save()
        self._stop_all_timers()
        self._start_all_timers()
        self._update_status_label()

    def _update_status_label(self):
        n = sum(1 for r in self.config["reminders"] if r.get("enabled"))
        self.status_lbl.setText(f"✓ {n} active reminder{'s' if n != 1 else ''} running")

    # ── timers ────────────────────────────────────────────────────────────────
    def _start_all_timers(self):
        for r in self.config["reminders"]:
            if r.get("enabled"):
                t = QTimer(self)
                t.setInterval(r["interval_min"] * 60 * 1000)
                t.timeout.connect(lambda rem=r: self._fire_reminder(rem))
                t.start()
                self.timers[r["id"]] = t

    def _stop_all_timers(self):
        for t in self.timers.values():
            t.stop(); t.deleteLater()
        self.timers.clear()

    def _pause_all(self):
        for t in self.timers.values(): t.stop()
        self.tray.setToolTip(APP_NAME + " — Paused")

    def _resume_all(self):
        self._stop_all_timers(); self._start_all_timers()
        self.tray.setToolTip(APP_NAME + " — Running")

    # ── fire a reminder (popup + optional sound) ──────────────────────────────
    def _fire_reminder(self, reminder: dict):
        msg = reminder.get("message", "").strip()
        if not msg:
            return
        # popup
        duration = self.config.get("popup_duration", 6)
        popup = PopupWindow(msg, duration)
        self.popups.append(popup)
        popup.destroyed.connect(
            lambda p=popup: self.popups.remove(p) if p in self.popups else None
        )
        # sound
        if reminder.get("sound_enabled") and reminder.get("sound_path"):
            vol = self.config.get("volume", 80)
            SoundPlayer.play(reminder["sound_path"], vol)

    # ── startup ───────────────────────────────────────────────────────────────
    def _toggle_startup(self):
        enabled = self.startup_chk.isChecked()
        self.config["startup"] = enabled
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{sys.executable}"')
            else:
                try: winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError: pass
            winreg.CloseKey(key)
        except Exception:
            pass
        self._save()

    def closeEvent(self, event):
        event.ignore(); self.hide()

# ── Entry ─────────────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "System tray not available.")
        sys.exit(1)
    win = MainWindow()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
