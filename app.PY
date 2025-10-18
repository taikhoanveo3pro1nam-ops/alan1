import sys
import os
from pathlib import Path
import importlib.util

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QFrame, QGridLayout, QMessageBox, QScrollArea, QSizePolicy, QSpacerItem,
    QSplashScreen, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QSize, QSettings, QTimer
from PyQt6.QtGui import QFont, QEnterEvent, QPixmap, QPainter, QColor, QShortcut, QKeySequence

# --- CÁC HẰNG SỐ CẤU HÌNH ---
SIDEBAR_WIDTH_EXPANDED = 280
SIDEBAR_WIDTH_COLLAPSED = 50
PLUGINS_DIR = "plugins"  # Tên thư mục chứa các plugin

# --- THEME SYSTEM ---
class ThemeManager:
    def __init__(self):
        self.current_theme = "professional"  # default theme
        self.themes = {
            "light": {
                "name": "Light Theme",
                "colors": {
                    "primary_bg": "#ffffff",
                    "secondary_bg": "#f8f9fa", 
                    "sidebar_bg": "#e9ecef",
                    "card_bg": "#ffffff",
                    "text_primary": "#212529",
                    "text_secondary": "#6c757d",
                    "accent": "#007bff",
                    "accent_hover": "#0056b3",
                    "border": "#dee2e6",
                    "button_bg": "#007bff",
                    "button_hover": "#0056b3",
                    "success": "#28a745",
                    "success_hover": "#1e7e34"
                }
            },
            "dark": {
                "name": "Dark Theme", 
                "colors": {
                    "primary_bg": "#1a1a1a",
                    "secondary_bg": "#2d2d2d",
                    "sidebar_bg": "#0f0f0f", 
                    "card_bg": "#1f1f1f",
                    "text_primary": "#ffffff",
                    "text_secondary": "#aaaaaa",
                    "accent": "#dfbb00",
                    "accent_hover": "#eccf3f",
                    "border": "#2f2f2f",
                    "button_bg": "#dfbb00",
                    "button_hover": "#eccf3f",
                    "success": "#00b894",
                    "success_hover": "#00d19a"
                }
            },
            "professional": {
                "name": "Professional Theme",
                "colors": {
                    "primary_bg": "#0d1117",
                    "secondary_bg": "#161b22",
                    "sidebar_bg": "#161b22",
                    "card_bg": "#21262d", 
                    "text_primary": "#f0f6fc",
                    "text_secondary": "#8b949e",
                    "accent": "#58a6ff",
                    "accent_hover": "#79c0ff",
                    "border": "#30363d",
                    "button_bg": "#238636",
                    "button_hover": "#2ea043",
                    "success": "#238636",
                    "success_hover": "#2ea043"
                }
            }
        }
    
    def get_current_theme(self):
        return self.themes[self.current_theme]
    
    def set_theme(self, theme_name):
        if theme_name in self.themes:
            self.current_theme = theme_name
            return True
        return False
    
    def get_available_themes(self):
        return list(self.themes.keys())

