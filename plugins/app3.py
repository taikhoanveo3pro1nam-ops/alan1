import sys
import json
import math
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QSpinBox,
    QMessageBox, QLineEdit, QProgressBar, QFrame, QListWidget, QListWidgetItem,
    QScrollArea, QSizePolicy, QCheckBox, QSlider, QStackedLayout, QGridLayout, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings, QSize, QUrl, QTime
from PyQt6.QtGui import QFont, QCursor, QMouseEvent
import subprocess
import os
from pathlib import Path
import tempfile
import re
import shutil

# THÊM MỚI: Import Multimedia (Để xem trước video)
try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaFormat
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    CAN_PLAY_VIDEO = True
except ImportError:
    CAN_PLAY_VIDEO = False

# Import theme manager
from theme_manager import PluginThemeManager
    
# --- CƠ CHẾ CUSTOM SLIDER (ĐỂ HỖ TRỢ CLICK TO JUMP) ---
class VolumeSlider(QSlider):
    """QSlider tùy chỉnh cho phép nhảy đến vị trí khi nhấp chuột."""
    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            if self.orientation() == Qt.Orientation.Horizontal:
                value = self.minimum() + (self.maximum() - self.minimum()) * event.pos().x() / self.width()
            else:
                value = self.maximum() - (self.maximum() - self.minimum()) * event.pos().y() / self.height()
            self.setValue(int(value))
# --- END CUSTOM SLIDER ---


