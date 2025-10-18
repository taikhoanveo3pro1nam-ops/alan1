# theme_manager.py - Theme Manager cho các plugin
# Đồng bộ theme với app chính

class PluginThemeManager:
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
                    "success_hover": "#1e7e34",
                    "danger": "#dc3545",
                    "danger_hover": "#c82333",
                    "warning": "#ffc107",
                    "warning_hover": "#e0a800",
                    "info": "#17a2b8",
                    "info_hover": "#138496"
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
                    "success_hover": "#00d19a",
                    "danger": "#e74c3c",
                    "danger_hover": "#c0392b",
                    "warning": "#f39c12",
                    "warning_hover": "#e67e22",
                    "info": "#3498db",
                    "info_hover": "#2980b9"
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
                    "success_hover": "#2ea043",
                    "danger": "#da3633",
                    "danger_hover": "#f85149",
                    "warning": "#d29922",
                    "warning_hover": "#e3b341",
                    "info": "#58a6ff",
                    "info_hover": "#79c0ff"
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
    
    def get_standard_stylesheet(self):
        """Trả về stylesheet chuẩn cho plugin dựa trên theme hiện tại"""
        colors = self.get_current_theme()["colors"]
        
        return f"""
            QWidget {{ 
                background-color: {colors['primary_bg']}; 
                color: {colors['text_primary']}; 
                font-family: 'Segoe UI'; 
                font-size: 14px; 
            }}
            QLabel {{ 
                color: {colors['text_primary']}; 
                font-size: 14px; 
            }}
            QLabel[objectName="titleLabel"] {{ 
                color: {colors['text_primary']}; 
                font-size: 20px; 
                font-weight: bold; 
                margin-bottom: 15px; 
            }} 
            QLabel[objectName="frameTitle"] {{ 
                color: {colors['text_secondary']}; 
                font-weight: bold; 
                margin-bottom: 5px; 
            }}
            QPushButton {{ 
                background-color: {colors['success']}; 
                color: {colors['primary_bg']}; 
                padding: 10px 15px; 
                border-radius: 8px; 
                font-weight: bold; 
                border: none; 
            }}
            QPushButton:hover {{ 
                background-color: {colors['success_hover']}; 
            }}
            QPushButton:disabled {{ 
                background-color: #555555; 
                color: #bbbbbb; 
            }}
            QPushButton#ResetButton {{ 
                background-color: {colors['danger']}; 
                color: white; 
            }}
            QPushButton#ResetButton:hover {{ 
                background-color: {colors['danger_hover']}; 
            }}
            QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QListWidget {{ 
                background-color: {colors['card_bg']}; 
                border: 1px solid {colors['border']}; 
                border-radius: 6px; 
                padding: 8px; 
                color: {colors['text_primary']}; 
                font-size: 13px; 
            }}
            QFrame {{ 
                background-color: {colors['secondary_bg']}; 
                border-radius: 8px; 
                padding: 10px; 
            }}
            QProgressBar {{ 
                background-color: {colors['card_bg']}; 
                color: {colors['text_primary']}; 
                border-radius: 5px; 
                text-align: center; 
            }}
            QProgressBar::chunk {{ 
                background-color: {colors['success']}; 
                border-radius: 5px; 
            }}
            QScrollArea {{ 
                border: none; 
            }}
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ 
                subcontrol-origin: border; 
                width: 20px; 
                border-left: 1px solid {colors['border']}; 
                background-color: {colors['accent']}; 
            }}
            QDoubleSpinBox::up-button {{ 
                subcontrol-position: top right; 
                border-bottom: 1px solid {colors['border']}; 
                border-top-right-radius: 5px; 
            }}
            QDoubleSpinBox::down-button {{ 
                subcontrol-position: bottom right; 
                border-bottom-right-radius: 5px; 
            }}
            QDoubleSpinBox::up-arrow {{ 
                content: '+'; 
                color: white; 
                font-weight: bold; 
            }}
            QDoubleSpinBox::down-arrow {{ 
                content: '-'; 
                color: white; 
                font-weight: bold; 
            }}
            QSlider::groove:horizontal {{ 
                border: none; 
                height: 6px; 
                background: {colors['card_bg']}; 
                margin: 0px 0; 
                border-radius: 3px; 
            }}
            QSlider::handle:horizontal {{ 
                background: {colors['success']}; 
                border: none; 
                width: 14px; 
                margin: -4px 0; 
                border-radius: 7px; 
            }}
            QSlider#VolumeSlider::groove:horizontal {{ 
                height: 4px; 
                background: {colors['card_bg']}; 
                border-radius: 2px; 
            }}
            QSlider#VolumeSlider::handle:horizontal {{ 
                background: {colors['text_primary']}; 
                border: none; 
                width: 10px; 
                margin: -3px 0; 
                border-radius: 5px; 
            }}
            QPushButton#PlayPauseButton {{ 
                background-color: transparent; 
                color: {colors['success']}; 
                border: none; 
                padding: 0px; 
                font-size: 26px; 
                font-weight: bold; 
                text-align: center; 
                min-width: 30px; 
                max-width: 30px; 
            }}
            QPushButton#PlayPauseButton:hover {{ 
                color: {colors['success_hover']}; 
            }}
            QLabel#VolumeIcon {{ 
                font-size: 16px; 
                margin-left: 10px; 
                margin-right: 5px; 
            }}
            QPushButton#AddButton, QPushButton#RemoveButton {{ 
                font-size: 18px; 
                padding: 5px; 
                min-width: 35px; 
                max-width: 35px; 
            }}
            QPushButton#AddButton {{ 
                background-color: {colors['success']}; 
                color: white; 
                border-radius: 4px; 
            }}
            QPushButton#AddButton:hover {{ 
                background-color: {colors['success_hover']}; 
            }}
            QPushButton#RemoveButton {{ 
                background-color: {colors['danger']}; 
                color: white; 
                border-radius: 4px; 
            }}
            QPushButton#RemoveButton:hover {{ 
                background-color: {colors['danger_hover']}; 
            }}
            QFrame#AudioControls {{ 
                background-color: {colors['card_bg']}; 
                border: 1px solid {colors['border']}; 
                border-radius: 5px; 
            }}
            QPushButton#AudioPlayButton {{ 
                background-color: {colors['info']}; 
                color: {colors['primary_bg']}; 
                padding: 5px 10px; 
                border-radius: 4px; 
                font-weight: bold; 
            }}
            QPushButton#AudioPlayButton:hover {{ 
                background-color: {colors['info_hover']}; 
            }}
        """