# --- SPLASH SCREEN ---
class SplashScreen(QSplashScreen):
    def __init__(self):
        # Tạo pixmap cho splash screen
        pixmap = QPixmap(500, 300)
        pixmap.fill(QColor("#0d1117"))
        
        # Vẽ logo và text
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Vẽ background gradient
        from PyQt6.QtGui import QLinearGradient
        gradient = QLinearGradient(0, 0, 0, 300)
        gradient.setColorAt(0, QColor("#0d1117"))
        gradient.setColorAt(1, QColor("#161b22"))
        painter.fillRect(pixmap.rect(), gradient)
        
        # Vẽ logo (emoji lớn)
        painter.setFont(QFont("Segoe UI", 48, QFont.Weight.Bold))
        painter.setPen(QColor("#58a6ff"))
        painter.drawText(200, 100, "🎬")
        
        # Vẽ app name
        painter.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        painter.setPen(QColor("#f0f6fc"))
        painter.drawText(150, 150, "VideoCraft Pro")
        
        # Vẽ subtitle
        painter.setFont(QFont("Segoe UI", 12))
        painter.setPen(QColor("#8b949e"))
        painter.drawText(180, 180, "Professional Video Editor")
        
        # Vẽ version
        painter.setFont(QFont("Segoe UI", 10))
        painter.setPen(QColor("#6e7681"))
        painter.drawText(220, 200, "v1.0.0")
        
        # Vẽ loading text
        painter.setFont(QFont("Segoe UI", 10))
        painter.setPen(QColor("#58a6ff"))
        painter.drawText(200, 250, "Loading...")
        
        painter.end()
        
        super().__init__(pixmap)
        self.setWindowFlags(Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
        
        # Tạo progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedSize(300, 6)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #21262d;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #58a6ff;
                border-radius: 3px;
            }
        """)
        
        # Đặt progress bar vào splash screen
        self.progress_bar.move(100, 270)
        self.progress_bar.setParent(self)
        
        # Timer để simulate loading
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)
        self.progress_value = 0
        
    def start_loading(self):
        self.timer.start(50)  # Update every 50ms
        
    def update_progress(self):
        self.progress_value += 2
        self.progress_bar.setValue(self.progress_value)
        
        if self.progress_value >= 100:
            self.timer.stop()
            self.finish_loading()
    
    def finish_loading(self):
        QTimer.singleShot(500, self.close)  # Close after 500ms

# --- CÁC WIDGET TÙY CHỈNH (Giữ nguyên) ---

class SidebarButton(QPushButton):
    hover_signal = pyqtSignal(str)
    def __init__(self, text, description="", theme_manager=None):
        super().__init__(text)
        self.description = description
        self.theme_manager = theme_manager
        self.setCheckable(True)
        self.original_text = text
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_style()
    
    def update_style(self):
        if not self.theme_manager:
            return
        colors = self.theme_manager.get_current_theme()["colors"]
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['secondary_bg']}; 
                color: {colors['text_primary']}; 
                border: 1px solid {colors['border']}; 
                padding: 12px 16px; 
                text-align: left; 
                font-size: 14px; 
                border-radius: 6px;
                font-weight: 500;
            }}
            QPushButton:hover {{ 
                background-color: {colors['card_bg']}; 
                color: {colors['text_primary']}; 
                border-color: {colors['accent']};
            }}
            QPushButton:checked {{ 
                background-color: {colors['accent']}; 
                color: {colors['primary_bg']}; 
                font-weight: bold; 
                border-color: {colors['accent']};
            }}
        """)
    def enterEvent(self, event: QEnterEvent):
        self.hover_signal.emit(self.description)
        super().enterEvent(event)
    def leaveEvent(self, event):
        self.hover_signal.emit("")
        super().leaveEvent(event)

class ToolCard(QFrame):
    def __init__(self, title, subtitle, callback, theme_manager=None):
        super().__init__()
        self.theme_manager = theme_manager
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.update_style()
        
        layout = QVBoxLayout(self); layout.setContentsMargins(15,15,15,15)
        title_lbl = QLabel(title); title_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold)); layout.addWidget(title_lbl)
        if subtitle:
            sub_lbl = QLabel(subtitle); layout.addWidget(sub_lbl)
        layout.addStretch()
        btn = QPushButton("Open Tool"); btn.clicked.connect(callback); layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self.setLayout(layout)
    
    def update_style(self):
        if not self.theme_manager:
            return
        colors = self.theme_manager.get_current_theme()["colors"]
        self.setStyleSheet(f"""
            QFrame {{ 
                background-color: {colors['card_bg']}; 
                border-radius: 12px; 
                border: 1px solid {colors['border']}; 
            }}
            QLabel {{ 
                color: {colors['text_primary']}; 
            }}
            QLabel[objectName="subtitle"] {{
                color: {colors['text_secondary']}; 
                font-size: 12px; 
                line-height: 1.5;
            }}
            QPushButton {{
                background-color: {colors['success']}; 
                color: #ffffff; 
                padding: 10px 16px;
                border-radius: 8px; 
                font-weight: 600; 
                border: none;
                font-size: 14px;
            }}
            QPushButton:hover {{ 
                background-color: {colors['success_hover']}; 
            }}
        """)

