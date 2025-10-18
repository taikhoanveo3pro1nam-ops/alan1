# app4.py - Giao diện v4 được tích hợp làm plugin

import sys
import subprocess
import tempfile
import os
import shutil
import math
import random 
from pathlib import Path

# Thư viện PyQt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox, QLineEdit, QFrame, QProgressBar, QCheckBox, QListWidget, QListWidgetItem,
    QSlider, QSpinBox, QComboBox, QApplication, QSizePolicy, QStackedWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QTime, QSettings
from PyQt6.QtGui import QFont, QCursor, QMouseEvent

# Thư viện Multimedia
try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    CAN_PLAY_VIDEO = True
except ImportError:
    CAN_PLAY_VIDEO = False

# Import theme manager
from theme_manager import PluginThemeManager

# --- LOGIC ĐƯỜNG DẪN FFmpeg (ĐÃ SỬA) ---
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    # Đi lên 1 cấp để ra khỏi thư mục 'plugins'
    BASE_DIR = Path(__file__).resolve().parent.parent

FFMPEG_EXE = BASE_DIR / "ffmpeg.exe"
FFPROBE_EXE = BASE_DIR / "ffprobe.exe" 
# -----------------------------

# --- CƠ CHẾ CUSTOM SLIDER ---
class VolumeSlider(QSlider):
    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            if self.orientation() == Qt.Orientation.Horizontal:
                value = self.minimum() + (self.maximum() - self.minimum()) * event.pos().x() / self.width()
            else:
                value = self.maximum() - (self.maximum() - self.minimum()) * event.pos().y() / self.height()
            self.setValue(int(value))
            
