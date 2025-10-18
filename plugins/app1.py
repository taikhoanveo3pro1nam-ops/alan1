# app1.py - Tua Nhanh / Làm Chậm / Zoom Video (Giao diện tùy biến theo app5)

import sys
import os
import re
import shutil
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QDoubleSpinBox, QCheckBox, QMessageBox, QFrame, QLineEdit,
    QProgressBar, QListWidget, QListWidgetItem, QScrollArea, QSlider, QGridLayout, QApplication
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QThread, QSettings, QUrl, QTime, QSize, QSizeF, QTimer
)
from PyQt6.QtGui import QFont, QCursor, QMouseEvent, QTransform
import time

try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
    from PyQt6.QtMultimediaWidgets import QVideoWidget, QGraphicsVideoItem
    from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene
    from PyQt6.QtGui import QPainter
    CAN_PLAY_VIDEO = True
except ImportError:
    CAN_PLAY_VIDEO = False

# Import theme manager
from theme_manager import PluginThemeManager

class TransformableVideoWidget(QGraphicsView):
    """Professional video widget with real-time transform preview"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_zoom = 1.0
        self._current_flip = False
        self._current_speed = 1.0
        
        # Setup graphics scene and video item
        self._scene = QGraphicsScene()
        self.setScene(self._scene)
        
        self._video_item = QGraphicsVideoItem()
        self._scene.addItem(self._video_item)
        
        # Configure graphics view for professional video playback
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("""
            QGraphicsView {
                background-color: black; 
                border-radius: 5px;
                border: 2px solid #333;
            }
        """)
        
        # Set fixed 16:9 aspect ratio
        self._aspect_ratio = 16.0 / 9.0
        self._video_item.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        
        # Set initial size and position with 16:9 aspect ratio
        self._setupVideoItemSize()
        
        # Enable smooth scaling and clipping
        self._video_item.setFlag(self._video_item.GraphicsItemFlag.ItemIgnoresTransformations, False)
        self._video_item.setFlag(self._video_item.GraphicsItemFlag.ItemClipsToShape, True)
        
        # Set initial scene rect
        self._scene.setSceneRect(0, 0, self.width(), self.height())
        
    def _setupVideoItemSize(self):
        """Setup video item size to fit within 16:9 frame while maintaining aspect ratio"""
        widget_width = self.width()
        widget_height = self.height()
        
        # Calculate size that fits within the 16:9 frame while maintaining video's aspect ratio
        # This will add black bars if needed but won't distort the video
        size_f = QSizeF(widget_width, widget_height)
        self._video_item.setSize(size_f)
        self._video_item.setPos(0, 0)
        
        # Keep aspect ratio to prevent distortion
        self._video_item.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        
    def setVideoOutput(self, media_player):
        """Set video output for media player"""
        self._media_player = media_player
        media_player.setVideoOutput(self._video_item)
        
    def setPreviewTransform(self, zoom=1.0, flip=False, speed=1.0):
        """Apply real-time transform to video item with speed preview"""
        self._current_zoom = zoom
        self._current_flip = flip
        self._current_speed = speed
        
        # Create transform matrix
        transform = QTransform()
        
        # Get widget center for proper centering
        center_x = self.width() / 2
        center_y = self.height() / 2
        
        # Apply zoom with center point
        if zoom != 1.0:
            transform.translate(center_x, center_y)
            transform.scale(zoom, zoom)
            transform.translate(-center_x, -center_y)
            
        # Apply flip
        if flip:
            transform.translate(center_x, center_y)
            transform.scale(-1, 1)
            transform.translate(-center_x, -center_y)
            
        # Apply transform to video item
        self._video_item.setTransform(transform)
        
        # Ensure video item clips to shape to prevent overflow
        self._video_item.setFlag(self._video_item.GraphicsItemFlag.ItemClipsToShape, True)
        
        # Apply speed to media player if available
        if hasattr(self, '_media_player') and self._media_player:
            self._media_player.setPlaybackRate(speed)
        
        # Force immediate update
        self._scene.update()
        self.update()
        
    def resetTransform(self):
        """Reset transform to normal"""
        self._current_zoom = 1.0
        self._current_flip = False
        self._current_speed = 1.0
        self._video_item.resetTransform()
        
        # Reset speed to normal
        if hasattr(self, '_media_player') and self._media_player:
            self._media_player.setPlaybackRate(1.0)
        
        self._scene.update()
        self.update()
        
    def resizeEvent(self, event):
        """Handle resize to fit within 16:9 frame while maintaining aspect ratio"""
        super().resizeEvent(event)
        if hasattr(self, '_video_item'):
            # Get the new size
            new_size = event.size()
            widget_width = new_size.width()
            widget_height = new_size.height()
            
            # Fit within the 16:9 frame while maintaining aspect ratio
            size_f = QSizeF(widget_width, widget_height)
            self._video_item.setSize(size_f)
            self._video_item.setPos(0, 0)
            
            # Keep aspect ratio to prevent distortion
            self._video_item.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
            
            # Ensure video item fits within bounds
            self._video_item.setFlag(self._video_item.GraphicsItemFlag.ItemClipsToShape, True)
            
            # Set scene rect to match widget size
            self._scene.setSceneRect(0, 0, widget_width, widget_height)
            
            # Reapply current transform after resize
            self.setPreviewTransform(self._current_zoom, self._current_flip, self._current_speed)

class VolumeSlider(QSlider):
    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            if self.orientation() == Qt.Orientation.Horizontal:
                value = self.minimum() + (self.maximum() - self.minimum()) * event.pos().x() / self.width()
            else:
                value = self.maximum() - (self.maximum() - self.minimum()) * event.pos().y() / self.height()
            self.setValue(int(value))

# Theme manager instance
theme_manager = PluginThemeManager()

def get_standard_stylesheet():
    return theme_manager.get_standard_stylesheet()

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

FFMPEG_EXE = BASE_DIR / "ffmpeg.exe"
FFPROBE_EXE = BASE_DIR / "ffprobe.exe" 

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

# SỬA LỖI: Toàn bộ Class này đã được viết lại để sửa lỗi Race Condition
class VideoProcessingWorker(QThread):
    progress_update = pyqtSignal(int, str)
    video_finished = pyqtSignal(str, bool, str)
    all_videos_finished = pyqtSignal(int, int, str)
    processing_cancelled = pyqtSignal()
    
    def __init__(self, video_tasks, max_workers):
        super().__init__()
        self.video_tasks = video_tasks
        self.max_workers = max_workers
        self._is_cancelled = False
        self.processes = {}
        self.ffmpeg_cmd_base = [str(FFMPEG_EXE)] if FFMPEG_EXE.exists() else ["ffmpeg"]
        self.ffprobe_cmd_base = [str(FFPROBE_EXE)] if FFPROBE_EXE.exists() else ["ffprobe"]
        
    def cancel(self):
        self._is_cancelled = True
        for p, _, _ in self.processes.values():
            if p.poll() is None:
                try: 
                    p.terminate()
                    p.wait(timeout=5)
                except Exception: 
                    pass
                
    def run(self):
        tasks_queue = list(self.video_tasks)
        progress_map = {task['path']: 0 for task in self.video_tasks}
        durations = {}
        
        # Lấy thời lượng của tất cả video trước
        for task in tasks_queue:
            if self._is_cancelled: break
            durations[task['path']] = self._get_video_duration(task['path'])
            if durations[task['path']] == 0:
                self.video_finished.emit(task['path'], False, "Lỗi: Không đọc được thời lượng video.")
        
        # Lọc ra các task bị lỗi
        tasks_queue = [t for t in tasks_queue if durations[t['path']] > 0]
        
        if self._is_cancelled:
            self.processing_cancelled.emit()
            return
            
        success_count, error_count, finished_tasks = 0, 0, set()
        output_dir = self.video_tasks[0]['output_dir'] if self.video_tasks else ""
        
        while (tasks_queue or self.processes) and not self._is_cancelled:
            # Khởi động các tác vụ mới nếu có chỗ trống
            while len(self.processes) < self.max_workers and tasks_queue:
                if self._is_cancelled: break
                task = tasks_queue.pop(0)
                process, final_output_path = self._start_single_video_processing(task)
                if process:
                    self.processes[task['path']] = (process, final_output_path, [])

            finished_paths_this_iteration = []
            
            # Kiểm tra tiến trình và trạng thái của các video đang chạy
            for path, (process, _, output_lines) in self.processes.items():
                if process.poll() is not None:
                    finished_paths_this_iteration.append(path)
                    continue

                try:
                    while True:
                        line = process.stderr.readline()
                        if not line: break
                        output_lines.append(line)
                        time_match = re.search(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})", line)
                        if time_match and durations.get(path, 0) > 0:
                            h, m, s, ms = map(int, time_match.groups())
                            time_sec = h * 3600 + m * 60 + s + ms / 100.0
                            speed_ratio = next(t['speed_ratio'] for t in self.video_tasks if t['path'] == path)
                            output_duration = durations[path] / speed_ratio
                            percentage = int((time_sec / output_duration) * 100)
                            progress_map[path] = min(percentage, 99)
                except (IOError, ValueError):
                    pass

            # Xử lý các tác vụ đã hoàn thành trong vòng lặp này
            if finished_paths_this_iteration:
                for path in finished_paths_this_iteration:
                    if path in finished_tasks: continue

                    process, final_output_path, output_lines = self.processes.pop(path)
                    
                    try:
                        remaining_stderr = process.stderr.read()
                        full_output = "".join(output_lines) + remaining_stderr
                    except:
                        full_output = "".join(output_lines)

                    if process.returncode == 0 and not self._is_cancelled:
                        success, msg = True, "Hoàn thành"
                        success_count += 1
                        progress_map[path] = 100
                    else:
                        error_msg = full_output.strip().split('\n')[-1] if full_output else "Lỗi không xác định"
                        success, msg = False, "Đã hủy" if self._is_cancelled else f"Lỗi: {error_msg}"
                        error_count += 1
                        progress_map[path] = 0
                        if os.path.exists(final_output_path):
                            try: os.remove(final_output_path)
                            except OSError: pass
                    
                    self.video_finished.emit(path, success, msg)
                    finished_tasks.add(path)

            # Cập nhật tiến trình tổng thể
            total_duration = sum(durations.values())
            if total_duration > 0:
                processed_duration = sum(progress_map.get(task['path'], 0) * durations.get(task['path'], 0) / 100.0 for task in self.video_tasks)
                overall_percentage = int(processed_duration / total_duration * 100)
                message = f"Đang xử lý {len(self.processes)} video... (Tổng: {overall_percentage}%)"
                self.progress_update.emit(min(99, overall_percentage), message)
            
            time.sleep(0.1)
            
        if self._is_cancelled: 
            self.processing_cancelled.emit()
        else: 
            error_count = len(self.video_tasks) - success_count
            self.all_videos_finished.emit(success_count, error_count, output_dir)
            
    def _get_video_duration(self, video_path):
        try:
            safe_video_path = os.path.normpath(video_path)
            cmd = self.ffprobe_cmd_base + ["-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", safe_video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW, encoding='utf-8')
            return float(result.stdout.strip())
        except Exception: return 0
        
    def _start_single_video_processing(self, task):
        video_path, output_dir = os.path.normpath(task['path']), os.path.normpath(task['output_dir'])
        mute_original, speed_ratio, flip_video = task['mute_original'], task['speed_ratio'], task['flip_video'] 
        zoom_factor = task.get('zoom_factor', 1.0)
        is_speed_unchanged, is_zoom_unchanged = abs(speed_ratio - 1.0) < 0.001, abs(zoom_factor - 1.0) < 0.001
        
        try:
            audio_check_cmd = self.ffprobe_cmd_base + ["-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", video_path]
            has_audio = subprocess.run(audio_check_cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW, encoding='utf-8').stdout.strip()
            has_audio = bool(has_audio)
        except Exception: 
            has_audio = False

        base_name = os.path.splitext(os.path.basename(video_path))[0]
        safe_base_name = re.sub(r'[\\/*?:"<>|]', "", base_name)
        
        speed_tag, zoom_tag, flip_tag = ('' if is_speed_unchanged else f'_speed_{speed_ratio:.2f}x'), ('' if is_zoom_unchanged else f'_zoom_{zoom_factor:.2f}x'), ('_flipped' if flip_video else '')
        final_output_path = os.path.join(output_dir, f"{safe_base_name}{speed_tag}{zoom_tag}{flip_tag}.mp4")
        
        counter = 1
        while os.path.exists(final_output_path):
            final_output_path = os.path.join(output_dir, f"{safe_base_name}{speed_tag}{zoom_tag}{flip_tag}({counter}).mp4"); counter += 1
            
        cmd = self.ffmpeg_cmd_base + ["-y", "-i", video_path]
        needs_re_encode = False
        
        audio_filters, audio_source_map = [], None
        if not mute_original and has_audio:
            audio_source_map = "0:a:0"
            if not is_speed_unchanged:
                audio_filters.append(f"atempo={speed_ratio}")
                needs_re_encode = True
        
        video_filters = []
        if not is_zoom_unchanged: video_filters.append(f"crop=iw/{zoom_factor}:ih/{zoom_factor}")
        if flip_video: video_filters.append("hflip")
        if not is_speed_unchanged: video_filters.append(f"setpts={1/speed_ratio}*PTS")
        if video_filters: needs_re_encode = True
        
        filter_complex_parts, map_parts = [], []
        
        if video_filters:
            filter_complex_parts.append(f"[0:v]{','.join(video_filters)}[v_out]")
            map_parts.extend(["-map", "[v_out]"])
        else: 
            map_parts.extend(["-map", "0:v:0"])
            
        if audio_source_map:
            if audio_filters:
                filter_complex_parts.append(f"[{audio_source_map}]{','.join(audio_filters)}[a_out]")
                map_parts.extend(["-map", "[a_out]"])
            else: 
                map_parts.extend(["-map", audio_source_map])
        else:
            map_parts.append("-an")

        if needs_re_encode:
            if filter_complex_parts: cmd.extend(["-filter_complex", ";".join(filter_complex_parts)])
            cmd.extend(map_parts)
            cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-movflags", "+faststart"])
            if "-an" not in map_parts:
                 cmd.extend(["-c:a", "aac", "-b:a", "128k"])
        else: 
            cmd.extend(["-c", "copy"])
            cmd.extend(map_parts)
            
        cmd.append(final_output_path)

        return subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, 
            universal_newlines=True, creationflags=subprocess.CREATE_NO_WINDOW, encoding='utf-8'
        ), final_output_path

class PluginWidget(QWidget):
    PLUGIN_NAME = "Tua/Zoom/Lật Video"
    PLUGIN_DESCRIPTION = "Tăng/giảm tốc độ, zoom và lật video hàng loạt. Hỗ trợ xử lý nhiều file cùng lúc."
    
    def __init__(self):
        super().__init__()
        self.video_items, self.output_dir, self.worker_thread = {}, "", None
        self.setStyleSheet(get_standard_stylesheet())
        self._is_destroyed = False
        
        # Preview state tracking
        self.preview_zoom = 1.0
        self.preview_flip = False
        self.preview_speed = 1.0
        self.is_preview_mode = False
        
        # Fullscreen state tracking
        self.is_fullscreen = False
        self.original_geometry = None
        self._updating_fullscreen_slider = False
        
        # Fullscreen timer for all fullscreen updates
        self.fullscreen_timer = QTimer()
        self.fullscreen_timer.timeout.connect(self._update_all_fullscreen_controls)
        self.fullscreen_timer.setInterval(100)  # Update every 100ms for smooth seeking

        if CAN_PLAY_VIDEO:
            self.media_player = QMediaPlayer()
            self.audio_output = QAudioOutput()
            self.media_player.setAudioOutput(self.audio_output)
        else:
            self.media_player = None
            self.audio_output = None
            
        self.temp_dir, self.is_muted, self.last_volume = None, False, 100
        self.settings = QSettings("VideoEditorTool", "App1Settings")
        self.last_video_dir = self.settings.value("lastVideoDir", str(Path.home() / "Videos"))
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30); layout.setSpacing(15) 
        title_label = QLabel("Chỉnh sửa Video Hàng loạt (Tua/Zoom/Lật)"); title_label.setObjectName("titleLabel"); layout.addWidget(title_label)

        grid_layout = QGridLayout(); grid_layout.setSpacing(15) 
        grid_layout.setColumnStretch(0, 1); grid_layout.setColumnStretch(1, 1)
        grid_layout.setRowStretch(0, 1); grid_layout.setRowStretch(1, 1)
        
        self.video_frame = self._create_video_player_widget(); grid_layout.addWidget(self.video_frame, 0, 0)
        self.list_controls_container = self._create_list_controls_widget(); grid_layout.addWidget(self.list_controls_container, 0, 1)
        self.settings_frame = self._create_settings_widget(); grid_layout.addWidget(self.settings_frame, 1, 0)
        self.action_status_frame = self._create_action_status_widget(); grid_layout.addWidget(self.action_status_frame, 1, 1)
        
        layout.addLayout(grid_layout); layout.addStretch() 
        self.reset_ui(); self.ensure_default_output_dir_exists()

    def _create_frame(self, title):
        frame = QFrame(); frame_layout = QVBoxLayout(frame); frame_layout.setContentsMargins(10, 10, 10, 10)
        if title:
             title_label = QLabel(title); title_label.setStyleSheet("color: #bfbfbf; font-weight: bold; margin-bottom: 5px;"); frame_layout.addWidget(title_label)
        return frame, frame_layout
        
    def _create_video_player_widget(self):
        video_frame, video_layout = self._create_frame(""); video_frame.setMinimumHeight(300); video_layout.setSpacing(5)
        if CAN_PLAY_VIDEO:
            self.video_widget = TransformableVideoWidget()
            self.video_widget.setStyleSheet("background-color: black; border-radius: 5px;")
            if self.media_player: 
                self.video_widget.setVideoOutput(self.media_player)
                self.media_player.positionChanged.connect(self.position_changed)
                self.media_player.durationChanged.connect(self.duration_changed)
                self.media_player.playbackStateChanged.connect(self.state_changed)
            video_layout.addWidget(self.video_widget, 1) 

            self.control_panel = QFrame(); self.control_panel.setStyleSheet("QFrame { background-color: transparent; border: none; padding: 0px; }")
            control_layout = QVBoxLayout(self.control_panel); control_layout.setContentsMargins(0, 0, 0, 0); control_layout.setSpacing(5)
            self.position_slider = QSlider(Qt.Orientation.Horizontal); self.position_slider.setRange(0, 0); self.position_slider.sliderMoved.connect(self.set_position); control_layout.addWidget(self.position_slider)
            
            playback_layout = QHBoxLayout(); self.play_button = QPushButton("▶️"); self.play_button.setObjectName("PlayPauseButton"); self.play_button.clicked.connect(self.toggle_play_pause); playback_layout.addWidget(self.play_button)
            self.time_label = QLabel("00:00 / 00:00"); self.time_label.setStyleSheet("color: #d6d6d6; font-size: 14px; font-weight: bold;"); playback_layout.addWidget(self.time_label)
            playback_layout.addStretch()
            
            self.volume_icon = QLabel("🔊"); self.volume_icon.setObjectName("VolumeIcon"); self.volume_icon.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)); self.volume_icon.mousePressEvent = lambda event: self.toggle_mute(event); playback_layout.addWidget(self.volume_icon)
            self.volume_slider = VolumeSlider(Qt.Orientation.Horizontal); self.volume_slider.setObjectName("VolumeSlider"); self.volume_slider.setRange(0, 100); self.volume_slider.setValue(100); self.volume_slider.setFixedWidth(80); self.volume_slider.valueChanged.connect(self.set_volume); playback_layout.addWidget(self.volume_slider)
            
            # Preview toggle button
            self.preview_toggle = QPushButton("👁️ Preview"); self.preview_toggle.setCheckable(True); self.preview_toggle.setStyleSheet("""
                QPushButton { 
                    background-color: #58a6ff; color: white; font-weight: bold; 
                    padding: 5px 10px; border-radius: 4px; font-size: 12px;
                }
                QPushButton:checked { background-color: #238636; }
                QPushButton:hover { background-color: #79c0ff; }
                QPushButton:checked:hover { background-color: #2ea043; }
            """); self.preview_toggle.clicked.connect(self.toggle_preview_mode); playback_layout.addWidget(self.preview_toggle)
            
            # Preview info label
            self.preview_info_label = QLabel(""); self.preview_info_label.setStyleSheet("""
                QLabel {
                    color: #58a6ff; 
                    font-weight: bold; 
                    font-size: 12px;
                    padding: 2px 5px;
                    background-color: rgba(88, 166, 255, 0.1);
                    border-radius: 3px;
                }
            """); self.preview_info_label.setVisible(False); playback_layout.addWidget(self.preview_info_label)
            
            # Fullscreen button (icon only)
            self.fullscreen_button = QPushButton("⛶"); self.fullscreen_button.setStyleSheet("""
                QPushButton { 
                    background-color: #6f42c1; color: white; font-weight: bold; 
                    padding: 5px 8px; border-radius: 4px; font-size: 14px;
                    min-width: 30px; max-width: 30px;
                }
                QPushButton:hover { background-color: #8b5cf6; }
            """); self.fullscreen_button.clicked.connect(self.toggle_fullscreen); playback_layout.addWidget(self.fullscreen_button)
            
            control_layout.addLayout(playback_layout); video_layout.addWidget(self.control_panel); self.control_panel.setVisible(False) 
        else:
            self.video_widget = QLabel("⚠️ Cần cài đặt QtMultimedia để xem trước."); self.video_widget.setAlignment(Qt.AlignmentFlag.AlignCenter); self.video_widget.setStyleSheet("background-color: #1a1a1a; padding: 20px; border-radius: 4px; color: #e74c3c; font-weight: bold;"); video_layout.addWidget(self.video_widget)
            self.play_button, self.position_slider, self.time_label = None, None, None
        return video_frame

    def _create_list_controls_widget(self):
        list_controls_container, list_controls_layout = self._create_frame("Video đầu vào (Chọn MP4):"); list_controls_container.setMinimumHeight(300)
        list_and_buttons_layout = QHBoxLayout(); list_and_buttons_layout.setSpacing(5)
        list_container = QVBoxLayout(); self.video_list_widget = QListWidget(); self.video_list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection); self.video_list_widget.itemSelectionChanged.connect(self._on_list_selection_changed); list_container.addWidget(self.video_list_widget, 1)
        self.total_duration_label = QLabel("Tổng thời lượng: 00:00:00"); self.total_duration_label.setStyleSheet("font-weight: bold; color: #2ecc71; margin-top: 5px;"); list_container.addWidget(self.total_duration_label)
        list_and_buttons_layout.addLayout(list_container, 1)

        sort_buttons_layout = QVBoxLayout(); sort_buttons_layout.setContentsMargins(0, 0, 0, 0); sort_buttons_layout.setSpacing(5); sort_buttons_layout.addStretch() 
        self.btn_add_video = QPushButton("➕"); self.btn_add_video.setFixedSize(30, 30); self.btn_add_video.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold)); self.btn_add_video.setStyleSheet(""" QPushButton { background-color: #28a745; color: white; border-radius: 4px; padding: 0px; } QPushButton:hover { background-color: #218838; } """); self.btn_add_video.clicked.connect(self.select_videos); sort_buttons_layout.addWidget(self.btn_add_video, alignment=Qt.AlignmentFlag.AlignCenter)
        self.btn_remove_video = QPushButton("➖"); self.btn_remove_video.setFixedSize(30, 30); self.btn_remove_video.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold)); self.btn_remove_video.setStyleSheet(""" QPushButton { background-color: #dc3545; color: white; border-radius: 4px; padding: 0px; } QPushButton:hover { background-color: #c82333; } """); self.btn_remove_video.clicked.connect(self.remove_selected_files); self.btn_remove_video.setEnabled(False); sort_buttons_layout.addWidget(self.btn_remove_video, alignment=Qt.AlignmentFlag.AlignCenter)
        sort_buttons_layout.addStretch(); list_and_buttons_layout.addLayout(sort_buttons_layout)
        list_controls_layout.addLayout(list_and_buttons_layout) 

        self.btn_clear_all_videos = QPushButton("❌ Xóa tất cả"); self.btn_clear_all_videos.setObjectName("RemoveAllButton"); self.btn_clear_all_videos.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold; padding: 5px;"); self.btn_clear_all_videos.clicked.connect(self.clear_all_videos); list_controls_layout.addWidget(self.btn_clear_all_videos) 
        return list_controls_container

    def _create_settings_widget(self):
        settings_frame, settings_layout = self._create_frame("Cài đặt Chỉnh sửa")
        speed_layout = QHBoxLayout(); speed_label_title = QLabel("Tốc độ (0.1x - 4.0x):"); speed_layout.addWidget(speed_label_title)
        self.spin_speed = QDoubleSpinBox(); self.spin_speed.setRange(0.1, 4.0); self.spin_speed.setSingleStep(0.1); self.spin_speed.setValue(self.settings.value("speedRatio", 1.0, float)); self.spin_speed.valueChanged.connect(self._on_speed_changed); speed_layout.addWidget(self.spin_speed); speed_layout.addStretch(); settings_layout.addLayout(speed_layout)
        zoom_layout = QHBoxLayout(); zoom_label_title = QLabel("Zoom (1.00x - 5.00x):"); zoom_layout.addWidget(zoom_label_title)
        self.spin_zoom = QDoubleSpinBox(); self.spin_zoom.setRange(1.00, 5.00); self.spin_zoom.setSingleStep(0.01); self.spin_zoom.setValue(self.settings.value("zoomFactor", 1.00, float)); self.spin_zoom.valueChanged.connect(self._on_zoom_changed); zoom_layout.addWidget(self.spin_zoom); zoom_layout.addStretch(); settings_layout.addLayout(zoom_layout)
        settings_layout.addSpacing(10)
        
        options_layout = QHBoxLayout(); self.chk_flip_video = QCheckBox("Lật gương (Horizontal Flip)"); self.chk_flip_video.setChecked(self.settings.value("flipVideo", False, bool)); self.chk_flip_video.stateChanged.connect(self._on_flip_changed); options_layout.addWidget(self.chk_flip_video)
        options_layout.addSpacing(20)
        self.chk_mute_original = QCheckBox("Tắt âm thanh gốc"); self.chk_mute_original.setChecked(self.settings.value("muteOriginal", False, bool)); self.chk_mute_original.stateChanged.connect(lambda state: self.settings.setValue("muteOriginal", bool(state))); options_layout.addWidget(self.chk_mute_original)
        options_layout.addStretch(); settings_layout.addLayout(options_layout)
        settings_layout.addStretch(); return settings_frame

    def _create_action_status_widget(self):
        action_status_frame, action_status_layout = self._create_frame("")
        output_dir_label = QLabel("Thư mục lưu video đầu ra:"); output_dir_label.setStyleSheet("font-weight: bold;"); action_status_layout.addWidget(output_dir_label)
        output_dir_layout = QHBoxLayout(); self.output_dir_line_edit = QLineEdit(); self.output_dir_line_edit.setReadOnly(True); output_dir_layout.addWidget(self.output_dir_line_edit)
        self.btn_select_output_dir = QPushButton("Lưu"); self.btn_select_output_dir.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 6px 12px;"); self.btn_select_output_dir.setFixedSize(80, 35); self.btn_select_output_dir.clicked.connect(self.select_output_directory); output_dir_layout.addWidget(self.btn_select_output_dir); action_status_layout.addLayout(output_dir_layout)
        action_status_layout.addSpacing(15)

        self.progress_bar = QProgressBar(); self.progress_bar.setValue(0); self.progress_bar.setFormat("Chờ xử lý..."); action_status_layout.addWidget(self.progress_bar)
        self.progress_message_label = QLabel(""); self.progress_message_label.setStyleSheet("color: #aaaaaa; font-size: 12px; margin-top: 5px;"); action_status_layout.addWidget(self.progress_message_label)
        action_status_layout.addStretch(1) 

        action_buttons_layout = QHBoxLayout()
        self.btn_run = QPushButton("🚀 Bắt Đầu Xử lý"); self.btn_run.setMinimumHeight(40); self.btn_run.clicked.connect(self.run_processing); self.btn_run.setEnabled(False); action_buttons_layout.addWidget(self.btn_run)
        self.btn_cancel = QPushButton("❌ Reset"); self.btn_cancel.setObjectName("ResetButton"); self.btn_cancel.setMinimumHeight(40); self.btn_cancel.clicked.connect(self.handle_cancel_or_reset); action_buttons_layout.addWidget(self.btn_cancel)
        action_status_layout.addLayout(action_buttons_layout)
        return action_status_frame
    
    def toggle_play_pause(self):
        if not self.media_player or not self.video_items: return
        state = self.media_player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState: self.media_player.pause()
        else: self.media_player.play()

    def state_changed(self, state):
        if self.play_button:
            self.play_button.setText("⏸️" if state == QMediaPlayer.PlaybackState.PlayingState else "▶️")
        
        # Fullscreen controls will be updated by timer, not by signal

    def position_changed(self, position):
        if self.position_slider and not self.position_slider.isSliderDown(): 
            self.position_slider.setValue(position)
        
        # Fullscreen controls will be updated by timer, not by signal
        
        if self.time_label and self.media_player:
            current_time = QTime(0,0,0).addMSecs(position)
            total_time = QTime(0,0,0).addMSecs(self.media_player.duration())
            total_time_str = total_time.toString('mm:ss') if self.media_player.duration() > 0 else "00:00"
            self.time_label.setText(f"{current_time.toString('mm:ss')} / {total_time_str}")

    def duration_changed(self, duration):
        if self.position_slider: 
            self.position_slider.setRange(0, duration)
        
        # Fullscreen controls will be updated by timer, not by signal
        if hasattr(self, 'control_panel'): self.control_panel.setVisible(duration > 0)
            
    def set_position(self, position):
        if self.media_player: 
            self.media_player.setPosition(position)
            # Force update the position slider to prevent conflicts
            if self.position_slider and not self.position_slider.isSliderDown():
                self.position_slider.setValue(position)

    def set_volume(self, value):
        if not CAN_PLAY_VIDEO or not self.audio_output: return
        if value > 0 and self.is_muted: self.is_muted = False
        self.audio_output.setVolume(value / 100.0)
        self._update_volume_icon(value)
        if not self.is_muted: self.last_volume = value
        
    def toggle_mute(self, event):
        if not CAN_PLAY_VIDEO or not self.audio_output or not isinstance(event, QMouseEvent): return
        if self.is_muted:
            target_volume = self.last_volume if self.last_volume > 0 else 50; self.is_muted = False
        else:
            if self.volume_slider.value() > 0: self.last_volume = self.volume_slider.value()
            target_volume = 0; self.is_muted = True
        self.volume_slider.setValue(target_volume); self.audio_output.setVolume(target_volume / 100.0); self._update_volume_icon(target_volume)

    def _update_volume_icon(self, volume_level):
        if self.is_muted or volume_level == 0: self.volume_icon.setText("🔇") 
        elif volume_level > 70: self.volume_icon.setText("🔊")
        elif volume_level > 0: self.volume_icon.setText("🔉")
        else: self.volume_icon.setText("🔈")
    
    def _update_list_and_duration(self):
        if self.media_player: self.media_player.stop()
        self.video_list_widget.clear(); total_seconds = 0
        path_list = list(self.video_items.keys())
        for path in path_list:
            duration_sec = get_video_duration(path)
            self.video_items[path] = duration_sec; total_seconds += duration_sec
            QListWidgetItem(f"[{format_duration(duration_sec)}] {Path(path).name}", self.video_list_widget)
        self.total_duration_label.setText(f"Tổng thời lượng: {format_duration(total_seconds)}")
        self._update_run_button_state()
        if self.video_list_widget.count() > 0: self.video_list_widget.setCurrentRow(0)
        elif self.media_player: self.control_panel.setVisible(False)
            
    def _on_list_selection_changed(self):
        selected_items = self.video_list_widget.selectedItems()
        is_running = self.worker_thread and self.worker_thread.isRunning()
        self.btn_remove_video.setEnabled(bool(selected_items) and not is_running)
        if not selected_items:
            if self.media_player: self.media_player.stop()
            self._disable_preview_mode()
            return
        row = self.video_list_widget.row(selected_items[0])
        if self.media_player and 0 <= row < len(self.video_items):
            selected_path = list(self.video_items.keys())[row]
            if self.media_player.source() != QUrl.fromLocalFile(selected_path): 
                self.media_player.setSource(QUrl.fromLocalFile(selected_path))
                # Wait a moment for the source to be set
                QTimer.singleShot(100, lambda: self.media_player.play())
            else:
                self.media_player.play()
            # Auto-enable preview mode when video is selected
            self.preview_toggle.setChecked(True)
            self._enable_preview_mode()
            self.update_preview()
            
    def select_videos(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Chọn video MP4", self.last_video_dir, "Video (*.mp4)")
        if files:
            is_new_file_added = any(file not in self.video_items for file in files)
            for file in files: self.video_items[file] = None 
            if is_new_file_added:
                self.last_video_dir = os.path.dirname(files[0])
                self.settings.setValue("lastVideoDir", self.last_video_dir); self._update_list_and_duration()
    
    def remove_selected_files(self):
        selected_items = self.video_list_widget.selectedItems()
        if not selected_items: return
        if self.media_player: self.media_player.stop()
        rows_to_remove = sorted([self.video_list_widget.row(item) for item in selected_items], reverse=True)
        paths_to_remove = [list(self.video_items.keys())[row] for row in rows_to_remove]
        for path in paths_to_remove:
            if path in self.video_items: del self.video_items[path]
        self._update_list_and_duration()

    def clear_all_videos(self):
        if self.video_items and QMessageBox.question(self, "Xác nhận", "Xóa tất cả video?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            if self.media_player: self.media_player.stop()
            self.video_items.clear(); self.video_list_widget.clear(); self.total_duration_label.setText("Tổng thời lượng: 00:00:00")
            self._update_run_button_state(); self.control_panel.setVisible(False)
        
    def select_output_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu video đầu ra", self.settings.value("outputDir", str(Path.home())))
        if directory: self.output_dir = directory; self.output_dir_line_edit.setText(self.output_dir); self.settings.setValue("outputDir", self.output_dir); self._update_run_button_state()
            
    def ensure_default_output_dir_exists(self):
        default_dir = Path.home() / "Videos" / "VideoEditorTool_App1"
        saved_dir = self.settings.value("outputDir", str(default_dir)); self.output_dir = saved_dir; self.output_dir_line_edit.setText(self.output_dir)
        if not Path(saved_dir).exists():
            try: Path(saved_dir).mkdir(parents=True, exist_ok=True)
            except Exception: self.output_dir = str(Path.home() / "Videos"); self.output_dir_line_edit.setText(self.output_dir)
        
    def _check_ffmpeg(self): return FFMPEG_EXE.exists() or shutil.which("ffmpeg")
    
    def _set_controls_enabled(self, enabled):
        for widget in [self.btn_add_video, self.btn_select_output_dir, self.spin_speed, self.spin_zoom, self.chk_flip_video, self.chk_mute_original, self.btn_clear_all_videos, self.video_list_widget]:
            widget.setEnabled(enabled)
        self.btn_remove_video.setEnabled(enabled and bool(self.video_list_widget.selectedItems())) 
        if self.control_panel: self.control_panel.setEnabled(enabled and bool(self.video_items))
        
    def _update_run_button_state(self):
        is_running = self.worker_thread and self.worker_thread.isRunning()
        can_run = bool(self.video_items) and bool(self.output_dir) and self._check_ffmpeg() and not is_running
        self.btn_run.setEnabled(can_run)
        self.btn_cancel.setText("❌ Hủy" if is_running else "❌ Reset")
        self._set_controls_enabled(not is_running)

    def reset_ui(self):
        if self.media_player: self.media_player.stop() 
        self.video_items.clear(); self.video_list_widget.clear()
        self.spin_speed.setValue(self.settings.value("speedRatio", 1.0, float)); self.spin_zoom.setValue(self.settings.value("zoomFactor", 1.00, float))
        self.chk_flip_video.setChecked(self.settings.value("flipVideo", False, bool)); self.chk_mute_original.setChecked(self.settings.value("muteOriginal", False, bool))
        if self.volume_slider: self.volume_slider.setValue(100)
        self.progress_bar.setValue(0); self.progress_bar.setFormat("Chờ xử lý..."); self.progress_message_label.setText("")
        self.worker_thread = None; self.total_duration_label.setText("Tổng thời lượng: 00:00:00")
        if self.control_panel: self.control_panel.setVisible(False)
        self._update_run_button_state()
        
    def run_processing(self):
        if not self.btn_run.isEnabled(): return
        self.progress_bar.setValue(0); self.progress_bar.setFormat("Đang chuẩn bị...")
        
        for i in range(self.video_list_widget.count()):
            item = self.video_list_widget.item(i); item_text = item.text()
            file_name = item_text.split('] ', 1)[-1].split(' - ')[0].strip() 
            duration_part = item_text.split('] ')[0] + ']'
            item.setText(f"{duration_part} {file_name} - ⏳ Chờ..."); item.setForeground(Qt.GlobalColor.white); item.setToolTip("")
        
        self.setCursor(Qt.CursorShape.WaitCursor); self.progress_message_label.setText(f"Đang chuẩn bị {len(self.video_items)} video...")
        
        video_tasks = [{'path': path, 'output_dir': self.output_dir, 'speed_ratio': self.spin_speed.value(), 'mute_original': self.chk_mute_original.isChecked(), 'flip_video': self.chk_flip_video.isChecked(), 'zoom_factor': self.spin_zoom.value()} for path in self.video_items.keys()]
        max_workers = min(max(1, (os.cpu_count() or 1) // 2), 4)
        
        self.worker_thread = VideoProcessingWorker(video_tasks, max_workers)
        self.worker_thread.progress_update.connect(self.on_progress_update); self.worker_thread.video_finished.connect(self.on_video_finished)
        self.worker_thread.all_videos_finished.connect(self.on_all_videos_finished); self.worker_thread.processing_cancelled.connect(self.on_processing_cancelled)
        self.worker_thread.start(); self._update_run_button_state()
        
    def on_progress_update(self, overall_percentage, message):
        self.progress_bar.setValue(overall_percentage); self.progress_bar.setFormat(f"{overall_percentage}% - {message.split('...')[0]}"); self.progress_message_label.setText("") 
        
    def on_video_finished(self, original_path, success, message):
        base_name = os.path.basename(original_path)
        status_text, color = ("✅ Hoàn thành", Qt.GlobalColor.darkGreen) if success else ("❌ Lỗi", Qt.GlobalColor.red)
        for i in range(self.video_list_widget.count()):
            item = self.video_list_widget.item(i); item_text = item.text()
            try:
                file_name_part = item_text.split('] ', 1)[-1].split(' - ')[0].strip()
                if base_name == file_name_part:
                    duration_part = item_text.split('] ')[0] + ']'
                    item.setText(f"{duration_part} {file_name_part} - {status_text}"); item.setForeground(color) 
                    if not success: item.setToolTip(message)
                    break
            except IndexError: continue

    def on_all_videos_finished(self, success_count, error_count, output_dir):
        self.setCursor(Qt.CursorShape.ArrowCursor); self.worker_thread = None
        final_message = f"Hoàn tất! {success_count} thành công, {error_count} thất bại."
        self.progress_message_label.setText(""); self.progress_bar.setValue(100); self.progress_bar.setFormat("Hoàn thành!")
        QMessageBox.information(self, "Hoàn tất", f"{final_message}\nLưu tại:\n{output_dir}")
        try: os.startfile(output_dir)
        except AttributeError: subprocess.Popen(['xdg-open', output_dir])
        self._update_run_button_state()
        
    def on_processing_cancelled(self):
        self.setCursor(Qt.CursorShape.ArrowCursor); self.worker_thread = None
        self.progress_message_label.setText(""); self.progress_bar.setFormat("Tác vụ đã bị hủy.")
        QMessageBox.information(self, "Đã hủy", "Quá trình xử lý đã dừng.")
        self._update_run_button_state()
        
    def handle_cancel_or_reset(self):
        if self.worker_thread and self.worker_thread.isRunning():
            if QMessageBox.question(self, "Xác nhận", "Dừng quá trình xử lý?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                self.worker_thread.cancel()
        else: self.reset_ui()
    
    def set_theme(self, theme_name):
        """Set theme for this plugin"""
        if theme_manager.set_theme(theme_name):
            self.setStyleSheet(get_standard_stylesheet())
            return True
        return False
    
    def update_preview(self):
        """Update video preview with current settings"""
        if not CAN_PLAY_VIDEO or not self.media_player or not self.video_items:
            return
            
        # Get current settings
        zoom_factor = self.spin_zoom.value()
        flip_video = self.chk_flip_video.isChecked()
        speed_ratio = self.spin_speed.value()
        
        # Update preview state
        self.preview_zoom = zoom_factor
        self.preview_flip = flip_video
        self.preview_speed = speed_ratio
        
        # Apply visual effects to video widget
        self._apply_preview_effects()
    
    def _apply_preview_effects(self):
        """Apply real-time visual effects to the video widget for preview"""
        if not hasattr(self, 'video_widget') or not self.video_widget:
            return
            
        # Apply real transforms using professional widget
        if hasattr(self.video_widget, 'setPreviewTransform'):
            self.video_widget.setPreviewTransform(
                self.preview_zoom, 
                self.preview_flip, 
                self.preview_speed
            )
        
        # Apply speed to media player for real-time preview
        if hasattr(self, 'media_player') and self.media_player:
            self.media_player.setPlaybackRate(self.preview_speed)
        
        # Create preview info text
        preview_info = []
        if self.preview_zoom != 1.0:
            preview_info.append(f"Zoom: {self.preview_zoom:.2f}x")
        if self.preview_flip:
            preview_info.append("Flip: ON")
        if self.preview_speed != 1.0:
            preview_info.append(f"Speed: {self.preview_speed:.2f}x")
        
        # Apply professional preview styling
        if preview_info:
            info_text = " | ".join(preview_info)
            self.video_widget.setStyleSheet(f"""
                QGraphicsView {{
                    background-color: black; 
                    border-radius: 5px;
                    border: 3px solid #58a6ff;
                }}
            """)
            # Show preview info in label
            if hasattr(self, 'preview_info_label'):
                self.preview_info_label.setText(f"🎬 Preview: {info_text}")
                self.preview_info_label.setVisible(True)
                self.preview_info_label.setStyleSheet("""
                    QLabel {
                        background-color: rgba(88, 166, 255, 0.9);
                        color: white;
                        padding: 5px 10px;
                        border-radius: 3px;
                        font-weight: bold;
                        font-size: 12px;
                    }
                """)
            self.video_widget.setToolTip(f"🎬 Preview Mode: {info_text}")
        else:
            self.video_widget.setStyleSheet("""
                QGraphicsView {
                    background-color: black; 
                    border-radius: 5px;
                    border: 2px solid #333;
                }
            """)
            if hasattr(self, 'preview_info_label'):
                self.preview_info_label.setVisible(False)
            self.video_widget.setToolTip("")
    
    def _enable_preview_mode(self):
        """Enable professional preview mode"""
        self.is_preview_mode = True
        if hasattr(self, 'video_widget') and self.video_widget:
            self.video_widget.setStyleSheet("""
                QGraphicsView {
                    background-color: black; 
                    border-radius: 5px;
                    border: 3px solid #58a6ff;
                }
            """)
            self.video_widget.setToolTip("🎬 Preview Mode: Active")
        if hasattr(self, 'preview_toggle'):
            self.preview_toggle.setChecked(True)
            self.preview_toggle.setText("🎬 Preview ON")
            self.preview_toggle.setStyleSheet("""
                QPushButton { 
                    background-color: #238636; color: white; font-weight: bold; 
                    padding: 5px 10px; border-radius: 4px; font-size: 12px;
                }
                QPushButton:hover { background-color: #2ea043; }
            """)
        if hasattr(self, 'preview_info_label'):
            self.preview_info_label.setVisible(True)
        # Apply current preview settings
        self.update_preview()
    
    def _disable_preview_mode(self):
        """Disable preview mode and reset transforms"""
        self.is_preview_mode = False
        if hasattr(self, 'video_widget') and self.video_widget:
            self.video_widget.setStyleSheet("""
                QGraphicsView {
                    background-color: black; 
                    border-radius: 5px;
                    border: 2px solid #333;
                }
            """)
        if hasattr(self, 'preview_toggle'):
            self.preview_toggle.setChecked(False)
            self.preview_toggle.setText("👁️ Preview")
            self.preview_toggle.setStyleSheet("""
                QPushButton { 
                    background-color: #58a6ff; color: white; font-weight: bold; 
                    padding: 5px 10px; border-radius: 4px; font-size: 12px;
                }
                QPushButton:hover { background-color: #79c0ff; }
            """)
        if hasattr(self, 'preview_info_label'):
            self.preview_info_label.setVisible(False)
        # Reset video transform and speed
        if hasattr(self.video_widget, 'resetTransform'):
            self.video_widget.resetTransform()
        
        # Reset media player speed to normal
        if hasattr(self, 'media_player') and self.media_player:
            self.media_player.setPlaybackRate(1.0)
    
    def _on_speed_changed(self, value):
        """Handle speed change with real-time preview"""
        self.settings.setValue("speedRatio", value)
        
        # Update preview speed immediately
        self.preview_speed = value
        
        # Apply speed to media player for real-time preview
        if hasattr(self, 'media_player') and self.media_player and self.is_preview_mode:
            self.media_player.setPlaybackRate(value)
        
        # Update preview effects
        self.update_preview()
    
    def _on_zoom_changed(self, value):
        """Handle zoom change with real-time preview"""
        self.settings.setValue("zoomFactor", value)
        
        # Update preview zoom immediately
        self.preview_zoom = value
        
        # Apply zoom to video widget for real-time preview
        if hasattr(self, 'video_widget') and self.video_widget and self.is_preview_mode:
            self.video_widget.setPreviewTransform(
                self.preview_zoom, 
                self.preview_flip, 
                self.preview_speed
            )
        
        # Update preview effects
        self.update_preview()
    
    def _on_flip_changed(self, state):
        """Handle flip change with real-time preview"""
        self.settings.setValue("flipVideo", bool(state))
        
        # Update preview flip immediately
        self.preview_flip = bool(state)
        
        # Apply flip to video widget for real-time preview
        if hasattr(self, 'video_widget') and self.video_widget and self.is_preview_mode:
            self.video_widget.setPreviewTransform(
                self.preview_zoom, 
                self.preview_flip, 
                self.preview_speed
            )
        
        # Update preview effects
        self.update_preview()
    
    def toggle_preview_mode(self):
        """Toggle preview mode on/off"""
        if self.preview_toggle.isChecked():
            self._enable_preview_mode()
            self.update_preview()
        else:
            self._disable_preview_mode()
    
    def toggle_fullscreen(self):
        """Toggle fullscreen mode for video preview"""
        if not hasattr(self, 'video_widget') or not self.video_widget:
            return
            
        if not self.is_fullscreen:
            # Enter fullscreen mode
            self.original_geometry = self.video_widget.geometry()
            
            # Create fullscreen window
            self.fullscreen_window = QWidget()
            self.fullscreen_window.setWindowTitle("Video Preview - Fullscreen")
            self.fullscreen_window.setStyleSheet("background-color: black;")
            self.fullscreen_window.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
            
            # Create layout for fullscreen window
            fullscreen_layout = QVBoxLayout(self.fullscreen_window)
            fullscreen_layout.setContentsMargins(0, 0, 0, 0)
            
            # Create a new video widget for fullscreen
            self.fullscreen_video_widget = TransformableVideoWidget()
            self.fullscreen_video_widget.setStyleSheet("background-color: black;")
            
            # Set video output to fullscreen widget
            if self.media_player:
                self.fullscreen_video_widget.setVideoOutput(self.media_player)
                # Apply current preview settings
                self.fullscreen_video_widget.setPreviewTransform(
                    self.preview_zoom, 
                    self.preview_flip, 
                    self.preview_speed
                )
            
            fullscreen_layout.addWidget(self.fullscreen_video_widget)
            
            # Create control panel for fullscreen
            self.fullscreen_control_panel = QFrame()
            self.fullscreen_control_panel.setStyleSheet("""
                QFrame { 
                    background-color: rgba(0, 0, 0, 150); 
                    border: none; 
                    padding: 10px; 
                }
            """)
            fullscreen_control_layout = QVBoxLayout(self.fullscreen_control_panel)
            fullscreen_control_layout.setContentsMargins(20, 10, 20, 10)
            
            # Progress bar for fullscreen
            self.fullscreen_position_slider = QSlider(Qt.Orientation.Horizontal)
            self.fullscreen_position_slider.setRange(0, 0)
            self.fullscreen_position_slider.sliderMoved.connect(self._fullscreen_set_position)
            self.fullscreen_position_slider.setStyleSheet("""
                QSlider::groove:horizontal {
                    border: 1px solid #999999;
                    height: 8px;
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #B1B1B1, stop:1 #c4c4c4);
                    margin: 2px 0;
                    border-radius: 4px;
                }
                QSlider::handle:horizontal {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #b4b4b4, stop:1 #8f8f8f);
                    border: 1px solid #5c5c5c;
                    width: 18px;
                    margin: -2px 0;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #d4d4d4, stop:1 #8f8f8f);
                }
            """)
            fullscreen_control_layout.addWidget(self.fullscreen_position_slider)
            
            # Control buttons layout
            fullscreen_buttons_layout = QHBoxLayout()
            
            # Play/Pause button
            self.fullscreen_play_button = QPushButton("▶️")
            self.fullscreen_play_button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.2);
                    color: white;
                    font-weight: bold;
                    padding: 8px 12px;
                    border-radius: 5px;
                    font-size: 16px;
                    min-width: 40px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.3);
                }
            """)
            self.fullscreen_play_button.clicked.connect(self.toggle_play_pause)
            fullscreen_buttons_layout.addWidget(self.fullscreen_play_button)
            
            # Time label
            self.fullscreen_time_label = QLabel("00:00 / 00:00")
            self.fullscreen_time_label.setStyleSheet("""
                color: white; 
                font-size: 14px; 
                font-weight: bold;
                padding: 0 10px;
            """)
            fullscreen_buttons_layout.addWidget(self.fullscreen_time_label)
            
            fullscreen_buttons_layout.addStretch()
            
            # Volume control
            self.fullscreen_volume_icon = QLabel("🔊")
            self.fullscreen_volume_icon.setStyleSheet("color: white; font-size: 16px;")
            self.fullscreen_volume_icon.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.fullscreen_volume_icon.mousePressEvent = lambda event: self.toggle_mute(event)
            fullscreen_buttons_layout.addWidget(self.fullscreen_volume_icon)
            
            self.fullscreen_volume_slider = VolumeSlider(Qt.Orientation.Horizontal)
            self.fullscreen_volume_slider.setRange(0, 100)
            self.fullscreen_volume_slider.setValue(100)
            self.fullscreen_volume_slider.setFixedWidth(100)
            self.fullscreen_volume_slider.valueChanged.connect(self.set_volume)
            self.fullscreen_volume_slider.setStyleSheet("""
                QSlider::groove:horizontal {
                    border: 1px solid #999999;
                    height: 6px;
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #B1B1B1, stop:1 #c4c4c4);
                    margin: 2px 0;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #b4b4b4, stop:1 #8f8f8f);
                    border: 1px solid #5c5c5c;
                    width: 16px;
                    margin: -2px 0;
                    border-radius: 3px;
                }
            """)
            fullscreen_buttons_layout.addWidget(self.fullscreen_volume_slider)
            
            # Exit fullscreen button
            self.fullscreen_exit_button = QPushButton("❌")
            self.fullscreen_exit_button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(220, 53, 69, 0.8);
                    color: white;
                    font-weight: bold;
                    padding: 8px 12px;
                    border-radius: 5px;
                    font-size: 16px;
                    min-width: 40px;
                }
                QPushButton:hover {
                    background-color: rgba(220, 53, 69, 1.0);
                }
            """)
            self.fullscreen_exit_button.clicked.connect(self.toggle_fullscreen)
            fullscreen_buttons_layout.addWidget(self.fullscreen_exit_button)
            
            fullscreen_control_layout.addLayout(fullscreen_buttons_layout)
            fullscreen_layout.addWidget(self.fullscreen_control_panel)
            
            # Show fullscreen window
            self.fullscreen_window.showFullScreen()
            self.is_fullscreen = True
            
            # Update button text
            self.fullscreen_button.setText("📱")
            self.fullscreen_button.setStyleSheet("""
                QPushButton { 
                    background-color: #dc3545; color: white; font-weight: bold; 
                    padding: 5px 8px; border-radius: 4px; font-size: 14px;
                    min-width: 30px; max-width: 30px;
                }
                QPushButton:hover { background-color: #c82333; }
            """)
            
            # Start fullscreen timer for all updates
            self.fullscreen_timer.start()
            
        else:
            # Exit fullscreen mode
            # Stop fullscreen timer
            self.fullscreen_timer.stop()
            
            if hasattr(self, 'fullscreen_position_slider') and self.fullscreen_position_slider:
                try:
                    self.fullscreen_position_slider.sliderMoved.disconnect()
                except:
                    pass
            
            if hasattr(self, 'fullscreen_window'):
                self.fullscreen_window.close()
                delattr(self, 'fullscreen_window')
            if hasattr(self, 'fullscreen_video_widget'):
                delattr(self, 'fullscreen_video_widget')
            if hasattr(self, 'fullscreen_control_panel'):
                delattr(self, 'fullscreen_control_panel')
            if hasattr(self, 'fullscreen_position_slider'):
                delattr(self, 'fullscreen_position_slider')
            if hasattr(self, 'fullscreen_play_button'):
                delattr(self, 'fullscreen_play_button')
            if hasattr(self, 'fullscreen_time_label'):
                delattr(self, 'fullscreen_time_label')
            if hasattr(self, 'fullscreen_volume_icon'):
                delattr(self, 'fullscreen_volume_icon')
            if hasattr(self, 'fullscreen_volume_slider'):
                delattr(self, 'fullscreen_volume_slider')
            if hasattr(self, 'fullscreen_exit_button'):
                delattr(self, 'fullscreen_exit_button')
            
            # Restore original video widget
            if self.media_player and hasattr(self, 'video_widget'):
                self.video_widget.setVideoOutput(self.media_player)
                # Reapply current preview settings
                self.video_widget.setPreviewTransform(
                    self.preview_zoom, 
                    self.preview_flip, 
                    self.preview_speed
                )
            
            self.is_fullscreen = False
            
            # Update button text
            self.fullscreen_button.setText("⛶")
            self.fullscreen_button.setStyleSheet("""
                QPushButton { 
                    background-color: #6f42c1; color: white; font-weight: bold; 
                    padding: 5px 8px; border-radius: 4px; font-size: 14px;
                    min-width: 30px; max-width: 30px;
                }
                QPushButton:hover { background-color: #8b5cf6; }
            """)
    
    
    def _update_all_fullscreen_controls(self):
        """Update all fullscreen controls using timer"""
        if not self.is_fullscreen or not self.media_player:
            return
            
        try:
            # Update position slider
            if hasattr(self, 'fullscreen_position_slider') and self.fullscreen_position_slider:
                position = self.media_player.position()
                if not self.fullscreen_position_slider.isSliderDown() and not self._updating_fullscreen_slider:
                    self.fullscreen_position_slider.setValue(position)
            
            # Update time label
            if hasattr(self, 'fullscreen_time_label') and self.fullscreen_time_label:
                position = self.media_player.position()
                duration = self.media_player.duration()
                
                position_time = self._format_time(position)
                duration_time = self._format_time(duration)
                
                self.fullscreen_time_label.setText(f"{position_time} / {duration_time}")
            
            # Update play button
            if hasattr(self, 'fullscreen_play_button') and self.fullscreen_play_button:
                state = self.media_player.playbackState()
                if state == QMediaPlayer.PlaybackState.PlayingState:
                    self.fullscreen_play_button.setText("⏸️")
                else:
                    self.fullscreen_play_button.setText("▶️")
                    
        except RuntimeError:
            # Widget has been deleted, ignore
            pass
    
    def _format_time(self, milliseconds):
        """Format milliseconds to MM:SS format"""
        seconds = milliseconds // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"
    
    def _fullscreen_set_position(self, position):
        """Set position for fullscreen mode"""
        if self.media_player and self.is_fullscreen:
            self._updating_fullscreen_slider = True
            self.media_player.setPosition(position)
            # Update the main position slider as well
            if self.position_slider and not self.position_slider.isSliderDown():
                self.position_slider.setValue(position)
            self._updating_fullscreen_slider = False
    
    def cleanup_resources(self):
        """Clean up resources to prevent memory leaks"""
        if self._is_destroyed:
            return
        
        try:
            # Exit fullscreen mode if active
            if self.is_fullscreen:
                self.toggle_fullscreen()
            
            # Stop and cleanup media player
            if hasattr(self, 'media_player') and self.media_player:
                self.media_player.stop()
                self.media_player.setSource(QUrl())
            
            # Cancel and cleanup worker thread
            if self.worker_thread and self.worker_thread.isRunning():
                self.worker_thread.cancel()
                self.worker_thread.wait(5000)  # Wait up to 5 seconds
                if self.worker_thread.isRunning():
                    self.worker_thread.terminate()
                    self.worker_thread.wait(1000)
            
            # Clear video items
            self.video_items.clear()
            
            self._is_destroyed = True
        except Exception:
            pass
    
    def closeEvent(self, event):
        """Handle widget close event"""
        self.cleanup_resources()
        super().closeEvent(event)