class MainPage(QWidget):
    def __init__(self, loaded_plugins, open_tool_callback, theme_manager=None):
        super().__init__()
        self.theme_manager = theme_manager
        layout = QVBoxLayout(); layout.setContentsMargins(20,20,20,20)
        # Header với logo và branding
        header_frame = QFrame()
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Logo placeholder (bạn có thể thay bằng logo thật)
        logo_label = QLabel("🎬")
        logo_label.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
        logo_label.setStyleSheet("color: #58a6ff; margin-right: 15px;")
        header_layout.addWidget(logo_label)
        
        # App title và subtitle
        title_container = QVBoxLayout()
        title_container.setContentsMargins(0, 0, 0, 0)
        
        header = QLabel("VideoCraft Pro")
        header.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        header.setStyleSheet("color: #ffffff; margin: 0; padding: 0;")
        title_container.addWidget(header)
        
        sub = QLabel("Professional Video Editing Suite - Choose a tool from the sidebar")
        sub.setStyleSheet("color: #8b949e; margin: 0; padding: 0; font-size: 14px;")
        title_container.addWidget(sub)
        
        header_layout.addLayout(title_container)
        header_layout.addStretch()
        
        # Version và status info
        info_container = QVBoxLayout()
        info_container.setContentsMargins(0, 0, 0, 0)
        info_container.setSpacing(2)
        
        version_label = QLabel("v1.0.0")
        version_label.setStyleSheet("color: #6e7681; font-size: 12px; padding: 3px 8px; background-color: #21262d; border-radius: 4px;")
        info_container.addWidget(version_label)
        
        status_label = QLabel("Ready")
        status_label.setStyleSheet("color: #2ea043; font-size: 10px; padding: 2px 6px; background-color: #0d1117; border-radius: 3px;")
        info_container.addWidget(status_label)
        
        header_layout.addLayout(info_container)
        
        layout.addWidget(header_frame)
        grid = QGridLayout(); grid.setSpacing(18)
        
        NUM_COLUMNS = 2 
        
        for idx, plugin_class in enumerate(loaded_plugins):
            # *** SỬA ĐỔI: Tự động thêm số thứ tự vào tiêu đề thẻ ***
            title = f"{idx + 1}. {getattr(plugin_class, 'PLUGIN_NAME', f'Plugin {idx+1}')}"
            subtitle = getattr(plugin_class, 'PLUGIN_DESCRIPTION', "Không có mô tả.")
            
            callback = lambda _, plugin_id=id(plugin_class): open_tool_callback(plugin_id) 
            card = ToolCard(title, subtitle, callback, self.theme_manager)
            row, col = divmod(idx, NUM_COLUMNS); 
            grid.addWidget(card, row, col) 
            
        row_count = (len(loaded_plugins) + NUM_COLUMNS - 1) // NUM_COLUMNS
        if len(loaded_plugins) % NUM_COLUMNS != 0:
            grid.setColumnStretch(NUM_COLUMNS - 1, 1)

        grid.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding), row_count, 0)
        
        grid_container = QWidget(); grid_container.setLayout(grid)
        scroll_area = QScrollArea(); scroll_area.setWidgetResizable(True); scroll_area.setWidget(grid_container); scroll_area.setStyleSheet("border: none;"); layout.addWidget(scroll_area)
        self.setLayout(layout)

# --- TRÌNH QUẢN LÝ PLUGIN ---
class PluginManager:
    def __init__(self, plugin_dir):
        self.plugin_dir = Path(plugin_dir)
        self.loaded_plugins = self._find_and_load_plugins()

    def _find_and_load_plugins(self):
        plugins = []
        if not self.plugin_dir.exists() or not self.plugin_dir.is_dir():
            print(f"Cảnh báo: Thư mục plugin '{self.plugin_dir}' không tồn tại.")
            return []

        for file_path in sorted(self.plugin_dir.glob("*.py")):
            if file_path.name.startswith("__"):
                continue

            try:
                spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)

                if hasattr(module, 'PluginWidget'):
                    plugin_class = getattr(module, 'PluginWidget')
                    if hasattr(plugin_class, 'PLUGIN_NAME') and hasattr(plugin_class, 'PLUGIN_DESCRIPTION'):
                        plugins.append(plugin_class)
                    else:
                        print(f"Cảnh báo: Plugin '{file_path.name}' thiếu PLUGIN_NAME hoặc PLUGIN_DESCRIPTION.")
            except Exception as e:
                print(f"Lỗi khi tải plugin '{file_path.name}': {e}")
        
        return plugins