# --- FFmpeg/FFprobe Utilities ---
def get_video_duration(video_path):
    if not FFPROBE_EXE.exists(): return 0
    try:
        cmd = [str(FFPROBE_EXE), "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", os.path.normpath(video_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW, encoding='utf-8')
        return float(result.stdout.strip())
    except Exception: return 0

def format_duration(seconds):
    seconds = int(seconds)
    if seconds < 0: seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

# --- Worker Thread cho FFmpeg ---
class MergeVideoWorker(QThread):
    progress_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(list)
    error_signal = pyqtSignal(str)
    
    def __init__(self, videos, output_dir, output_count, should_mute, is_random, is_cloning_mode, clone_count=1):
        super().__init__()
        self.videos = list(videos)
        self.output_dir = output_dir
        self.output_count = output_count
        self.should_mute = should_mute
        self.is_random = is_random
        self.is_cloning_mode = is_cloning_mode
        self.clone_count = clone_count
        self._is_cancelled = False
        self.ffmpeg_cmd = [str(FFMPEG_EXE)] if FFMPEG_EXE.exists() else ["ffmpeg"]
        self.current_process = None
        self.tmpdir_path = None

    def cancel(self):
        self._is_cancelled = True
        if self.current_process and self.current_process.poll() is None:
            self.current_process.terminate()
            self.current_process.wait()

    def run(self):
        if not self.ffmpeg_cmd:
            self.error_signal.emit("Lỗi: Không tìm thấy FFmpeg (ffmpeg.exe).")
            return
            
        if self._is_cancelled: return
        
        self.tmpdir_path = Path(tempfile.mkdtemp())
        
        try:
            output_paths = []
            
            if self.is_cloning_mode:
                if not self.videos:
                    self.error_signal.emit("Không có video nào được chọn để nhân bản.")
                    return
                    
                video_to_clone = self.videos[0]
                
                self.status_signal.emit(f"Đang nhân bản video {Path(video_to_clone).name} x {self.clone_count} lần...")
                self.progress_signal.emit(5) 
                
                list_path = self.tmpdir_path / "clone_list.txt"
                with open(list_path, "w", encoding="utf-8") as f:
                    for _ in range(self.clone_count):
                        f.write(f"file '{Path(video_to_clone).resolve().as_posix()}'\n")

                output_filename_base = Path(video_to_clone).stem
                output_filename = f"clone_{output_filename_base}_x{self.clone_count}.mp4"
                output_file_path = Path(self.output_dir) / output_filename
                
                counter = 1
                final_output_path = output_file_path
                while final_output_path.exists():
                    output_filename = f"clone_{output_filename_base}_x{self.clone_count}({counter}).mp4"
                    final_output_path = Path(self.output_dir) / output_filename
                    counter += 1
                
                command = self.ffmpeg_cmd + ["-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy"]
                
                if self.should_mute:
                    command.append("-an")
                else:
                    command.extend(["-c:a", "copy"]) 
                    
                command.extend([str(final_output_path), "-y"])

                self.current_process = subprocess.run(
                    command, 
                    capture_output=True, 
                    text=True, 
                    check=True, 
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    encoding='utf-8', 
                    errors='ignore'
                )
                
                if self._is_cancelled:
                    if os.path.exists(final_output_path): os.remove(final_output_path)
                    return
                
                if self.current_process.returncode != 0:
                    error_msg = f"Lỗi FFmpeg khi nhân bản:\n{self.current_process.stderr.strip()}"
                    raise Exception(error_msg)

                output_paths.append(str(final_output_path))
                
            else:
                if self.is_random:
                    random.shuffle(self.videos)

                total_videos = len(self.videos)
                if total_videos == 0:
                    self.finished_signal.emit([])
                    return
                    
                num_videos_per_group = math.ceil(total_videos / self.output_count)
                
                groups = []
                for i in range(0, total_videos, num_videos_per_group):
                    if len(groups) < self.output_count:
                        groups.append(self.videos[i:i + num_videos_per_group])
                    else:
                        break

                total_groups = len(groups)
                
                for i, group in enumerate(groups):
                    if self._is_cancelled: break
                    
                    self.status_signal.emit(f"Đang chuẩn bị nhóm {i+1}/{total_groups}...")
                    self.progress_signal.emit(int((i / total_groups) * 5))
                    
                    ts_paths = []
                    ts_list_path = self.tmpdir_path / f"group_{i+1}_ts_list.txt"

                    for j, video_path_str in enumerate(group):
                        if self._is_cancelled: break
                        
                        ts_path = self.tmpdir_path / f"temp_{i}_{j}.ts"
                        ts_paths.append(str(ts_path))
                        
                        self.status_signal.emit(f"Đang chuyển đổi {Path(video_path_str).name} sang .ts...")
                        
                        ts_command = self.ffmpeg_cmd + [
                            "-i", video_path_str,
                            "-c", "copy",
                            "-bsf:v", "h264_mp4toannexb", 
                            "-f", "mpegts",
                            str(ts_path),
                            "-y"
                        ]
                        
                        self.current_process = subprocess.run(
                            ts_command, 
                            capture_output=True, 
                            text=True, 
                            check=True, 
                            creationflags=subprocess.CREATE_NO_WINDOW,
                            encoding='utf-8', 
                            errors='ignore'
                        )
                        
                        if self.current_process.returncode != 0:
                            error_msg = f"Lỗi FFmpeg khi chuyển đổi sang .ts:\n{self.current_process.stderr.strip()}"
                            raise Exception(error_msg)
                            
                        with open(ts_list_path, "a", encoding="utf-8") as f:
                            f.write(f"file '{Path(ts_path).resolve().as_posix()}'\n") 
                        
                    if self._is_cancelled: break

                    concatenated_ts_path = self.tmpdir_path / f"group_{i+1}_concat.ts"
                    
                    self.status_signal.emit(f"Đang ghép {len(ts_paths)} file .ts...")
                    
                    concat_command = self.ffmpeg_cmd + [
                        "-f", "concat", "-safe", "0", "-i", str(ts_list_path),
                        "-c", "copy",
                        str(concatenated_ts_path),
                        "-y"
                    ]
                    
                    self.current_process = subprocess.run(
                        concat_command, 
                        capture_output=True, 
                        text=True, 
                        check=True, 
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        encoding='utf-8', 
                        errors='ignore'
                    )
                    
                    if self.current_process.returncode != 0:
                        error_msg = f"Lỗi FFmpeg khi ghép các file .ts:\n{self.current_process.stderr.strip()}"
                        raise Exception(error_msg)
                        
                    output_filename_base = Path(self.videos[0]).stem
                    if total_groups == 1:
                        output_filename = f"ghepnhiu_{output_filename_base}.mp4"
                    else:
                        output_filename = f"ghephangloat_{output_filename_base}_nhom_{i+1:03d}.mp4"
                        
                    output_file_path = Path(self.output_dir) / output_filename

                    counter = 1
                    final_output_path = output_file_path
                    while final_output_path.exists():
                        if total_groups == 1:
                            output_filename = f"ghepnhiu_{output_filename_base}({counter}).mp4"
                        else:
                            output_filename = f"ghephangloat_{output_filename_base}_nhom_{i+1:03d}({counter}).mp4"
                        final_output_path = Path(self.output_dir) / output_filename
                        counter += 1
                        
                    self.status_signal.emit(f"Đang chuyển đổi container sang MP4 đầu ra (Nhanh)...")
                    
                    final_command = self.ffmpeg_cmd + [
                        "-i", str(concatenated_ts_path),
                        "-c", "copy", 
                        "-bsf:a", "aac_adtstoasc",
                        "-movflags", "+faststart",
                        "-map", "0:v:0",
                    ]
                    
                    if not self.should_mute:
                        final_command.extend(["-map", "0:a:0"])
                    
                    final_command.extend([str(final_output_path), "-y"])

                    self.current_process = subprocess.run(
                        final_command, 
                        capture_output=True, 
                        text=True, 
                        check=True, 
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        encoding='utf-8', 
                        errors='ignore'
                    )
                    
                    if self.current_process.returncode != 0:
                        error_msg = f"Lỗi FFmpeg khi đóng gói thành MP4:\n{self.current_process.stderr.strip()}"
                        raise Exception(error_msg)

                    output_paths.append(str(final_output_path))
                    
                    self.progress_signal.emit(int(((i + 1) / total_groups) * 100)) 
            
            if self._is_cancelled:
                return

            self.status_signal.emit(f"Hoàn tất. Đã tạo {len(output_paths)} video đầu ra.")
            self.progress_signal.emit(100)
            self.finished_signal.emit(output_paths)

        except Exception as e:
            if not self._is_cancelled:
                self.error_signal.emit(f"Đã xảy ra lỗi: {str(e)}")
        finally:
            self.current_process = None
            if self.tmpdir_path and self.tmpdir_path.exists():
                shutil.rmtree(self.tmpdir_path, ignore_errors=True)

class PluginWidget(QWidget):
    PLUGIN_NAME = "Nối/Nhân Bản Video"
    PLUGIN_DESCRIPTION = "Ghép nhiều video lại với nhau hoặc nhân bản một video thành nhiều lần."

    MODE_MERGE = 'merge'
    MODE_CLONE = 'clone'

    def __init__(self):
        super().__init__()
        self.video_paths = []
        self.worker = None
        self.last_volume = 100 
        self.is_muted = False
        self.mode = self.MODE_MERGE

        self.setStyleSheet("""
            QWidget { 
                background-color: #1e1e1e; 
                color: #d6d6d6; 
                font-family: 'Segoe UI', Arial, sans-serif; 
                font-size: 14px; 
            }
            QLabel { 
                color: #e0e0e0; 
            }
            QLabel[objectName=\"titleLabel\"] { 
                color: #ffffff; 
                font-size: 20px; 
                font-weight: bold; 
                margin-bottom: 15px; 
            }
            QPushButton { 
                background-color: #00b894;
                color: #071717; 
                padding: 10px 15px; 
                border-radius: 8px; 
                font-weight: bold; 
                border: none; 
            }
            QPushButton:hover { 
                background-color: #00d19a; 
            }
            QPushButton:disabled { 
                background-color: #555555; 
                color: #bbbbbb; 
            }
            QPushButton#CancelButton, QPushButton#RemoveAllButton { 
                background-color: #dc3545;
                color: white; 
            }
            QPushButton#CancelButton:hover, QPushButton#RemoveAllButton:hover {
                background-color: #c82333;
            }
            QPushButton#BrowseButton, QPushButton#StartButton {
                background-color: #28a745;
                color: white; 
                font-size: 16px;
            }
            QPushButton#BrowseButton:hover, QPushButton#StartButton:hover {
                background-color: #218838;
            }
            QPushButton#ModeButton {
                background-color: #2a2a2a;
                color: #bfbfbf; 
                padding: 10px 15px; 
                border-radius: 8px; 
                font-weight: bold; 
                border: 1px solid #3a3a3a;
            }
            QPushButton#ModeButton:checked {
                background-color: #dfbb00;
                color: #071717; 
                border: 1px solid #dfbb00;
            }
            QPushButton#ModeButton:hover {
                background-color: #1e1e1e;
            }
            QPushButton#ModeButton:checked:hover {
                background-color: #eccf3f;
            }
            QListWidget { 
                background-color: #3a3a3a; 
                border: 1px solid #4a4a4a; 
                border-radius: 6px; 
                padding: 8px; 
            }
            QLineEdit { 
                background-color: #3a3a3a; 
                border: 1px solid #4a4a4a; 
                border-radius: 6px; 
                padding: 8px;
            }
            QSpinBox { 
                background-color: #3a3a3a; 
                border: 1px solid #4a4a4a; 
                border-radius: 6px; 
                padding: 5px;
            }
            QFrame { 
                background-color: #2a2a2a; 
                border-radius: 8px; 
                padding: 10px; 
                border: none; 
            }
            QFrame#SettingsArea QWidget, 
            QFrame#SettingsArea QSpinBox,
            QFrame#SettingsArea QCheckBox,
            QFrame#SettingsArea QLineEdit {
                background-color: transparent; 
                border: none;
                padding: 0px; 
            }
            QFrame#SettingsArea QLabel {
                padding: 0px; 
            }
            QFrame#SettingsArea QSpinBox {
                background-color: #3a3a3a; 
                border: 1px solid #4a4a4a; 
                border-radius: 6px; 
                padding: 5px;
            }
            QFrame#SettingsArea QSpinBox::up-button, QFrame#SettingsArea QSpinBox::down-button {
                subcontrol-origin: border;
                width: 20px;
                border-left: 1px solid #4a4a4a;
                background-color: #3a3a3a;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
                padding: 0px;
            }
            QFrame#SettingsArea QSpinBox::up-arrow { content: '▲'; color: white; font-weight: bold; }
            QFrame#SettingsArea QSpinBox::down-arrow { content: '▼'; color: white; font-weight: bold; }
            QFrame#SettingsArea QCheckBox::indicator {
                width: 18px; 
                height: 18px;
                border: 1px solid #00b894;
                border-radius: 4px;
                background-color: #1e1e1e;
            }
            QFrame#SettingsArea QCheckBox::indicator:checked {
                background-color: #00b894;
                image: url(data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAcAAAAHCAYAAACzXTVzAAAABmJLR0QA/wD/AP/AdttERwAAAD9JREFUGFdjYICAA///IygB1Q8Ghn8cGBh4v/XzB+F/hgsGBoZf+74/kP+PZkMwGA4zADdGgATDfwYI/39iAACb4Sj3k1QkegAAAABJRU5ErkJggg==);
            }
            QProgressBar { 
                background-color: #3a3a3a; color: #ffffff; border-radius: 5px; text-align: center; 
                min-height: 20px; padding: 3px; 
            }
            QProgressBar::chunk { background-color: #00b894; border-radius: 5px; }
            QSlider::groove:horizontal { border: none; height: 6px; background: #3a3a3a; margin: 0px 0; border-radius: 3px; }
            QSlider::handle:horizontal { background: #00b894; border: none; width: 14px; margin: -4px 0; border-radius: 7px; }
            QSlider#VolumeSlider::groove:horizontal { height: 4px; background: #3a3a3a; border-radius: 2px; }
            QSlider#VolumeSlider::handle:horizontal { background: #d6d6d6; border: none; width: 10px; margin: -3px 0; border-radius: 5px; }
            QPushButton#PlayPauseButton { 
                background-color: transparent; 
                color: #00b894; 
                border: none; 
                padding: 0px; 
                font-size: 26px; 
                font-weight: bold;
                text-align: center; 
                min-width: 30px;
                max-width: 30px;
            }
            QPushButton#PlayPauseButton:hover { 
                color: #00d19a; 
            }
        """)
        
        main_layout_container = QVBoxLayout(self)
        main_layout_container.setContentsMargins(0, 0, 0, 0)
        
        content_widget = QWidget()
        main_layout_container.addWidget(content_widget)
        
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        header_layout = QHBoxLayout()
        title_label = QLabel("Nối/Nhân bản nhiều file MP4")
        title_label.setObjectName("titleLabel")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        self.btn_mode_merge = QPushButton("Ghép Nhóm")
        self.btn_mode_merge.setObjectName("ModeButton")
        self.btn_mode_merge.setCheckable(True)
        self.btn_mode_merge.setChecked(True)
        self.btn_mode_merge.clicked.connect(lambda: self.set_mode(self.MODE_MERGE))
        header_layout.addWidget(self.btn_mode_merge) 
        
        self.btn_mode_clone = QPushButton("Nhân bản Video")
        self.btn_mode_clone.setObjectName("ModeButton")
        self.btn_mode_clone.setCheckable(True)
        self.btn_mode_clone.setChecked(False)
        self.btn_mode_clone.clicked.connect(lambda: self.set_mode(self.MODE_CLONE))
        header_layout.addWidget(self.btn_mode_clone) 
        
        layout.addLayout(header_layout)

        grid_layout = QGridLayout()
        grid_layout.setSpacing(20) 
        grid_layout.setColumnStretch(0, 1)
        grid_layout.setColumnStretch(1, 1)
        grid_layout.setRowStretch(0, 1)
        grid_layout.setRowStretch(1, 1)
        
        self.video_frame = self._create_video_player_widget()
        self.video_frame.setObjectName("VideoArea")
        self.video_frame.setMinimumHeight(250)
        grid_layout.addWidget(self.video_frame, 0, 0)
        
        self.list_controls_container = self._create_list_controls_widget()
        self.list_controls_container.setObjectName("ListArea")
        grid_layout.addWidget(self.list_controls_container, 0, 1)

        self.settings_frame = self._create_settings_widget()
        self.settings_frame.setObjectName("SettingsArea")
        grid_layout.addWidget(self.settings_frame, 1, 0)

        self.action_status_frame = self._create_action_status_widget()
        self.action_status_frame.setObjectName("ActionArea")
        grid_layout.addWidget(self.action_status_frame, 1, 1)

        layout.addLayout(grid_layout)
        layout.addStretch() 

        self.check_initial_setup()
        self._update_group_controls()
        
    def _create_video_player_widget(self):
        video_frame = QFrame()
        video_layout = QVBoxLayout(video_frame)
        video_layout.setContentsMargins(10, 10, 10, 10) 
        video_layout.setSpacing(5) 
        
        if CAN_PLAY_VIDEO:
            self.media_player = QMediaPlayer()
            self.audio_output = QAudioOutput()
            self.media_player.setAudioOutput(self.audio_output)
            
            self.video_widget = QVideoWidget()
            self.video_widget.setStyleSheet("background-color: black; border-radius: 5px;")
            self.media_player.setVideoOutput(self.video_widget)
            video_layout.addWidget(self.video_widget, 1) 
            
            self.control_panel = QFrame()
            self.control_panel.setStyleSheet("QFrame { background-color: transparent; border: none; padding: 0px; }")
            control_layout = QHBoxLayout(self.control_panel)
            control_layout.setContentsMargins(0, 0, 0, 0)
            control_layout.setSpacing(5)
            
            self.play_button = QPushButton("▶️") 
            self.play_button.setObjectName("PlayPauseButton")
            self.play_button.clicked.connect(self.toggle_play_pause)
            control_layout.addWidget(self.play_button, alignment=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

            self.time_label = QLabel("00:00 / 00:00") 
            self.time_label.setStyleSheet("font-weight: bold; margin-left: 5px;")
            control_layout.addWidget(self.time_label)

            self.position_slider = QSlider(Qt.Orientation.Horizontal)
            self.position_slider.setRange(0, 0)
            self.position_slider.sliderMoved.connect(self.set_position)
            control_layout.addWidget(self.position_slider, 1) 

            self.volume_icon = QLabel("🔊")
            self.volume_icon.setStyleSheet("font-size: 16px; margin-left: 10px; margin-right: 5px;")
            self.volume_icon.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.volume_icon.mousePressEvent = self.toggle_mute 
            control_layout.addWidget(self.volume_icon)
            
            self.volume_slider = VolumeSlider(Qt.Orientation.Horizontal)
            self.volume_slider.setObjectName("VolumeSlider")
            self.volume_slider.setRange(0, 100)
            self.volume_slider.setValue(100)
            self.volume_slider.setFixedWidth(80)
            self.volume_slider.valueChanged.connect(self.set_volume)
            control_layout.addWidget(self.volume_slider)
            
            video_layout.addWidget(self.control_panel) 
            self.control_panel.setVisible(False) 
            
            self.audio_output.setVolume(1.0)
            
            self.media_player.positionChanged.connect(self.position_changed)
            self.media_player.durationChanged.connect(self.duration_changed)
            self.media_player.playbackStateChanged.connect(self.state_changed)
            
        else:
            self.video_widget = QLabel("⚠️ Cần cài đặt QtMultimedia để xem trước.")
            self.video_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            video_layout.addWidget(self.video_widget)
            self.media_player = None
            self.audio_output = None
            
        return video_frame

    def _create_list_controls_widget(self):
        list_controls_container = QFrame()
        list_controls_container.setStyleSheet("QFrame { background-color: #2a2a2a; border-radius: 8px; padding: 10px; border: none; }")
        
        list_controls_layout = QVBoxLayout(list_controls_container)
        list_controls_layout.setContentsMargins(10, 10, 10, 10)
        list_controls_layout.setSpacing(10) 

        list_title = QLabel("Video đầu vào (Chọn MP4):")
        list_title.setStyleSheet("color: #bfbfbf; font-weight: bold; margin-bottom: 5px;")
        list_controls_layout.addWidget(list_title)
        
        list_and_buttons_layout = QHBoxLayout()
        list_and_buttons_layout.setSpacing(5) 

        self.video_list_widget = QListWidget()
        self.video_list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.video_list_widget.setMinimumHeight(150)
        self.video_list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.video_list_widget.model().rowsMoved.connect(self._reorder_video_paths)
        self.video_list_widget.itemSelectionChanged.connect(self._on_list_selection_changed) 
        self.video_list_widget.setStyleSheet("QListWidget { background-color: #3a3a3a; border: 1px solid #4a4a4a; border-radius: 6px; padding: 4px; }")
        
        list_and_buttons_layout.addWidget(self.video_list_widget, 1)

        sort_buttons_container = QWidget() 
        sort_buttons_container.setStyleSheet("QWidget { background-color: transparent; }")
        sort_buttons_layout = QVBoxLayout(sort_buttons_container)
        sort_buttons_layout.setContentsMargins(0, 0, 0, 0)
        sort_buttons_layout.setSpacing(5) 
        
        sort_buttons_layout.addStretch() 

        self.btn_add_image = QPushButton("➕")
        self.btn_add_image.setFixedSize(30, 30)
        self.btn_add_image.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.btn_add_image.setStyleSheet("QPushButton { background-color: #28a745; color: white; border-radius: 4px; padding: 0px; } QPushButton:hover { background-color: #218838; }")
        self.btn_add_image.clicked.connect(self.select_files)
        sort_buttons_layout.addWidget(self.btn_add_image, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        
        self.btn_remove_image = QPushButton("➖")
        self.btn_remove_image.setFixedSize(30, 30)
        self.btn_remove_image.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.btn_remove_image.setStyleSheet("QPushButton { background-color: #dc3545; color: white; border-radius: 4px; padding: 0px; } QPushButton:hover { background-color: #c82333; }")
        self.btn_remove_image.clicked.connect(self.remove_selected_files)
        self.btn_remove_image.setEnabled(False) 
        sort_buttons_layout.addWidget(self.btn_remove_image, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        
        self.btn_move_up = QPushButton("\u25b2") 
        self.btn_move_up.setFixedSize(0, 0) 
        self.btn_move_up.setVisible(False)
        self.btn_move_up.clicked.connect(lambda: self._move_item(-1))
        sort_buttons_layout.addWidget(self.btn_move_up)
        
        self.btn_move_down = QPushButton("\u25bc") 
        self.btn_move_down.setFixedSize(0, 0) 
        self.btn_move_down.setVisible(False)
        self.btn_move_down.clicked.connect(lambda: self._move_item(1))
        sort_buttons_layout.addWidget(self.btn_move_down)
        
        sort_buttons_layout.addStretch() 
        list_and_buttons_layout.addWidget(sort_buttons_container) 
        
        list_controls_layout.addLayout(list_and_buttons_layout, 1) 

        self.total_duration_label = QLabel("Tổng thời lượng: 00:00:00")
        self.total_duration_label.setStyleSheet("font-weight: bold; color: #2ecc71; margin-top: 5px;")
        list_controls_layout.addWidget(self.total_duration_label)

        self.btn_clear_files = QPushButton("❌ Xóa tất cả")
        self.btn_clear_files.setObjectName("RemoveAllButton")
        self.btn_clear_files.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold; padding: 10px 15px; border-radius: 8px; border: none;") 
        self.btn_clear_files.clicked.connect(self.clear_files)
        list_controls_layout.addWidget(self.btn_clear_files) 
        
        return list_controls_container

    def _create_settings_widget(self):
        settings_frame = QFrame()
        settings_layout = QVBoxLayout(settings_frame)
        settings_layout.setContentsMargins(10, 10, 10, 10)
        settings_layout.setSpacing(15) 
        
        self.mode_stack = QStackedWidget()
        
        self.merge_mode_widget = QWidget()
        merge_mode_layout = QVBoxLayout(self.merge_mode_widget)
        merge_mode_layout.setContentsMargins(0, 0, 0, 0)
        
        output_count_layout = QHBoxLayout()
        output_count_layout.addWidget(QLabel("Số lượng video ĐẦU RA:"))
        self.spin_output_count = QSpinBox()
        self.spin_output_count.setObjectName("OutputCountSpinBox")
        self.spin_output_count.setRange(1, 1000) 
        self.spin_output_count.setValue(1)
        self.spin_output_count.valueChanged.connect(self._update_output_summary)
        output_count_layout.addWidget(self.spin_output_count)
        output_count_layout.addStretch()
        merge_mode_layout.addLayout(output_count_layout)
        
        self.chk_random = QCheckBox("🔀 Trộn thứ tự video trước khi ghép")
        self.chk_random.stateChanged.connect(self._update_run_button_state)
        merge_mode_layout.addWidget(self.chk_random)
        
        self.summary_label = QLabel("Tóm tắt: Ghép 0 video thành 1 video.")
        self.summary_label.setStyleSheet("color: #ecf0f1; font-weight: bold; margin-top: 10px; border-top: 1px solid #3a3a3a; padding-top: 5px;")
        merge_mode_layout.addWidget(self.summary_label)
        
        self.mode_stack.addWidget(self.merge_mode_widget)
        
        self.clone_mode_widget = QWidget()
        clone_mode_layout = QVBoxLayout(self.clone_mode_widget)
        clone_mode_layout.setContentsMargins(0, 0, 0, 0)
        
        clone_count_layout = QHBoxLayout()
        clone_count_layout.addWidget(QLabel("Số lần Nhân bản (N):"))
        self.spin_clone_count = QSpinBox()
        self.spin_clone_count.setObjectName("CloneCountSpinBox")
        self.spin_clone_count.setRange(1, 10000) 
        self.spin_clone_count.setValue(10)
        self.spin_clone_count.valueChanged.connect(self._update_clone_summary)
        clone_count_layout.addWidget(self.spin_clone_count)
        clone_count_layout.addStretch()
        clone_mode_layout.addLayout(clone_count_layout)
        
        self.clone_summary_label = QLabel("Thời lượng video đầu ra: 00:00:00")
        self.clone_summary_label.setStyleSheet("color: #f1c40f; font-weight: bold; margin-top: 10px; border-top: 1px solid #3a3a3a; padding-top: 5px;")
        clone_mode_layout.addWidget(self.clone_summary_label)
        
        self.clone_warning_label = QLabel("⚠️ Chế độ này chỉ hoạt động với **một video** được chọn.")
        self.clone_warning_label.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 12px;")
        clone_mode_layout.addWidget(self.clone_warning_label)
        
        self.mode_stack.addWidget(self.clone_mode_widget)

        settings_layout.addWidget(self.mode_stack)
        
        settings_layout.addSpacing(15)
        
        self.chk_mute_original = QCheckBox("Tắt tiếng hoàn toàn video đầu ra")
        self.chk_mute_original.setChecked(False)
        self.chk_mute_original.stateChanged.connect(self._update_run_button_state)
        settings_layout.addWidget(self.chk_mute_original)
        
        settings_layout.addStretch()
        return settings_frame

    def _create_action_status_widget(self):
        action_status_frame = QFrame()
        action_status_layout = QVBoxLayout(action_status_frame)
        action_status_layout.setContentsMargins(10, 10, 10, 10)
        
        output_group_box = QFrame()
        output_group_layout = QVBoxLayout(output_group_box)
        output_group_layout.setContentsMargins(0, 0, 0, 0)

        output_group_layout.addWidget(QLabel("Thư mục đầu ra:"))
        output_dir_layout = QHBoxLayout()
        self.output_dir_edit = QLineEdit(str(Path.home() / "Videos"))
        output_dir_layout.addWidget(self.output_dir_edit)
        
        self.btn_select_output_dir = QPushButton("Lưu...")
        self.btn_select_output_dir.setObjectName("BrowseButton")
        self.btn_select_output_dir.clicked.connect(self.select_output_directory)
        
        output_dir_layout.addWidget(self.btn_select_output_dir)
        output_group_layout.addLayout(output_dir_layout)
        
        action_status_layout.addWidget(output_group_box)
        action_status_layout.addStretch(1) 

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Sẵn sàng.") 
        action_status_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Sẵn sàng.")
        
        action_buttons_layout = QHBoxLayout()
        
        self.btn_run = QPushButton("🚀 Bắt Đầu Tạo Video")
        self.btn_run.setObjectName("StartButton")
        self.btn_run.clicked.connect(self.run)
        self.btn_run.setEnabled(False)
        action_buttons_layout.addWidget(self.btn_run)
        
        self.btn_cancel = QPushButton("❌ Reset")
        self.btn_cancel.setObjectName("CancelButton")
        self.btn_cancel.clicked.connect(self.handle_cancel_or_reset)
        action_buttons_layout.addWidget(self.btn_cancel)
        
        action_status_layout.addLayout(action_buttons_layout)
        
        return action_status_frame
    
    def set_mode(self, new_mode):
        if self.worker and self.worker.isRunning(): return 
        if self.mode == new_mode: return

        if new_mode == self.MODE_MERGE:
            self.btn_mode_merge.setChecked(True); self.btn_mode_clone.setChecked(False)
        else:
            self.btn_mode_merge.setChecked(False); self.btn_mode_clone.setChecked(True)
        self.mode = new_mode
        self.reset_ui_state()
        self._update_run_button_state()

    def _update_clone_summary(self):
        if not self.video_paths:
            self.clone_summary_label.setText("Thời lượng video đầu ra: 00:00:00"); self.clone_warning_label.setVisible(False); return

        is_single_video = len(self.video_paths) == 1
        
        if not is_single_video:
            self.clone_warning_label.setText("⚠️ Chế độ này chỉ hoạt động với **một video** được chọn. Vui lòng xóa bớt.")
            self.clone_warning_label.setVisible(True); self.clone_summary_label.setText("Thời lượng video đầu ra: 00:00:00")
            self._update_run_button_state(); return

        self.clone_warning_label.setVisible(False)
        
        original_duration = get_video_duration(self.video_paths[0])
        clone_count = self.spin_clone_count.value()
        
        if original_duration > 0:
            self.clone_summary_label.setText(f"Thời lượng video đầu ra: {format_duration(original_duration * clone_count)}")
        else:
            self.clone_summary_label.setText("Thời lượng video đầu ra: 00:00:00 (Lỗi đọc video)")
        self._update_run_button_state()

    def set_volume(self, value):
        if CAN_PLAY_VIDEO and self.audio_output:
            if value > 0 and self.is_muted: self.is_muted = False
            self.audio_output.setVolume(value / 100.0); self._update_volume_icon(value)
            if not self.is_muted: self.last_volume = value
        
    def toggle_mute(self, event):
        if CAN_PLAY_VIDEO and self.audio_output and isinstance(event, QMouseEvent):
            if self.is_muted:
                target_volume = self.last_volume if self.last_volume > 0 else 50; self.is_muted = False
            else:
                if self.volume_slider.value() > 0: self.last_volume = self.volume_slider.value()
                target_volume = 0; self.is_muted = True
            self.volume_slider.setValue(target_volume); self.audio_output.setVolume(target_volume / 100.0); self._update_volume_icon(target_volume)

    def _update_volume_icon(self, vol):
        if self.is_muted or vol == 0: self.volume_icon.setText("🔇")
        elif vol > 70: self.volume_icon.setText("🔊")
        else: self.volume_icon.setText("🔉")
            
    def toggle_play_pause(self):
        if self.media_player:
            if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState: self.media_player.pause()
            else: self.media_player.play()

    def state_changed(self, state):
        if self.media_player:
            if state == QMediaPlayer.PlaybackState.PlayingState:
                self.play_button.setText("⏸️")
            else:
                self.play_button.setText("▶️")

    def position_changed(self, position):
        if self.media_player and not self.position_slider.isSliderDown():
            self.position_slider.setValue(position)
        self.time_label.setText(f"{QTime(0,0,0).addMSecs(position).toString('mm:ss')} / {QTime(0,0,0).addMSecs(self.media_player.duration()).toString('mm:ss')}")

    def duration_changed(self, duration):
        self.position_slider.setRange(0, duration)
        self.time_label.setText(f"{QTime(0,0,0).addMSecs(self.media_player.position()).toString('mm:ss')} / {QTime(0,0,0).addMSecs(duration).toString('mm:ss')}")
        self.control_panel.setVisible(duration > 0)

    def set_position(self, position):
        if self.media_player: self.media_player.setPosition(position)
            
    def _on_list_selection_changed(self):
        selected_items = self.video_list_widget.selectedItems()
        is_running = self.worker and self.worker.isRunning()
        self.btn_remove_image.setEnabled(bool(selected_items) and not is_running)
        if hasattr(self, 'btn_move_up') and self.mode == self.MODE_MERGE:
            self.btn_move_up.setEnabled(not is_running); self.btn_move_down.setEnabled(not is_running)

        if not selected_items:
            if self.media_player: self.media_player.stop()
            self._update_run_button_state(); return
            
        row = self.video_list_widget.row(selected_items[0])
        
        if self.media_player and 0 <= row < len(self.video_paths):
            selected_path = self.video_paths[row]
            if self.media_player.source() != QUrl.fromLocalFile(selected_path):
                self.media_player.setSource(QUrl.fromLocalFile(selected_path))
            self.media_player.play()
        self._update_run_button_state()

    def check_initial_setup(self):
        if not FFMPEG_EXE.exists() or not FFPROBE_EXE.exists():
            QMessageBox.critical(self, "Lỗi Lớn", f"Không tìm thấy file FFmpeg/FFprobe:\nFFmpeg: {FFMPEG_EXE.exists()}\nFFprobe: {FFPROBE_EXE.exists()}\n\nVui lòng đảm bảo các file này nằm trong cùng thư mục với app.py.")
            self.btn_run.setEnabled(False)
        
        output_dir_path = Path(self.output_dir_edit.text())
        if not output_dir_path.exists():
            try: output_dir_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                QMessageBox.warning(self, "Lỗi", f"Không thể tạo thư mục đầu ra mặc định: {e}"); self.output_dir_edit.setText(str(Path.home()))

    def select_files(self):
        current_dir = os.path.dirname(self.video_paths[0]) if self.video_paths else str(Path.home())
        if self.mode == self.MODE_CLONE:
            file, _ = QFileDialog.getOpenFileName(self, "Chọn một video để nhân bản", current_dir, "Video (*.mp4)")
            if file:
                self.video_paths = [file]; self.video_list_widget.clear()
                self.video_list_widget.addItem(QListWidgetItem(format_duration(get_video_duration(file)) + " " + Path(file).name))
                self.video_list_widget.setCurrentRow(0)
        else:
            files, _ = QFileDialog.getOpenFileNames(self, "Chọn video MP4 để ghép nhóm", current_dir, "Video (*.mp4)")
            if files:
                for file in files:
                    if file not in self.video_paths: self.video_paths.append(file)
        self._update_list_and_duration()
            
        if self.media_player and self.video_paths:
            self.media_player.setSource(QUrl.fromLocalFile(self.video_paths[0])); self.media_player.play()
        if self.audio_output: self.audio_output.setVolume(self.volume_slider.value() / 100.0)

    def remove_selected_files(self):
        selected_rows = [self.video_list_widget.row(item) for item in self.video_list_widget.selectedItems()]
        if not selected_rows:
            QMessageBox.warning(self, "Thông báo", "Vui lòng chọn ít nhất một video để xóa."); return
        if self.media_player: self.media_player.stop()
        selected_rows.sort(reverse=True)
        for row in selected_rows:
            if 0 <= row < len(self.video_paths): del self.video_paths[row]
        self._update_list_and_duration()
        if self.media_player and self.video_paths:
            self.media_player.setSource(QUrl.fromLocalFile(self.video_paths[0])); self.media_player.play()
        elif self.media_player: self.control_panel.setVisible(False)

    def clear_files(self):
        if self.media_player: self.media_player.stop()
        self.video_paths.clear(); self.video_list_widget.clear(); self._update_list_and_duration()
        if self.media_player: self.control_panel.setVisible(False)
            
    def select_output_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu video đầu ra", self.output_dir_edit.text())
        if directory:
            self.output_dir_edit.setText(directory); self._update_run_button_state()
            
    def _update_list_and_duration(self):
        self.video_list_widget.clear(); total_seconds = 0
        for path in self.video_paths:
            duration_sec = get_video_duration(path); total_seconds += duration_sec
            self.video_list_widget.addItem(f"[{format_duration(duration_sec)}] {Path(path).name}")
        self.total_duration_label.setText(f"Tổng thời lượng: {format_duration(total_seconds)}")
        self._update_run_button_state()
        if self.mode == self.MODE_MERGE: self._update_output_summary() 
        else: self._update_clone_summary()

    def _reorder_video_paths(self, source_index, destination_index, *args):
        if self.media_player: self.media_player.stop()
        new_paths = [Path(self.video_list_widget.item(i).text().split('] ')[-1]).name for i in range(self.video_list_widget.count())]
        self.video_paths = [next(p for p in self.video_paths if Path(p).name == name) for name in new_paths]
        self._update_list_and_duration()
        if self.media_player and self.video_paths:
            self.media_player.setSource(QUrl.fromLocalFile(self.video_paths[0])); self.media_player.play()
            
    def _move_item(self, direction):
        current_row = self.video_list_widget.currentRow()
        if current_row < 0: return
        if self.media_player: self.media_player.stop()
        new_row = current_row + direction
        if 0 <= new_row < self.video_list_widget.count():
            item = self.video_paths.pop(current_row); self.video_paths.insert(new_row, item)
            self._update_list_and_duration(); self.video_list_widget.setCurrentRow(new_row)
            if self.media_player: 
                self.media_player.setSource(QUrl.fromLocalFile(self.video_paths[new_row])); self.media_player.play()

    def _update_group_controls(self):
        max_output = max(1, len(self.video_paths))
        self.spin_output_count.setRange(1, max_output)
        self.spin_output_count.setValue(min(self.spin_output_count.value(), max_output))
        self._update_output_summary(); self._update_run_button_state()

    def _update_output_summary(self):
        total_videos = len(self.video_paths)
        if total_videos == 0:
            self.spin_output_count.setRange(1, 1); self.spin_output_count.setValue(1)
            self.summary_label.setText("Tóm tắt: Chưa có video."); self._update_run_button_state(); return
            
        self.spin_output_count.setRange(1, total_videos)
        output_count = self.spin_output_count.value()
        if output_count == 1:
            summary = f"Tóm tắt: Ghép {total_videos} video thành 1 video (1 nhóm {total_videos} video)."
        else:
            if output_count > total_videos:
                output_count = total_videos; self.spin_output_count.setValue(output_count)
            num_videos_per_group = total_videos // output_count; remainder = total_videos % output_count
            if remainder == 0:
                summary = f"Tóm tắt: Ghép {total_videos} video thành {output_count} video (mỗi nhóm {num_videos_per_group} video)."
            else:
                larger_groups, smaller_groups = remainder, output_count - remainder
                smaller_group_size_text = f", {smaller_groups} nhóm {num_videos_per_group} video" if smaller_groups > 0 else ""
                summary = f"Tóm tắt: Ghép {total_videos} video thành {output_count} video ({larger_groups} nhóm {num_videos_per_group + 1} video{smaller_group_size_text})."
        self.summary_label.setText(summary); self._update_run_button_state()
            
    def _update_run_button_state(self):
        is_running = self.worker and self.worker.isRunning()
        is_ready = bool(self.video_paths) and bool(self.output_dir_edit.text()) and (FFMPEG_EXE.exists() and FFPROBE_EXE.exists())
        
        if self.mode == self.MODE_CLONE:
            can_run = is_ready and len(self.video_paths) == 1 and self.spin_clone_count.value() >= 1 and not is_running
        else:
            can_run = is_ready and not is_running
        self.btn_run.setEnabled(can_run)
        
        controls_enabled = not is_running
        self.btn_add_image.setEnabled(controls_enabled)
        self.btn_remove_image.setEnabled(controls_enabled and bool(self.video_list_widget.selectedItems()))
        self.btn_clear_files.setEnabled(controls_enabled); self.btn_select_output_dir.setEnabled(controls_enabled)
        self.video_list_widget.setEnabled(controls_enabled); self.chk_mute_original.setEnabled(controls_enabled)

        if controls_enabled:
            self.btn_mode_merge.setEnabled(self.mode != self.MODE_MERGE)
            self.btn_mode_clone.setEnabled(self.mode != self.MODE_CLONE)
        else:
            self.btn_mode_merge.setEnabled(False); self.btn_mode_clone.setEnabled(False)

        if self.mode == self.MODE_MERGE:
            self.spin_output_count.setEnabled(controls_enabled); self.chk_random.setEnabled(controls_enabled)
            self.spin_clone_count.setEnabled(False)
        else:
            self.spin_clone_count.setEnabled(controls_enabled and len(self.video_paths) == 1)
            self.spin_output_count.setEnabled(False); self.chk_random.setEnabled(False)
        
        if can_run: self.btn_run.setStyleSheet("QPushButton#StartButton { background-color: #28a745; color: white; padding: 10px 15px; border-radius: 8px; font-weight: bold; font-size: 16px; } QPushButton#StartButton:hover { background-color: #218838; }")
        else: self.btn_run.setStyleSheet("background-color: #555555; color: #bbbbbb; font-size: 16px; font-weight: bold;")
        self.btn_cancel.setText("❌ Reset")
        
        if CAN_PLAY_VIDEO and self.media_player and hasattr(self, 'control_panel'):
            is_playing_item_available = bool(self.video_paths) and controls_enabled
            self.control_panel.setEnabled(is_playing_item_available)
            if self.audio_output: self.volume_slider.setEnabled(is_playing_item_available)
            if self.media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.play_button.setEnabled(is_playing_item_available)

    def _check_ffmpeg(self): return FFMPEG_EXE.exists() or shutil.which("ffmpeg")

    def run(self):
        if not self.btn_run.isEnabled(): return
        output_directory = self.output_dir_edit.text()
        if not Path(output_directory).is_dir():
            QMessageBox.warning(self, "Lỗi", "Thư mục đầu ra không hợp lệ."); return
        if self.media_player: self.media_player.stop()
        self._update_run_button_state(); self.setCursor(Qt.CursorShape.WaitCursor)
        self.progress_bar.setValue(0); self.progress_bar.setFormat("Đang khởi tạo..."); QApplication.processEvents()
        
        if self.mode == self.MODE_CLONE:
            videos, clone_count, output_count, is_random = [self.video_paths[0]], self.spin_clone_count.value(), 1, False
        else:
            videos, output_count, clone_count, is_random = self.video_paths, self.spin_output_count.value(), 1, self.chk_random.isChecked()

        self.worker = MergeVideoWorker(videos, Path(output_directory), output_count, self.chk_mute_original.isChecked(), is_random, (self.mode == self.MODE_CLONE), clone_count)
        self.worker.progress_signal.connect(self.update_progress); self.worker.status_signal.connect(self.update_status)
        self.worker.finished_signal.connect(self.handle_finished); self.worker.error_signal.connect(self.handle_error); self.worker.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_status(self, message):
        self.progress_bar.setFormat(f"{self.progress_bar.value()}% - {message.split('...')[0]}")

    def handle_finished(self, output_paths):
        self.setCursor(Qt.CursorShape.ArrowCursor); self.worker = None; self._update_run_button_state()
        self.progress_bar.setFormat("Hoàn thành!")
        output_dir = Path(self.output_dir_edit.text())
        if not output_paths:
            QMessageBox.warning(self, "Thông báo", "Không có video nào được tạo.")
        elif len(output_paths) == 1:
            msg = "Đã nhân bản video xong và lưu tại:" if self.mode == self.MODE_CLONE else "Đã ghép video xong và lưu tại:"
            QMessageBox.information(self, "Hoàn tất", f"{msg}\n{output_paths[0]}")
        else:
            QMessageBox.information(self, "Hoàn tất", f"Đã tạo thành công {len(output_paths)} video đầu ra.\nLưu tại thư mục:\n{output_dir}")
        try: os.startfile(output_dir)
        except: pass

    def handle_error(self, message):
        self.setCursor(Qt.CursorShape.ArrowCursor)
        QMessageBox.critical(self, "Lỗi", f"Đã xảy ra lỗi trong quá trình xử lý video:\n{message}")
        self.worker = None; self._update_run_button_state(); self.progress_bar.setValue(0); self.progress_bar.setFormat("Đã xảy ra lỗi.")
        
    def handle_cancel_or_reset(self):
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(self, "Xác nhận Hủy", "Bạn có chắc chắn muốn hủy tác vụ đang chạy?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                self.worker.cancel(); self.reset_ui_state(); self.progress_bar.setFormat("Tác vụ đã bị hủy.")
        else:
            self.reset_ui_state()

    def reset_ui_state(self):
        if self.media_player: self.media_player.stop()
        self.video_paths.clear(); self.worker = None
        
        if CAN_PLAY_VIDEO and self.audio_output:
            self.is_muted, self.last_volume = False, 100
            self.volume_slider.setValue(100); self.audio_output.setVolume(1.0); self._update_volume_icon(100)
            
        self._update_list_and_duration(); self.video_list_widget.clear() 
        
        self.spin_output_count.setValue(1); self.spin_clone_count.setValue(10); self.chk_mute_original.setChecked(False)
        
        if self.mode == self.MODE_MERGE:
            self.mode_stack.setCurrentWidget(self.merge_mode_widget); self.video_list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
            self.chk_random.setVisible(True); self._update_output_summary()
        else:
            self.mode_stack.setCurrentWidget(self.clone_mode_widget); self.video_list_widget.setDragDropMode(QListWidget.DragDropMode.NoDragDrop)
            self.chk_random.setVisible(False); self._update_clone_summary()
            
        self._update_run_button_state(); self.progress_bar.setValue(0); self.progress_bar.setFormat("Sẵn sàng.")
        self.setCursor(Qt.CursorShape.ArrowCursor)