# --- Worker Thread để xử lý hàng loạt (Mode 2: Chèn từng video) ---
class FFmpegBatchWorker(QThread):
    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, videos, audio, output_dir, mute_original, audio_volume_percent):
        super().__init__()
        self.videos = videos
        self.audio = audio
        self.output_dir = output_dir
        self.mute_original = mute_original
        self.audio_volume_percent = audio_volume_percent
        self._is_cancelled = False
        
        # Thiết lập đường dẫn FFmpeg
        if getattr(sys, 'frozen', False):
            BASE_DIR = Path(sys.executable).parent
        else:
            BASE_DIR = Path(__file__).resolve().parent

        self.FFMPEG_EXE = BASE_DIR / "ffmpeg.exe"
        self.FFPROBE_EXE = BASE_DIR / "ffprobe.exe"
        self.ffmpeg_cmd_base = [str(self.FFMPEG_EXE)] if self.FFMPEG_EXE.exists() else ["ffmpeg"]
        self.ffprobe_cmd_base = [str(self.FFPROBE_EXE)] if self.FFPROBE_EXE.exists() else ["ffprobe"]
        self.current_process = None

    def cancel(self):
        self._is_cancelled = True
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=5)
            except:
                pass
        
    def _check_ffmpeg(self):
        return self.FFMPEG_EXE.exists() or shutil.which("ffmpeg")

    def run(self):
        if not self._check_ffmpeg():
             self.error_signal.emit("Lỗi: Không tìm thấy FFmpeg.")
             return
             
        try:
            total_videos = len(self.videos)
            volume_multiplier = self.audio_volume_percent / 100.0

            for i, video_path_str in enumerate(self.videos):
                if self._is_cancelled:
                    self.progress_signal.emit(i * 100 // total_videos, "Đã hủy bởi người dùng.")
                    return

                video_path = Path(video_path_str)
                base_name = video_path.stem
                extension = video_path.suffix
                
                output_path = self.output_dir / f"{base_name}_newaudio{extension}" # Tên file mới để tránh ghi đè
                counter = 1
                while output_path.exists():
                    output_path = self.output_dir / f"{base_name}_newaudio({counter}){extension}"
                    counter += 1

                progress_message = f"Đang xử lý {i+1}/{total_videos}: {video_path.name}"
                
                # Cập nhật progress dựa trên số lượng video đã hoàn thành
                self.progress_signal.emit(i * 100 // total_videos, progress_message)

                command = self.ffmpeg_cmd_base
                
                if self.mute_original:
                    # Chèn nhạc, tắt tiếng gốc (thay thế)
                    command += [
                        "-i", str(video_path), "-i", self.audio,
                        "-c:v", "copy", 
                        "-map", "0:v:0", "-map", "1:a:0", # Chỉ lấy video gốc và audio mới
                        "-filter:a", f"volume={volume_multiplier}",
                        "-c:a", "aac", "-b:a", "192k",
                        "-shortest", str(output_path), "-y"
                    ]
                else:
                    # Chèn nhạc, trộn tiếng gốc và tiếng mới
                    # Sử dụng amix duration=first để thời lượng audio theo video (0:a)
                    filter_complex = (
                        f"[0:a]volume=1.0[a0];" # Audio gốc (volume giữ nguyên 1.0)
                        f"[1:a]volume={volume_multiplier}[a1];" # Audio mới (volume chỉnh)
                        f"[a0][a1]amix=inputs=2:duration=first[aout]" # Trộn, thời lượng theo video đầu tiên
                    )
                    command += [
                        "-i", str(video_path), "-i", self.audio,
                        "-filter_complex", filter_complex,
                        "-map", "0:v:0", "-map", "[aout]", # Lấy video gốc và audio đã trộn
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", str(output_path), "-y"
                    ]
                
                # Chạy subprocess và gán cho self.current_process để có thể hủy
                self.current_process = subprocess.run(
                    command, capture_output=True, text=True, encoding='utf-8',
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                if self.current_process.returncode != 0:
                    raise subprocess.CalledProcessError(self.current_process.returncode, command, stderr=self.current_process.stderr)
            
            if not self._is_cancelled:
                self.progress_signal.emit(100, f"Hoàn tất xử lý {total_videos} video!")
                self.finished_signal.emit(str(self.output_dir))

        except subprocess.CalledProcessError as e:
            if not self._is_cancelled:
                error_msg = f"Lỗi FFmpeg khi xử lý {video_path.name}:\n\n{e.stderr}" if 'video_path' in locals() else f"Lỗi FFmpeg: {e.stderr}"
                self.error_signal.emit(error_msg)
        except Exception as e:
            if not self._is_cancelled:
                self.error_signal.emit(f"Đã xảy ra lỗi: {e}")


# CHỈNH SỬA 1: Đổi tên class thành PluginWidget
class PluginWidget(QWidget):
    # CHỈNH SỬA 2: Thêm thuộc tính PLUGIN_NAME và PLUGIN_DESCRIPTION
    PLUGIN_NAME = "Chèn Nhạc Hàng Loạt"
    PLUGIN_DESCRIPTION = "Chèn một file nhạc nền vào nhiều video khác nhau, tùy chọn trộn hoặc thay thế âm thanh gốc."

    def __init__(self):
        super().__init__()
        # Khởi tạo QSettings
        self.settings = QSettings("VideoEditorTool", "App3Settings")
        self.is_muted = False
        self.last_volume = 100
        self.worker_thread = None # Đổi tên thành self.worker_thread
        
        self.videos = []
        self.audio = None

        self.last_video_dir = self.settings.value("lastVideoDir", str(Path.home()), str)
        self.last_audio_dir = self.settings.value("lastAudioDir", str(Path.home()), str)
        
        # Thêm Audio Player cho MP3 Preview
        if CAN_PLAY_VIDEO:
            self.media_player = QMediaPlayer()
            self.audio_output = QAudioOutput() 
            self.media_player.setAudioOutput(self.audio_output)
            # Khởi tạo Audio Player riêng cho MP3
            self.audio_preview_player = QMediaPlayer()
            self.audio_preview_output = QAudioOutput()
            self.audio_preview_player.setAudioOutput(self.audio_preview_output)
        else:
            self.media_player = None
            self.audio_output = None
            self.audio_preview_player = None
            self.audio_preview_output = None

        # Theme manager instance
        self.theme_manager = PluginThemeManager()
        self.setStyleSheet(self.theme_manager.get_standard_stylesheet())

        self._setup_ui()
        self.reset_ui()
        self.ensure_default_output_dir_exists()
        
    def _create_frame_title(self, text):
        label = QLabel(text)
        label.setObjectName("frameTitle")
        return label
        
    def _create_button(self, text, on_click, bg_color, hover_color, min_size=QSize(0,0)):
        btn = QPushButton(text)
        btn.clicked.connect(on_click)
        btn.setMinimumSize(min_size)
        btn.setStyleSheet(f"QPushButton {{ background-color: {bg_color}; color: white; padding: 6px 12px; border-radius: 6px; font-weight: bold; }} QPushButton:hover {{ background-color: {hover_color}; }} QPushButton:disabled {{ background-color: #555; color: #bbb; }}")
        return btn

    def _create_action_button(self, text, on_click, bg, hover, text_color):
        btn = QPushButton(text)
        btn.clicked.connect(on_click)
        btn.setStyleSheet(f"QPushButton {{ background-color: {bg}; color: {text_color}; padding: 12px 20px; border-radius: 8px; font-weight: bold; font-size: 16px; }} QPushButton:hover {{ background-color: {hover}; }} QPushButton:disabled {{ background-color: #555; color: #bbb; }}")
        return btn

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        title = QLabel("Chèn Nhạc vào Nhiều Video (Hàng loạt)")
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        
        # --- BỐ CỤC LƯỚI 3x2 TÙY CHỈNH ---
        grid_layout = QGridLayout()
        grid_layout.setSpacing(15) 
        
        # Cấu hình Column Stretch
        grid_layout.setColumnStretch(0, 2) # PHÁT VIDEO
        grid_layout.setColumnStretch(1, 1) # NHẬP MP4/MP3
        grid_layout.setColumnStretch(2, 1) # TÙY CHỈNH/ACTION
        
        # 1. PHÁT VIDEO (Hàng 1 & 2, Cột 1 - rowSpan=2)
        self.video_frame = self._create_video_player_widget()
        grid_layout.addWidget(self.video_frame, 0, 0, 2, 1)
        
        # 2. NHẬP MP4 (Hàng 1, Cột 2)
        grid_layout.addWidget(self._create_video_list_widget(), 0, 1)
        
        # 3. TÙY CHỈNH CHỨC NĂNG (Hàng 1, Cột 3)
        self.settings_frame = self._create_settings_widget()
        grid_layout.addWidget(self.settings_frame, 0, 2)

        # 4. NHẬP MP3 (Hàng 2, Cột 2) - NAY LÀ AUDIO PLAYER
        grid_layout.addWidget(self._create_audio_player_frame(), 1, 1)

        # 5. LOADING, START, RESET (Hàng 2, Cột 3)
        action_container = QFrame()
        action_layout = QVBoxLayout(action_container)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(10)
        
        action_layout.addWidget(self._create_output_dir_widget())
        action_layout.addWidget(self._create_loading_status_widget())
        action_layout.addWidget(self._create_action_buttons_widget())
        
        grid_layout.addWidget(action_container, 1, 2)
        
        layout.addLayout(grid_layout)
        layout.addStretch() 
        
        # KẾT NỐI PLAYER VÀ LIST (Giống app1)
        if CAN_PLAY_VIDEO and self.media_player:
            self.media_player.setVideoOutput(self.video_widget)
            self.media_player.positionChanged.connect(self.position_changed)
            self.media_player.durationChanged.connect(self.duration_changed)
            self.media_player.playbackStateChanged.connect(self.state_changed)
            
        # KẾT NỐI AUDIO PREVIEW
        if CAN_PLAY_VIDEO and self.audio_preview_player:
             self.audio_preview_player.positionChanged.connect(self.audio_position_changed)
             self.audio_preview_player.durationChanged.connect(self.audio_duration_changed)
             self.audio_preview_player.playbackStateChanged.connect(self.audio_state_changed)
        
    def _create_frame(self, title):
        frame = QFrame()
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(10, 10, 10, 10)
        
        if title:
             title_label = QLabel(title)
             title_label.setObjectName("frameTitle")
             frame_layout.addWidget(title_label)
        
        return frame, frame_layout
        
    # --- PLAYER WIDGET ---
    def _create_video_player_widget(self):
        """Ô 1: PHÁT VIDEO."""
        video_frame, video_layout = self._create_frame("PHÁT VIDEO")
        video_frame.setMinimumHeight(250) 
        video_layout.setSpacing(5)
        
        if CAN_PLAY_VIDEO:
            self.video_widget = QVideoWidget()
            self.video_widget.setStyleSheet("background-color: black; border-radius: 5px;")
                
            video_layout.addWidget(self.video_widget, 1) 

            # Control Panel (Slider, Play/Pause, Time)
            self.control_panel = QFrame() 
            self.control_panel.setStyleSheet("QFrame { background-color: transparent; border: none; padding: 0px; }")
            control_layout = QVBoxLayout(self.control_panel)
            control_layout.setContentsMargins(0, 0, 0, 0)
            control_layout.setSpacing(5)
            
            # 1. Thanh tua (Position Slider)
            self.position_slider = QSlider(Qt.Orientation.Horizontal)
            self.position_slider.setRange(0, 0)
            self.position_slider.sliderMoved.connect(self.set_position)
            control_layout.addWidget(self.position_slider)
            
            # 2. Hàng Play/Time/Volume
            playback_layout = QHBoxLayout()
            self.play_button = QPushButton("▶️") 
            self.play_button.setObjectName("PlayPauseButton")
            self.play_button.clicked.connect(self.toggle_play_pause)
            playback_layout.addWidget(self.play_button)
            
            self.time_label = QLabel("00:00 / 00:00")
            self.time_label.setStyleSheet("color: #d6d6d6; font-size: 14px; font-weight: bold;")
            playback_layout.addWidget(self.time_label)
            
            playback_layout.addStretch()
            
            # --- ĐIỀU CHỈNH ÂM LƯỢNG ---
            self.volume_icon = QLabel("🔊")
            self.volume_icon.setObjectName("VolumeIcon")
            self.volume_icon.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.volume_icon.mousePressEvent = lambda event: self.toggle_mute(event)
            playback_layout.addWidget(self.volume_icon)
            
            self.volume_slider = VolumeSlider(Qt.Orientation.Horizontal)
            self.volume_slider.setObjectName("VolumeSlider")
            self.volume_slider.setRange(0, 100)
            self.volume_slider.setValue(100)
            self.volume_slider.setFixedWidth(80)
            self.volume_slider.valueChanged.connect(self.set_volume)
            playback_layout.addWidget(self.volume_slider)
            # ---------------------------
            
            control_layout.addLayout(playback_layout)
            video_layout.addWidget(self.control_panel) 
            self.control_panel.setVisible(False) 
            
        else:
            self.video_widget = QLabel("⚠️ Cần cài đặt QtMultimedia để xem trước.")
            self.video_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.video_widget.setStyleSheet("background-color: #1a1a1a; padding: 20px; border-radius: 4px; color: #e74c3c; font-weight: bold;")
            video_layout.addWidget(self.video_widget)
            self.play_button = None
            self.position_slider = None
            self.time_label = None
            
        return video_frame

    # --- INPUT WIDGETS ---
    def _create_video_list_widget(self):
        """Hàng 1, Cột 2: NHẬP MP4."""
        video_list_frame = QFrame()
        video_list_layout = QVBoxLayout(video_list_frame)
        video_list_layout.setContentsMargins(10, 10, 10, 10)
        
        self.video_count_label = QLabel("Video đã chọn: 0")
        video_list_layout.addWidget(self.video_count_label)
        
        self.video_list_widget = QListWidget()
        self.video_list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.video_list_widget.setMinimumHeight(60)
        self.video_list_widget.itemSelectionChanged.connect(self._on_list_selection_changed)
        video_list_layout.addWidget(self.video_list_widget, 1)
        
        # SỬA: Thay nút "Thêm" và "Xóa" bằng Icon
        input_buttons_layout = QHBoxLayout()
        self.btn_add_video = QPushButton("➕")
        self.btn_add_video.setObjectName("AddButton")
        self.btn_add_video.setFixedSize(35, 35) # Icon size
        self.btn_add_video.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.btn_add_video.clicked.connect(self.select_videos)
        input_buttons_layout.addWidget(self.btn_add_video, alignment=Qt.AlignmentFlag.AlignLeft)
        
        self.btn_remove_video = QPushButton("−")
        self.btn_remove_video.setObjectName("RemoveButton")
        self.btn_remove_video.setFixedSize(35, 35) # Icon size
        self.btn_remove_video.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.btn_remove_video.clicked.connect(self.remove_selected_videos_update)
        input_buttons_layout.addWidget(self.btn_remove_video, alignment=Qt.AlignmentFlag.AlignLeft)
        
        input_buttons_layout.addStretch(1)
        
        # Nút Xóa tất cả (Giữ nguyên text và icon X)
        btn_clear_videos = self._create_button("❌ Xóa tất cả", self.clear_all_videos, "#dc3545", "#c82333")
        input_buttons_layout.addWidget(btn_clear_videos, alignment=Qt.AlignmentFlag.AlignRight)
        
        video_list_layout.addLayout(input_buttons_layout)
        
        return video_list_frame

    def _create_audio_player_frame(self):
        """Hàng 2, Cột 2: TRÌNH NGHE MP3."""
        audio_container, audio_layout = self._create_frame("TRÌNH NGHE MP3")
        audio_layout.setContentsMargins(10, 10, 10, 10)
        
        # 1. Hiển thị tên file MP3
        self.audio_path_line = QLineEdit("Chưa có nhạc nào được chọn...")
        self.audio_path_line.setReadOnly(True)
        audio_layout.addWidget(self.audio_path_line)
        
        # 2. Nút chọn/xóa file
        file_buttons_layout = QHBoxLayout()
        btn_add_audio = self._create_button("Chọn nhạc", self.select_audio, "#e74c3c", "#c0392b")
        btn_clear_audio = self._create_button("Xóa nhạc", self.clear_audio, "#6c757d", "#5a6268")
        file_buttons_layout.addWidget(btn_add_audio)
        file_buttons_layout.addWidget(btn_clear_audio)
        audio_layout.addLayout(file_buttons_layout)
        
        if CAN_PLAY_VIDEO:
            # 3. Controls Preview
            audio_controls_frame = QFrame()
            audio_controls_frame.setObjectName("AudioControls")
            controls_layout = QVBoxLayout(audio_controls_frame)
            controls_layout.setContentsMargins(5, 5, 5, 5)
            
            self.audio_position_slider = QSlider(Qt.Orientation.Horizontal)
            self.audio_position_slider.setRange(0, 0)
            self.audio_position_slider.sliderMoved.connect(self.audio_set_position)
            controls_layout.addWidget(self.audio_position_slider)
            
            play_time_layout = QHBoxLayout()
            self.audio_play_button = QPushButton("▶️")
            self.audio_play_button.setObjectName("AudioPlayButton")
            self.audio_play_button.setFixedSize(30, 30)
            self.audio_play_button.clicked.connect(self.audio_toggle_play_pause)
            play_time_layout.addWidget(self.audio_play_button)
            
            self.audio_time_label = QLabel("00:00 / 00:00")
            play_time_layout.addWidget(self.audio_time_label)
            play_time_layout.addStretch()
            
            controls_layout.addLayout(play_time_layout)
            
            audio_layout.addWidget(audio_controls_frame)
            self.audio_controls_frame = audio_controls_frame
            self.audio_controls_frame.setVisible(False)
        
        audio_layout.addStretch()
        return audio_container

    # --- SETTINGS WIDGET ---
    def _create_settings_widget(self):
        """Hàng 1, Cột 3: TÙY CHỈNH CHỨC NĂNG (Chỉ có Mute/Mix và Volume cho app3)."""
        settings_frame = QFrame()
        settings_layout = QVBoxLayout(settings_frame)
        
        settings_layout.addWidget(self._create_frame_title("TÙY CHỈNH CHỨC NĂNG:"))
        settings_layout.addSpacing(10)
        
        # Mute/Replace (Thay thế cho Thời lượng)
        self.mute_checkbox = QCheckBox("Tắt âm thanh gốc (Thay thế bằng nhạc mới)")
        self.mute_checkbox.setStyleSheet("QCheckBox { color: #bfbfbf; font-weight: bold; }")
        # Mặc định của APP3 là trộn (False), khác APP2
        self.mute_checkbox.setChecked(self.settings.value("muteOriginal", False, bool))
        self.mute_checkbox.stateChanged.connect(lambda state: self.settings.setValue("muteOriginal", bool(state)))
        settings_layout.addWidget(self.mute_checkbox)
        
        # Volume
        volume_layout = QHBoxLayout()
        volume_layout.addWidget(QLabel("Âm lượng nhạc nền:"))
        self.volume_slider_settings = VolumeSlider(Qt.Orientation.Horizontal) 
        self.volume_slider_settings.setRange(0, 200)
        self.volume_slider_settings.setValue(self.settings.value("volume", 100, int))
        self.volume_slider_settings.valueChanged.connect(self.update_volume_label)
        self.volume_label = QLabel(f"{self.settings.value('volume', 100, int)}%")
        self.volume_label.setMinimumWidth(40)
        volume_layout.addWidget(self.volume_slider_settings)
        volume_layout.addWidget(self.volume_label)
        settings_layout.addLayout(volume_layout)
        
        settings_layout.addStretch()
        return settings_frame
    
    # --- ACTION WIDGETS ---
    
    def _create_output_dir_widget(self):
        """Thư mục đầu ra."""
        output_frame = QFrame()
        output_layout = QVBoxLayout(output_frame)
        output_layout.setContentsMargins(0, 0, 0, 0)
        
        output_dir_label = QLabel("Thư mục lưu kết quả:"); 
        output_dir_label.setStyleSheet("font-weight: bold;"); 
        output_layout.addWidget(output_dir_label)
        
        output_dir_layout = QHBoxLayout()
        self.output_dir_line = QLineEdit()
        self.output_dir_line.setReadOnly(True)
        output_dir_layout.addWidget(self.output_dir_line)
        
        btn_browse_output = self._create_button("Lưu", self.select_output_directory, "#28a745", "#5a6268")
        btn_browse_output.setFixedSize(80, 35)
        output_dir_layout.addWidget(btn_browse_output)
        output_layout.addLayout(output_dir_layout)
        
        return output_frame

    def _create_loading_status_widget(self):
        """Phần Progress Bar và Status Message."""
        loading_frame = QFrame()
        loading_layout = QVBoxLayout(loading_frame)
        loading_layout.setContentsMargins(0, 0, 0, 0)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Chờ xử lý...")
        loading_layout.addWidget(self.progress_bar)
        
        # Message Label
        self.progress_message_label = QLabel("")
        self.progress_message_label.setStyleSheet("color: #aaaaaa; font-size: 12px; margin-top: 5px;")
        loading_layout.addWidget(self.progress_message_label)
        
        return loading_frame
        
    def _create_action_buttons_widget(self):
        """Phần START, RESET."""
        action_buttons_frame = QFrame()
        action_buttons_layout = QHBoxLayout(action_buttons_frame)
        action_buttons_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_run = self._create_action_button("🚀 Bắt đầu Xử Lý", self.start_processing, "#00b894", "#00d19a", "#071717")
        self.btn_run.setMinimumHeight(40)
        self.btn_run.setEnabled(False)
        action_buttons_layout.addWidget(self.btn_run)
        
        self.btn_cancel = self._create_action_button("❌ Reset", self.handle_cancel_or_reset, "#dc3545", "#c82333", "white")
        self.btn_cancel.setObjectName("ResetButton")
        self.btn_cancel.setMinimumHeight(40)
        action_buttons_layout.addWidget(self.btn_cancel)
        
        return action_buttons_frame
    
    # --- PLAYER METHODS (VIDEO) ---
    # NOTE: Logic này chỉ để xem preview. App3 không có logic cập nhật progress bar dựa trên thời gian thực.
    def toggle_play_pause(self):
        if not self.media_player: return
        current_state = self.media_player.playbackState()
        if current_state == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        elif current_state == QMediaPlayer.PlaybackState.PausedState:
            self.media_player.play()
        elif current_state == QMediaPlayer.PlaybackState.StoppedState:
            self.media_player.play()

    def state_changed(self, state):
        if not self.media_player or not hasattr(self, 'play_button'): return
        
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_button.setText("⏸️")
            if self.audio_preview_player and self.audio_preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                 self.audio_preview_player.pause() # Dừng audio preview khi phát video
        else:
            self.play_button.setText("▶️")

    def position_changed(self, position):
        if not self.media_player or not hasattr(self, 'position_slider'): return
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(position)
        
        current_time = QTime(0, 0, 0).addMSecs(position)
        total_time = QTime(0, 0, 0).addMSecs(self.media_player.duration())
        total_time_str = total_time.toString('mm:ss') if self.media_player.duration() > 0 else "00:00"
        if hasattr(self, 'time_label'):
             self.time_label.setText(f"{current_time.toString('mm:ss')} / {total_time_str}")

    def duration_changed(self, duration):
        if not hasattr(self, 'position_slider'): return
        self.position_slider.setRange(0, duration)
        
        if duration > 0 and hasattr(self, 'control_panel'):
            self.control_panel.setVisible(True)
        else:
            self.control_panel.setVisible(False)
            
    def set_position(self, position):
        if self.media_player:
            self.media_player.setPosition(position)

    def set_volume(self, value):
        if not CAN_PLAY_VIDEO or not self.audio_output: return
        if value > 0 and self.is_muted:
            self.is_muted = False
        volume = value / 100.0
        self.audio_output.setVolume(volume)
        self._update_volume_icon(value)
        if not self.is_muted:
            self.last_volume = value
        
    def toggle_mute(self, event):
        if not CAN_PLAY_VIDEO or not self.audio_output or not isinstance(event, QMouseEvent): return
        
        if self.is_muted:
            target_volume = self.last_volume if self.last_volume > 0 else 50
            self.is_muted = False
            self.volume_slider.setValue(target_volume)
            self.audio_output.setVolume(target_volume / 100.0)
            self._update_volume_icon(target_volume)
        else:
            current_volume = self.volume_slider.value()
            if current_volume > 0:
                self.last_volume = current_volume
            
            self.is_muted = True
            self.volume_slider.setValue(0)
            self.audio_output.setVolume(0.0)
            self._update_volume_icon(0)

    def _update_volume_icon(self, volume_level):
        if not hasattr(self, 'volume_icon'): return
        if self.is_muted or volume_level == 0:
            self.volume_icon.setText("🔇") 
        elif volume_level > 70:
            self.volume_icon.setText("🔊")
        elif volume_level > 0:
            self.volume_icon.setText("🔉")
        else:
            self.volume_icon.setText("🔈")
            
    # --- PLAYER METHODS (AUDIO MP3 PREVIEW) ---
    def audio_toggle_play_pause(self):
        if not self.audio_preview_player: return
        current_state = self.audio_preview_player.playbackState()
        if current_state == QMediaPlayer.PlaybackState.PlayingState:
            self.audio_preview_player.pause()
        else:
            if self.media_player and self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.media_player.pause() # Dừng video khi phát audio
            self.audio_preview_player.play()

    def audio_state_changed(self, state):
        if not self.audio_preview_player or not hasattr(self, 'audio_play_button'): return
        
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.audio_play_button.setText("⏸️")
        else:
            self.audio_play_button.setText("▶️")

    def audio_position_changed(self, position):
        if not self.audio_preview_player or not hasattr(self, 'audio_position_slider'): return
        if not self.audio_position_slider.isSliderDown():
            self.audio_position_slider.setValue(position)
        
        current_time = QTime(0, 0, 0).addMSecs(position)
        total_time = QTime(0, 0, 0).addMSecs(self.audio_preview_player.duration())
        total_time_str = total_time.toString('mm:ss') if self.audio_preview_player.duration() > 0 else "00:00"
        if hasattr(self, 'audio_time_label'):
             self.audio_time_label.setText(f"{current_time.toString('mm:ss')} / {total_time_str}")

    def audio_duration_changed(self, duration):
        if not hasattr(self, 'audio_position_slider'): return
        self.audio_position_slider.setRange(0, duration)
        
    def audio_set_position(self, position):
        if self.audio_preview_player:
            self.audio_preview_player.setPosition(position)
            
    # --- END AUDIO PLAYER METHODS ---
    
    # --- LOGIC THAO TÁC ---
    
    def remove_selected_videos_update(self):
        """Xóa video đang chọn khỏi list và cập nhật self.videos."""
        
        selected_items = self.video_list_widget.selectedItems()
        if not selected_items: return
        
        # Lưu trữ tên file để xóa
        file_names_to_remove = [item.text() for item in selected_items]
        
        # Danh sách mới
        new_videos = []
        for path in self.videos:
            if Path(path).name not in file_names_to_remove:
                new_videos.append(path)
        
        self.videos = new_videos
        
        # Xóa các item khỏi list widget (phải theo thứ tự ngược lại để tránh lỗi index)
        rows_to_remove = [self.video_list_widget.row(item) for item in selected_items]
        rows_to_remove.sort(reverse=True)
        for row in rows_to_remove:
            self.video_list_widget.takeItem(row)
            
        self.update_video_count_label()
        self._update_run_button_state()
        
        if self.media_player and not self.videos:
             self.media_player.stop()
             self.control_panel.setVisible(False)
        elif self.media_player and self.videos:
             # Phát video đầu tiên trong danh sách mới
             self.media_player.setSource(QUrl.fromLocalFile(self.videos[0]))
             self.media_player.play()


    def clear_all_videos(self):
        if self.media_player: self.media_player.stop()
        self.videos.clear()
        self.video_list_widget.clear()
        self.update_video_count_label()
        self._update_run_button_state()
        if hasattr(self, 'control_panel'): self.control_panel.setVisible(False)
        if self.media_player: self.media_player.setSource(QUrl())


    def select_videos(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Chọn video MP4", self.last_video_dir, "Video (*.mp4)")
        if files:
            self.last_video_dir = os.path.dirname(files[0])
            self.settings.setValue("lastVideoDir", self.last_video_dir)
            
            is_new_file = False
            for file in files:
                if file not in self.videos:
                    self.videos.append(file)
                    item = QListWidgetItem(os.path.basename(file))
                    self.video_list_widget.addItem(item)
                    is_new_file = True
                    
            if self.media_player and is_new_file and len(self.videos) > 0:
                # Tự động phát video đầu tiên khi thêm video
                self.media_player.setSource(QUrl.fromLocalFile(self.videos[0]))
                self.media_player.play()
                
            self.update_video_count_label()
        self._update_run_button_state()
        
    def _on_list_selection_changed(self):
        selected_items = self.video_list_widget.selectedItems()
        
        is_running = self.worker_thread and self.worker_thread.isRunning()
        self.btn_remove_video.setEnabled(bool(selected_items) and not is_running)

        if not selected_items:
            if self.media_player: self.media_player.stop()
            return
            
        row = self.video_list_widget.row(selected_items[0])
        
        if self.media_player and 0 <= row < len(self.videos):
            selected_path = self.videos[row]
            
            if self.media_player.source() != QUrl.fromLocalFile(selected_path):
                self.media_player.setSource(QUrl.fromLocalFile(selected_path))
            
            self.media_player.play() # Phát khi chọn
    
    def update_video_count_label(self):
        count = len(self.videos)
        if count == 0:
            self.video_count_label.setText("Video đã chọn: 0")
        else:
            self.video_count_label.setText(f"Video đã chọn: {count}")
        
    def select_audio(self):
        file, _ = QFileDialog.getOpenFileName(self, "Chọn nhạc MP3", self.last_audio_dir, "Audio (*.mp3)")
        if file:
            # Dừng preview cũ
            if self.audio_preview_player: self.audio_preview_player.stop()
            
            self.last_audio_dir = os.path.dirname(file)
            self.settings.setValue("lastAudioDir", self.last_audio_dir)
            self.audio = file
            self.audio_path_line.setText(os.path.basename(file))
            
            # Cấu hình Audio Preview
            if self.audio_preview_player:
                 self.audio_preview_player.setSource(QUrl.fromLocalFile(file))
                 self.audio_controls_frame.setVisible(True)
                 # self.audio_preview_player.play() # Không phát tự động để tránh xung đột
        
        self._update_run_button_state()

    def clear_audio(self):
        if self.audio_preview_player: self.audio_preview_player.stop()
        self.audio = None
        self.audio_path_line.setText("Chưa có nhạc nào được chọn...")
        if hasattr(self, 'audio_controls_frame'): self.audio_controls_frame.setVisible(False)
        self._update_run_button_state()
        
    def select_output_directory(self):
        current_dir = self.output_dir_line.text()
        directory = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu", current_dir)
        if directory:
            self.output_dir_line.setText(directory)
            self.settings.setValue("outputDir", directory)
            
    def ensure_default_output_dir_exists(self):
        default_dir = Path.home() / "Videos" / "VideoEditorTool_App3"; 
        saved_dir = self.settings.value("outputDir", str(default_dir), str)
        self.output_dir_line.setText(saved_dir)
        if not Path(saved_dir).exists():
            try:
                Path(saved_dir).mkdir(parents=True, exist_ok=True)
            except Exception:
                self.output_dir_line.setText(str(Path.home()))

    def update_volume_label(self, value):
        self.volume_label.setText(f"{value}%")
        self.settings.setValue("volume", value)
        
    def _update_run_button_state(self):
        is_running = self.worker_thread and self.worker_thread.isRunning()
        can_run = bool(self.videos) and bool(self.audio) and not is_running
        
        self.btn_run.setEnabled(can_run)
        self.btn_cancel.setText("❌ Hủy" if is_running else "❌ Reset")
        
        controls_enabled = not is_running
        self.set_controls_enabled(controls_enabled)
        
        if can_run: 
            self.btn_run.setStyleSheet("background-color: #00b894; color: #071717; font-size: 16px; font-weight: bold;")
        else: 
            self.btn_run.setStyleSheet("background-color: #555555; color: #bbbbbb; font-size: 16px; font-weight: bold;")
        
        

    def reset_ui(self):
        self.clear_all_videos()
        self.clear_audio()
        
        # Reset Audio Preview
        if self.audio_preview_player: self.audio_preview_player.stop()
        if hasattr(self, 'audio_controls_frame'): self.audio_controls_frame.setVisible(False)
        
        # Reset từ Settings
        self.mute_checkbox.setChecked(self.settings.value("muteOriginal", False, bool))
        self.volume_slider_settings.setValue(self.settings.value("volume", 100, int))
        self.update_volume_label(self.volume_slider_settings.value())
        
        self.progress_bar.setValue(0)
        self.progress_message_label.setText("") # Loại bỏ chữ "Sẵn sàng."
        self.progress_bar.setFormat("Chờ xử lý...")
        
        if CAN_PLAY_VIDEO and self.audio_output and hasattr(self, 'volume_slider'):
             self.volume_slider.setValue(100)
             self.audio_output.setVolume(1.0)
             self._update_volume_icon(100)
             
        self.set_controls_enabled(True)
        self._update_run_button_state()

    def set_controls_enabled(self, enabled):
        widgets_to_toggle = self.findChildren((QPushButton, QSpinBox, QListWidget, QSlider, QCheckBox))
        for child in widgets_to_toggle:
            if child not in [self.btn_run, self.btn_cancel, self.btn_remove_video]:
                child.setEnabled(enabled)
        
        # Nút xóa video chỉ bật khi có video trong list VÀ không đang chạy
        self.btn_remove_video.setEnabled(enabled and bool(self.videos))
        
        for btn in self.findChildren(QPushButton):
            if btn.text() == "❌ Xóa tất cả":
                btn.setEnabled(enabled and bool(self.videos))
        
        # Bật/tắt Player controls (Nếu có)
        if CAN_PLAY_VIDEO and hasattr(self, 'control_panel'):
            is_playing_item_available = bool(self.videos) and enabled
            self.control_panel.setEnabled(is_playing_item_available)
            if self.audio_output:
                self.volume_slider.setEnabled(is_playing_item_available)
            if self.media_player and self.media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                 self.play_button.setEnabled(is_playing_item_available)
                 
        if CAN_PLAY_VIDEO and hasattr(self, 'audio_controls_frame'):
            self.audio_controls_frame.setEnabled(enabled and bool(self.audio))


    def start_processing(self):
        if not self.videos or not self.audio:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng chọn video và nhạc nền.")
            return
        
        output_dir = Path(self.output_dir_line.text())
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Dừng mọi trình phát trước khi bắt đầu
        if self.media_player: self.media_player.stop()
        if self.audio_preview_player: self.audio_preview_player.stop()
        
        self.set_controls_enabled(False)
        self.btn_run.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_message_label.setText("Đang khởi tạo...")
        QApplication.processEvents() # Cập nhật giao diện

        self.worker_thread = FFmpegBatchWorker(
            list(self.videos), self.audio, output_dir,
            self.mute_checkbox.isChecked(), self.volume_slider_settings.value()
        )

        self.worker_thread.progress_signal.connect(self.update_progress)
        self.worker_thread.finished_signal.connect(self.processing_finished)
        self.worker_thread.error_signal.connect(self.processing_error)
        self.worker_thread.start()

    def handle_cancel_or_reset(self):
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(self, "Xác nhận hủy", "Bạn có muốn dừng quá trình đang chạy không?")
            if reply == QMessageBox.StandardButton.Yes:
                self.worker_thread.cancel()
                self.progress_message_label.setText("") 
                self.progress_bar.setFormat("Đã hủy bởi người dùng.")
                self.set_controls_enabled(True)
                self.btn_run.setEnabled(True)
        else:
            self.reset_ui()
            
    def update_progress(self, percentage, message):
        self.progress_bar.setValue(percentage)
        self.progress_bar.setFormat(f"{percentage}% - {message.split('...')[0]}")
        self.progress_message_label.setText(message) # Hiển thị mô tả bước

    def processing_finished(self, output_path_or_dir):
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("Hoàn thành!")
        self.progress_message_label.setText("")
        QMessageBox.information(self, "Thành công", f"Đã xử lý xong tất cả video!\nKết quả được lưu tại thư mục:\n{output_path_or_dir}")

        self.set_controls_enabled(True)
        self._update_run_button_state()
        try: os.startfile(Path(output_path_or_dir))
        except: pass


    def processing_error(self, error_message):
        error_box = QMessageBox()
        error_box.setIcon(QMessageBox.Icon.Critical)
        error_box.setText("Đã xảy ra lỗi trong quá trình xử lý.")
        error_box.setInformativeText("Vui lòng xem chi tiết bên dưới.")
        error_box.setDetailedText(error_message)
        error_box.setWindowTitle("Lỗi")
        error_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        error_box.exec()

        self.progress_message_label.setText("")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Đã xảy ra lỗi.")
        self.set_controls_enabled(True)
        self._update_run_button_state()
    
    def set_theme(self, theme_name):
        """Set theme for this plugin"""
        if self.theme_manager.set_theme(theme_name):
            self.setStyleSheet(self.theme_manager.get_standard_stylesheet())
            return True
        return False

# CHỈNH SỬA 3: Xóa hàm run_tool()
# def run_tool():
#    return InsertAudioBatchWidget()