# --- GIAO DIỆN CHÍNH ---
class VideoEditorTool(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VideoCraft Pro - Professional Video Editor")
        self.resize(1200, 800) 
        
        # Initialize theme manager
        self.theme_manager = ThemeManager()
        self.settings = QSettings("VideoCraftPro", "Settings")
        
        # Load saved theme
        saved_theme = self.settings.value("theme", "professional", str)
        self.theme_manager.set_theme(saved_theme)
        
        # Apply initial theme
        self.apply_theme()
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.plugin_manager = PluginManager(PLUGINS_DIR)
        self.loaded_plugins = self.plugin_manager.loaded_plugins
        self.loaded_plugin_widgets = {}

        self._build_sidebar()
        
        self.stack = QStackedWidget()
        self.main_page = MainPage(self.loaded_plugins, self.open_tool_by_id, self.theme_manager)
        self.stack.addWidget(self.main_page)
        
        main_layout.addWidget(self.sidebar_frame)
        main_layout.addWidget(self.stack, stretch=1)

        self.home_button.setChecked(True)
        self.stack.setCurrentWidget(self.main_page)
        
        if not self.loaded_plugins:
            QMessageBox.warning(self, "Không có Công cụ", 
                                f"Không tìm thấy công cụ nào trong thư mục '{PLUGINS_DIR}'.\n"
                                "Vui lòng đảm bảo các file app (plugin) nằm trong thư mục này.")
        
        # Setup keyboard shortcuts
        self.setup_shortcuts()
    
    def setup_shortcuts(self):
        """Setup keyboard shortcuts for the application"""
        # Ctrl+1,2,3... để mở plugin
        for i, plugin_class in enumerate(self.loaded_plugins):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{i+1}"), self)
            shortcut.activated.connect(lambda p_id=id(plugin_class): self.open_tool_by_id(p_id))
        
        # Ctrl+H để về trang chủ
        home_shortcut = QShortcut(QKeySequence("Ctrl+H"), self)
        home_shortcut.activated.connect(self.show_main_page)
        
        # Ctrl+T để toggle sidebar
        toggle_shortcut = QShortcut(QKeySequence("Ctrl+T"), self)
        toggle_shortcut.activated.connect(self.toggle_sidebar)
        
        # Ctrl+1,2,3 để chuyển theme
        light_shortcut = QShortcut(QKeySequence("Ctrl+Shift+1"), self)
        light_shortcut.activated.connect(lambda: self.change_theme("light"))
        
        dark_shortcut = QShortcut(QKeySequence("Ctrl+Shift+2"), self)
        dark_shortcut.activated.connect(lambda: self.change_theme("dark"))
        
        pro_shortcut = QShortcut(QKeySequence("Ctrl+Shift+3"), self)
        pro_shortcut.activated.connect(lambda: self.change_theme("professional"))
        
        # F11 để fullscreen
        fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
        fullscreen_shortcut.activated.connect(self.toggle_fullscreen)
    
    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
    
    def apply_theme(self):
        """Apply current theme to the entire application"""
        colors = self.theme_manager.get_current_theme()["colors"]
        
        # Apply main window style
        self.setStyleSheet(f"""
            QWidget {{ 
                background-color: {colors['primary_bg']}; 
                color: {colors['text_primary']}; 
                font-family: 'Segoe UI', Arial, sans-serif;
            }}
            QMainWindow {{ background-color: {colors['primary_bg']}; }}
        """)
        
        # Apply sidebar style (only if sidebar exists)
        if hasattr(self, 'sidebar_frame'):
            self.sidebar_frame.setStyleSheet(f"""
                QFrame#sidebarFrame {{ 
                    background-color: {colors['sidebar_bg']};
                    border-right: 2px solid {colors['border']};
                }}
            """)
        
        # Apply description frame style (only if description frame exists)
        if hasattr(self, 'description_frame'):
            self.description_frame.setStyleSheet(f"""
                background-color: {colors['card_bg']}; 
                border-radius: 8px; 
                border: 1px solid {colors['border']};
            """)
        
        # Update theme buttons (only if theme buttons exist)
        if hasattr(self, 'theme_buttons'):
            for theme_key, btn in self.theme_buttons.items():
                is_current = theme_key == self.theme_manager.current_theme
                btn.setChecked(is_current)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {colors['accent'] if is_current else colors['secondary_bg']};
                        color: {colors['primary_bg'] if is_current else colors['text_primary']};
                        border: 1px solid {colors['border']};
                        border-radius: 4px;
                        font-weight: bold;
                        font-size: 10px;
                    }}
                    QPushButton:hover {{
                        background-color: {colors['accent_hover'] if is_current else colors['card_bg']};
                    }}
                """)
        
        # Update all existing widgets
        self.update_all_widgets_theme()
    
    def update_all_widgets_theme(self):
        """Update theme for all existing widgets"""
        # Update sidebar buttons (only if they exist)
        if hasattr(self, 'sidebar_buttons'):
            for btn in self.sidebar_buttons:
                if hasattr(btn, 'update_style'):
                    btn.update_style()
        
        # Update main page cards (only if main page exists)
        if hasattr(self, 'main_page') and self.main_page:
            for card in self.main_page.findChildren(ToolCard):
                if hasattr(card, 'update_style'):
                    card.update_style()
    
    def change_theme(self, theme_name):
        """Change theme and save to settings"""
        if self.theme_manager.set_theme(theme_name):
            self.settings.setValue("theme", theme_name)
            self.apply_theme()
            
            # Apply theme to current plugin if it has set_theme method
            current_widget = self.stack.currentWidget()
            if current_widget and hasattr(current_widget, 'set_theme'):
                current_widget.set_theme(theme_name)
            
            return True
        return False

    def _build_sidebar(self):
        self.is_sidebar_collapsed = False
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setObjectName("sidebarFrame")
        self.sidebar_frame.setFixedWidth(SIDEBAR_WIDTH_EXPANDED)
        # Sidebar style will be applied by apply_theme method
        side_layout = QVBoxLayout()
        side_layout.setContentsMargins(5, 5, 5, 5)
        side_layout.setSpacing(5)

        self.home_button = SidebarButton("🏠 Trang Chủ", "Quay về màn hình chính.", self.theme_manager)
        self.home_button.clicked.connect(self.show_main_page)
        home_style_sheet = self.home_button.styleSheet()
        self.home_button.setStyleSheet(home_style_sheet.replace("padding: 12px 16px;", "padding: 10px 5px;"))
        side_layout.addWidget(self.home_button)
        side_layout.addSpacing(10)
        
        title_bar_layout = QHBoxLayout()
        self.title_label = QLabel("TOOLS")
        self.title_label.setStyleSheet("color: #f0f6fc; font-weight: bold; margin-bottom: 5px; padding-left: 5px; font-size: 14px;")
        self.title_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title_bar_layout.addWidget(self.title_label)
        self.toggle_button = QPushButton("«"); self.toggle_button.setFixedSize(20, 20)
        self.toggle_button.setStyleSheet("""
            QPushButton { background-color: #1e1e1e; color: #bfbfbf; border: none; border-radius: 4px; font-weight: bold; font-size: 14px; }
            QPushButton:hover { background-color: #3a3a3a; }
        """)
        self.toggle_button.clicked.connect(self.toggle_sidebar)
        title_bar_layout.addWidget(self.toggle_button)
        side_layout.addLayout(title_bar_layout)
        
        self.sidebar_buttons = []
        self.tool_buttons_container = QWidget()
        tool_buttons_layout = QVBoxLayout(self.tool_buttons_container)
        tool_buttons_layout.setContentsMargins(0, 0, 0, 0)
        tool_buttons_layout.setSpacing(5)

        # *** SỬA ĐỔI: Tự động tạo nút với số thứ tự ***
        for idx, plugin_class in enumerate(self.loaded_plugins):
            name = getattr(plugin_class, 'PLUGIN_NAME', 'Plugin không tên')
            description = getattr(plugin_class, 'PLUGIN_DESCRIPTION', '')
            
            # Tự động tạo tên hiển thị có số thứ tự
            display_name = f"{idx + 1}. {name}"
            
            btn = SidebarButton(display_name, description, self.theme_manager)
            btn.original_text = display_name # Lưu lại tên đầy đủ có số thứ tự
            
            plugin_id = id(plugin_class)
            btn.clicked.connect(lambda _, p_id=plugin_id: self.on_sidebar_clicked(p_id))
            
            tool_style_sheet = btn.styleSheet()
            new_style_sheet = tool_style_sheet.replace("padding: 12px 16px;", "padding: 10px 5px;")
            btn.setStyleSheet(new_style_sheet)
            
            self.sidebar_buttons.append(btn)
            tool_buttons_layout.addWidget(btn)
        
        side_layout.addWidget(self.tool_buttons_container)
        side_layout.addStretch()
        
        # Theme switcher
        theme_frame = QFrame()
        theme_frame.setStyleSheet("background-color: transparent; border: none;")
        theme_layout = QVBoxLayout(theme_frame)
        theme_layout.setContentsMargins(5, 5, 5, 5)
        
        theme_label = QLabel("Theme:")
        theme_label.setStyleSheet("color: #8b949e; font-weight: bold; font-size: 12px; margin-bottom: 5px;")
        theme_layout.addWidget(theme_label)
        
        theme_buttons_layout = QHBoxLayout()
        theme_buttons_layout.setSpacing(3)
        
        # Create theme buttons
        self.theme_buttons = {}
        shortcuts = {"light": "Ctrl+Shift+1", "dark": "Ctrl+Shift+2", "professional": "Ctrl+Shift+3"}
        for theme_key in self.theme_manager.get_available_themes():
            theme_info = self.theme_manager.themes[theme_key]
            btn = QPushButton(theme_info["name"][:3].upper())  # First 3 letters
            btn.setFixedSize(35, 25)
            btn.setCheckable(True)
            btn.setToolTip(f"{theme_info['name']}\nShortcut: {shortcuts.get(theme_key, '')}")
            btn.clicked.connect(lambda checked, t=theme_key: self.change_theme(t))
            self.theme_buttons[theme_key] = btn
            theme_buttons_layout.addWidget(btn)
        
        theme_layout.addLayout(theme_buttons_layout)
        side_layout.addWidget(theme_frame)
        
        self.description_frame = QFrame()
        self.description_frame.setMinimumHeight(80)
        self.description_frame.setStyleSheet("background-color: #1e1e1e; border-radius: 8px; border: 1px solid #2f2f2f;")
        desc_layout = QVBoxLayout(self.description_frame)
        self.description_label = QLabel("Hover over a tool to see description.")
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("color: #8b949e; font-size: 12px; padding: 8px; line-height: 1.4;")
        desc_layout.addWidget(self.description_label)
        side_layout.addWidget(self.description_frame)
        
        self.sidebar_frame.setLayout(side_layout)
        
        self.home_button.hover_signal.connect(self.update_description)
        for btn in self.sidebar_buttons: 
            btn.hover_signal.connect(self.update_description)

    def on_sidebar_clicked(self, plugin_id):
        self.open_tool_by_id(plugin_id)

    def show_main_page(self):
        for btn in self.sidebar_buttons: btn.setChecked(False)
        self.home_button.setChecked(True)
        self.stack.setCurrentWidget(self.main_page)
        self.update_description(self.home_button.description)

    def open_tool_by_id(self, plugin_id):
        self.home_button.setChecked(False)
        target_plugin_class = next((p for p in self.loaded_plugins if id(p) == plugin_id), None)
        if not target_plugin_class:
            QMessageBox.critical(self, "Lỗi", "Không tìm thấy plugin tương ứng.")
            return

        for i, btn in enumerate(self.sidebar_buttons):
            is_active = (id(self.loaded_plugins[i]) == plugin_id)
            btn.setChecked(is_active)
            if is_active:
                self.update_description(btn.description)
        
        if plugin_id in self.loaded_plugin_widgets:
            self.stack.setCurrentWidget(self.loaded_plugin_widgets[plugin_id])
            return

        try:
            widget_instance = target_plugin_class()
            if isinstance(widget_instance, QWidget):
                self.loaded_plugin_widgets[plugin_id] = widget_instance
                self.stack.addWidget(widget_instance)
                self.stack.setCurrentWidget(widget_instance)
            else:
                QMessageBox.critical(self, "Lỗi Plugin", f"Plugin '{target_plugin_class.PLUGIN_NAME}' không phải là một QWidget hợp lệ.")
                self.show_main_page()
        except Exception as e:
            QMessageBox.critical(self, "Lỗi Mở Công Cụ", f"Không thể khởi tạo công cụ '{getattr(target_plugin_class, 'PLUGIN_NAME', 'Không tên')}':\n{e}")
            self.show_main_page()


    def update_description(self, text):
        if not self.is_sidebar_collapsed:
            self.description_label.setText(text or "Di chuột vào một công cụ để xem mô tả.")

    def toggle_sidebar(self):
        self.is_sidebar_collapsed = not self.is_sidebar_collapsed
        target_width = SIDEBAR_WIDTH_COLLAPSED if self.is_sidebar_collapsed else SIDEBAR_WIDTH_EXPANDED
        is_collapsed = self.is_sidebar_collapsed

        self.title_label.setVisible(not is_collapsed)
        self.description_frame.setVisible(not is_collapsed)
        self.home_button.setText("🏠" if is_collapsed else "🏠 Trang Chủ")
        self.home_button.setToolTip("Trang Chủ" if is_collapsed else "Quay về màn hình chính.")
        self.toggle_button.setText("»" if is_collapsed else "«")
        self.toggle_button.setToolTip("Mở rộng" if is_collapsed else "Thu nhỏ")

        # *** SỬA ĐỔI: Cập nhật logic thu gọn để lấy đúng số thứ tự ***
        for idx, btn in enumerate(self.sidebar_buttons):
            current_style = btn.styleSheet()
            if is_collapsed:
                # Lấy số thứ tự từ index của vòng lặp
                index_num = str(idx + 1)
                
                btn.setText(index_num)
                btn.setToolTip(btn.description)
                new_style = current_style.replace("text-align: left;", "text-align: center;").replace("padding: 10px 5px;", "padding: 10px 0px;")
                btn.setStyleSheet(new_style) 
            else:
                btn.setText(btn.original_text) # original_text đã có số thứ tự
                btn.setToolTip("")
                new_style = current_style.replace("text-align: center;", "text-align: left;").replace("padding: 10px 0px;", "padding: 10px 5px;")
                btn.setStyleSheet(new_style)
        
        home_style = self.home_button.styleSheet()
        if is_collapsed:
            home_style_new = home_style.replace("text-align: left;", "text-align: center;").replace("padding: 10px 5px;", "padding: 10px 0px;")
            self.home_button.setStyleSheet(home_style_new)
        else:
            home_style_new = home_style.replace("text-align: center;", "text-align: left;").replace("padding: 10px 0px;", "padding: 10px 5px;")
            self.home_button.setStyleSheet(home_style_new)

        self.animation = QPropertyAnimation(self.sidebar_frame, b"minimumWidth")
        self.animation.setDuration(250)
        self.animation.setStartValue(self.sidebar_frame.width())
        self.animation.setEndValue(target_width)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.finished.connect(lambda: self.sidebar_frame.setFixedWidth(target_width))
        self.animation.start()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Tạo và hiển thị splash screen
    splash = SplashScreen()
    splash.show()
    splash.start_loading()
    
    # Process events để hiển thị splash screen
    app.processEvents()
    
    # Tạo thư mục plugins nếu chưa có
    Path(PLUGINS_DIR).mkdir(exist_ok=True)
    
    # Tạo main window
    window = VideoEditorTool()
    
    # Đợi splash screen hoàn thành rồi mới hiển thị main window
    QTimer.singleShot(3000, lambda: window.show())
    
    sys.exit(app.exec())
