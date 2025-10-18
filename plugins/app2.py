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

try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaFormat
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    CAN_PLAY_VIDEO = True
except ImportError:
    CAN_PLAY_VIDEO = False

# Import theme manager
from theme_manager import PluginThemeManager

class VolumeSlider(QSlider):
    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            if self.orientation() == Qt.Orientation.Horizontal:
                value = self.minimum() + (self.maximum() - self.minimum()) * event.pos().x() / self.width()
            else:
                value = self.maximum() - (self.maximum() - self.minimum()) * event.pos().y() / self.height()
            self.setValue(int(value))

class FFmpegWorker(QThread):
    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, videos, audio, total_minutes, output_dir, mute_original, audio_volume_percent):
        super().__init__()
        self.videos = videos
        self.audio = audio
        self.total_minutes = total_minutes
        self.output_dir = output_dir
        self.mute_original = mute_original
        self.audio_volume_percent = audio_volume_percent
        self.process = None
        self._is_cancelled = False
        
        if getattr(sys, 'frozen', False):
            BASE_DIR = Path(sys.executable).parent
        else:
            BASE_DIR = Path(__file__).resolve().parent.parent

        self.FFMPEG_EXE = BASE_DIR / "ffmpeg.exe"
        self.FFPROBE_EXE = BASE_DIR / "ffprobe.exe"
        self.ffmpeg_cmd_base = [str(self.FFMPEG_EXE)] if self.FFMPEG_EXE.exists() else ["ffmpeg"]
        self.ffprobe_cmd_base = [str(self.FFPROBE_EXE)] if self.FFPROBE_EXE.exists() else ["ffprobe"]

    def cancel(self):
        self._is_cancelled = True
        if self.process and self.process.poll() is None:
            try:
                if self.process.stdin:
                    self.process.stdin.write('q\n')
                    self.process.stdin.flush()
                if self.process.wait(timeout=2) is None:
                    self.process.terminate()
            except (IOError, BrokenPipeError, subprocess.TimeoutExpired):
                self.process.terminate()
            except Exception:
                pass

    def _get_audio_duration(self, audio_path):
        if not self.FFPROBE_EXE.exists(): return 0.0
        try:
            cmd = self.ffprobe_cmd_base + ["-v", "quiet", "-print_format", "json", "-show_format", str(audio_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            audio_info = json.loads(result.stdout)
            return float(audio_info['format']['duration'])
        except Exception: return 0.0

    def _run_ffmpeg_command(self, command, step_name, progress_value):
        if self._is_cancelled: return False
        self.progress_signal.emit(progress_value, f"Đang {step_name}...")
        try:
            result = subprocess.run(
                command, check=True, capture_output=True, text=True,
                encoding='utf-8', errors='ignore', creationflags=subprocess.CREATE_NO_WINDOW
            )
            return True
        except subprocess.CalledProcessError as e:
            self.error_signal.emit(f"Lỗi FFmpeg ở bước '{step_name}':\n{' '.join(e.cmd)}\n\n{e.stderr}")
            return False

    def run(self):
        if not self.videos or not self.audio:
            self.error_signal.emit("Lỗi nội bộ: Không có video hoặc audio được chọn để xử lý.")
            return

        tmpdir_path = None
        if not self.FFMPEG_EXE.exists() or not self.FFPROBE_EXE.exists():
            self.error_signal.emit("Lỗi: Không tìm thấy FFmpeg hoặc FFprobe.")
            return

        try:
            tmpdir = tempfile.mkdtemp(prefix="video_editor_tmp_")
            tmpdir_path = Path(tmpdir)
            target_dur_seconds = self.total_minutes * 60

            self.progress_signal.emit(2, "Đang chuẩn bị file nhạc...")
            safe_audio_path = tmpdir_path / "safe_audio.mp3"
            shutil.copy(self.audio, safe_audio_path)

            audio_duration_sec = self._get_audio_duration(safe_audio_path)
            if audio_duration_sec == 0:
                raise Exception("Không thể đọc thời lượng của file nhạc.")

            self.progress_signal.emit(10, "Đang ghép video gốc...")
            concatenated_video_path = tmpdir_path / "concatenated.mp4"
            
            video_list_path = tmpdir_path / "video_list_input.txt"
            with open(video_list_path, "w", encoding='utf-8') as f:
                for p in self.videos:
                    clean_path = Path(p).resolve().as_posix()
                    escaped_path = clean_path.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")

            concat_cmd = self.ffmpeg_cmd_base + [
                "-f", "concat", "-safe", "0", "-i", str(video_list_path),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                str(concatenated_video_path), "-y"
            ]
            if not self._run_ffmpeg_command(concat_cmd, "ghép các video gốc", 20): return

            self.progress_signal.emit(25, "Đang lặp video nền...")
            looped_video_path = tmpdir_path / "looped_video.mp4"
            
            concat_video_duration = self._get_audio_duration(concatenated_video_path)
            if concat_video_duration == 0:
                 raise Exception("Không thể đọc thời lượng của video đã ghép.")
                 
            num_loops_required = math.ceil(audio_duration_sec / concat_video_duration)
            
            loop_list_path = tmpdir_path / "video_loop_list.txt"
            with open(loop_list_path, "w", encoding='utf-8') as f:
                for _ in range(max(1, int(num_loops_required))):
                    clean_path = concatenated_video_path.resolve().as_posix()
                    escaped_path = clean_path.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")
            
            loop_video_cmd = self.ffmpeg_cmd_base + [
                "-f", "concat", "-safe", "0", "-i", str(loop_list_path),
                "-t", str(audio_duration_sec),
                "-c", "copy", str(looped_video_path), "-y"
            ]
            if not self._run_ffmpeg_command(loop_video_cmd, "lặp video theo nhạc", 35): return

            base_output_path = tmpdir_path / "base_output.mp4"
            volume_multiplier = self.audio_volume_percent / 100.0
            
            self.progress_signal.emit(40, "Đang trộn/thay thế âm thanh...")
            
            merge_base_cmd = self.ffmpeg_cmd_base + [
                "-i", str(looped_video_path), 
                "-i", str(safe_audio_path)
            ]
            
            if self.mute_original:
                filter_complex = f"[1:a]volume={volume_multiplier}[aout]"
                merge_base_cmd += [
                    "-filter_complex", filter_complex,
                    "-map", "0:v:0", "-map", "[aout]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", str(base_output_path), "-y"
                ]
            else:
                filter_complex = f"[0:a]volume=1.0[a0];[1:a]volume={volume_multiplier}[a1];[a0][a1]amix=inputs=2:duration=longest[aout]"
                merge_base_cmd += [
                    "-filter_complex", filter_complex,
                    "-map", "0:v:0", "-map", "[aout]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", str(base_output_path), "-y"
                ]

            if not self._run_ffmpeg_command(merge_base_cmd, "ghép nhạc vào video nền", 55): return

            base_name = Path(self.videos[0]).stem
            final_output_path = self.output_dir / f"{base_name}_nhacdai_{self.total_minutes}m.mp4"
            counter = 1
            while final_output_path.exists():
                final_output_path = self.output_dir / f"{base_name}_nhacdai_{self.total_minutes}m({counter}).mp4"
                counter += 1

            duration_of_base_output = self._get_audio_duration(base_output_path)
            if duration_of_base_output == 0:
                 raise Exception("Lỗi: Không thể đọc thời lượng của video đã trộn âm thanh.")
                 
            num_loops_final = math.ceil(target_dur_seconds / duration_of_base_output)
            
            final_loop_list_path = tmpdir_path / "final_loop_list.txt"
            with open(final_loop_list_path, "w", encoding='utf-8') as f:
                for _ in range(max(1, int(num_loops_final))):
                    clean_path = base_output_path.resolve().as_posix()
                    escaped_path = clean_path.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")
                    
            long_looped_video_path = tmpdir_path / "long_looped_final.mp4"
            concat_loop_cmd = self.ffmpeg_cmd_base + [
                "-f", "concat", "-safe", "0", "-i", str(final_loop_list_path),
                "-c", "copy", str(long_looped_video_path), "-y"
            ]
            if not self._run_ffmpeg_command(concat_loop_cmd, "tạo video lặp cuối cùng", 70): return
            
            trim_cmd = self.ffmpeg_cmd_base + [
                "-i", str(long_looped_video_path), 
                "-t", str(target_dur_seconds),
                "-c", "copy", str(final_output_path), "-y"
            ]
            self._run_ffmpeg_with_progress(trim_cmd, target_dur_seconds, 75, 99, "Đang cắt video ra độ dài cuối cùng...")
            
            if not self._is_cancelled:
                self.progress_signal.emit(100, "Hoàn tất!")
                self.finished_signal.emit(str(final_output_path))

        except Exception as e:
            if not self._is_cancelled:
                error_type = type(e).__name__
                self.error_signal.emit(f"Đã xảy ra lỗi không xác định ({error_type}):\n{e}")
        finally:
            self.process = None
            if tmpdir_path and tmpdir_path.exists():
                shutil.rmtree(tmpdir_path, ignore_errors=True)
    
    def _run_ffmpeg_with_progress(self, command, total_duration, start_progress, end_progress, message):
        if self._is_cancelled: return
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, encoding='utf-8', errors='ignore',
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        time_regex = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.\d{2}")
        
        for line in self.process.stderr:
            if self._is_cancelled: break
            match = time_regex.search(line)
            if match:
                h, m, s = map(int, match.groups())
                current_seconds = h * 3600 + m * 60 + s
                if total_duration > 0:
                    step_progress = current_seconds / total_duration
                    overall_progress = int(start_progress + (end_progress - start_progress) * step_progress)
                    self.progress_signal.emit(min(end_progress, overall_progress), message)

        self.process.wait()
        if not self._is_cancelled and self.process.returncode != 0:
            error_output = self.process.stderr.read()
            raise subprocess.CalledProcessError(self.process.returncode, command, stderr=error_output)


class PluginWidget(QWidget):
    PLUGIN_NAME = "Tạo Video Nhạc Dài"
    PLUGIN_DESCRIPTION = "Ghép nhiều video ngắn và lặp lại chúng để tạo một video dài, chèn nhạc nền có độ dài tùy chỉnh."

    def __init__(self):
        super().__init__()
        self.settings = QSettings("VideoEditorTool", "App2Settings")
        self.is_muted = False
        self.last_volume = 100
        self.worker_thread = None
        self.videos = []
        self.audio = None
        self.last_video_dir = self.settings.value("lastVideoDir", str(Path.home()), str)
        self.last_audio_dir = self.settings.value("lastAudioDir", str(Path.home()), str)
        
        if CAN_PLAY_VIDEO:
            self.media_player = QMediaPlayer()
            self.audio_output = QAudioOutput() 
            self.media_player.setAudioOutput(self.audio_output)
            self.audio_preview_player = QMediaPlayer()
            self.audio_preview_output = QAudioOutput()
            self.audio_preview_player.setAudioOutput(self.audio_preview_output)
        else:
            self.media_player, self.audio_output, self.audio_preview_player, self.audio_preview_output = None, None, None, None
            
        # Theme manager instance
        self.theme_manager = PluginThemeManager()
        self.setStyleSheet(self.theme_manager.get_standard_stylesheet())

        self._setup_ui()
        self.reset_ui()
        self.ensure_default_output_dir_exists()
        
    def _create_frame_title(self, text):
        label = QLabel(text); label.setObjectName("frameTitle"); return label
        
    def _create_button(self, text, on_click, bg_color, hover_color, min_size=QSize(0,0)):
        btn = QPushButton(text); btn.clicked.connect(on_click); btn.setMinimumSize(min_size)
        btn.setStyleSheet(f"QPushButton {{ background-color: {bg_color}; color: white; padding: 6px 12px; border-radius: 6px; font-weight: bold; }} QPushButton:hover {{ background-color: {hover_color}; }} QPushButton:disabled {{ background-color: #555; color: #bbb; }}")
        return btn

    def _create_action_button(self, text, on_click, bg, hover, text_color):
        btn = QPushButton(text); btn.clicked.connect(on_click)
        btn.setStyleSheet(f"QPushButton {{ background-color: {bg}; color: {text_color}; padding: 12px 20px; border-radius: 8px; font-weight: bold; font-size: 16px; }} QPushButton:hover {{ background-color: {hover}; }} QPushButton:disabled {{ background-color: #555; color: #bbb; }}")
        return btn

    def _setup_ui(self):
        layout = QVBoxLayout(self); layout.setContentsMargins(30, 30, 30, 30); layout.setSpacing(15)
        title = QLabel("Tạo Video Nhạc Dài (Ghép & Lặp)"); title.setObjectName("titleLabel"); layout.addWidget(title)
        
        grid_layout = QGridLayout(); grid_layout.setSpacing(15); grid_layout.setColumnStretch(0, 2); grid_layout.setColumnStretch(1, 1); grid_layout.setColumnStretch(2, 1)
        
        self.video_frame = self._create_video_player_widget(); grid_layout.addWidget(self.video_frame, 0, 0, 2, 1)
        grid_layout.addWidget(self._create_video_list_widget(), 0, 1)
        self.settings_frame = self._create_settings_widget(); grid_layout.addWidget(self.settings_frame, 0, 2)
        grid_layout.addWidget(self._create_audio_player_frame(), 1, 1)

        action_container = QFrame(); action_layout = QVBoxLayout(action_container); action_layout.setContentsMargins(0, 0, 0, 0); action_layout.setSpacing(10)
        action_layout.addWidget(self._create_output_dir_widget()); action_layout.addWidget(self._create_loading_status_widget()); action_layout.addWidget(self._create_action_buttons_widget())
        grid_layout.addWidget(action_container, 1, 2)
        
        layout.addLayout(grid_layout); layout.addStretch() 
        
        if CAN_PLAY_VIDEO and self.media_player:
            self.media_player.setVideoOutput(self.video_widget); self.media_player.positionChanged.connect(self.position_changed)
            self.media_player.durationChanged.connect(self.duration_changed); self.media_player.playbackStateChanged.connect(self.state_changed)
        if CAN_PLAY_VIDEO and self.audio_preview_player:
             self.audio_preview_player.positionChanged.connect(self.audio_position_changed); self.audio_preview_player.durationChanged.connect(self.audio_duration_changed)
             self.audio_preview_player.playbackStateChanged.connect(self.audio_state_changed)
        
    def _create_frame(self, title):
        frame = QFrame(); frame_layout = QVBoxLayout(frame); frame_layout.setContentsMargins(10, 10, 10, 10)
        if title: frame_layout.addWidget(self._create_frame_title(title))
        return frame, frame_layout
        
    def _create_video_player_widget(self):
        video_frame, video_layout = self._create_frame("PHÁT VIDEO"); video_frame.setMinimumHeight(250); video_layout.setSpacing(5)
        if CAN_PLAY_VIDEO:
            self.video_widget = QVideoWidget(); self.video_widget.setStyleSheet("background-color: black; border-radius: 5px;"); video_layout.addWidget(self.video_widget, 1) 
            self.control_panel = QFrame(); self.control_panel.setStyleSheet("QFrame { background-color: transparent; border: none; padding: 0px; }")
            control_layout = QVBoxLayout(self.control_panel); control_layout.setContentsMargins(0, 0, 0, 0); control_layout.setSpacing(5)
            self.position_slider = QSlider(Qt.Orientation.Horizontal); self.position_slider.setRange(0, 0); self.position_slider.sliderMoved.connect(self.set_position); control_layout.addWidget(self.position_slider)
            
            playback_layout = QHBoxLayout(); self.play_button = QPushButton("▶️"); self.play_button.setObjectName("PlayPauseButton"); self.play_button.clicked.connect(self.toggle_play_pause); playback_layout.addWidget(self.play_button)
            self.time_label = QLabel("00:00 / 00:00"); self.time_label.setStyleSheet("color: #d6d6d6; font-size: 14px; font-weight: bold;"); playback_layout.addWidget(self.time_label); playback_layout.addStretch()
            
            self.volume_icon = QLabel("🔊"); self.volume_icon.setObjectName("VolumeIcon"); self.volume_icon.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)); self.volume_icon.mousePressEvent = lambda event: self.toggle_mute(event); playback_layout.addWidget(self.volume_icon)
            self.volume_slider = VolumeSlider(Qt.Orientation.Horizontal); self.volume_slider.setObjectName("VolumeSlider"); self.volume_slider.setRange(0, 100); self.volume_slider.setValue(100); self.volume_slider.setFixedWidth(80); self.volume_slider.valueChanged.connect(self.set_volume); playback_layout.addWidget(self.volume_slider)
            
            control_layout.addLayout(playback_layout); video_layout.addWidget(self.control_panel); self.control_panel.setVisible(False) 
        else:
            self.video_widget = QLabel("⚠️ Cần cài đặt QtMultimedia để xem trước."); self.video_widget.setAlignment(Qt.AlignmentFlag.AlignCenter); self.video_widget.setStyleSheet("background-color: #1a1a1a; padding: 20px; border-radius: 4px; color: #e74c3c; font-weight: bold;"); video_layout.addWidget(self.video_widget)
            self.play_button, self.position_slider, self.time_label = None, None, None
        return video_frame

    def _create_video_list_widget(self):
        video_list_frame = QFrame(); video_list_layout = QVBoxLayout(video_list_frame); video_list_layout.setContentsMargins(10, 10, 10, 10)
        self.video_count_label = QLabel("Video đã chọn: 0"); video_list_layout.addWidget(self.video_count_label)
        self.video_list_widget = QListWidget()
        self.video_list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        # THÊM MỚI: Kích hoạt kéo-thả
        self.video_list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.video_list_widget.setMinimumHeight(60)
        self.video_list_widget.itemSelectionChanged.connect(self._on_list_selection_changed)
        video_list_layout.addWidget(self.video_list_widget, 1)
        
        input_buttons_layout = QHBoxLayout(); self.btn_add_video = QPushButton("➕"); self.btn_add_video.setObjectName("AddButton"); self.btn_add_video.setFixedSize(35, 35); self.btn_add_video.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold)); self.btn_add_video.clicked.connect(self.select_videos); input_buttons_layout.addWidget(self.btn_add_video, alignment=Qt.AlignmentFlag.AlignLeft)
        self.btn_remove_video = QPushButton("−"); self.btn_remove_video.setObjectName("RemoveButton"); self.btn_remove_video.setFixedSize(35, 35); self.btn_remove_video.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold)); self.btn_remove_video.clicked.connect(self.remove_selected_videos_update); input_buttons_layout.addWidget(self.btn_remove_video, alignment=Qt.AlignmentFlag.AlignLeft); input_buttons_layout.addStretch(1)
        
        btn_clear_videos = self._create_button("❌ Xóa tất cả", self.clear_all_videos, "#dc3545", "#c82333"); input_buttons_layout.addWidget(btn_clear_videos, alignment=Qt.AlignmentFlag.AlignRight); video_list_layout.addLayout(input_buttons_layout)
        return video_list_frame

    def _create_audio_player_frame(self):
        audio_container, audio_layout = self._create_frame("TRÌNH NGHE MP3"); audio_layout.setContentsMargins(10, 10, 10, 10)
        self.audio_path_line = QLineEdit("Chưa có nhạc nào được chọn..."); self.audio_path_line.setReadOnly(True); audio_layout.addWidget(self.audio_path_line)
        
        file_buttons_layout = QHBoxLayout(); btn_add_audio = self._create_button("Chọn nhạc", self.select_audio, "#e74c3c", "#c0392b"); btn_clear_audio = self._create_button("Xóa nhạc", self.clear_audio, "#6c757d", "#5a6268"); file_buttons_layout.addWidget(btn_add_audio); file_buttons_layout.addWidget(btn_clear_audio); audio_layout.addLayout(file_buttons_layout)
        
        if CAN_PLAY_VIDEO:
            self.audio_controls_frame = QFrame(); self.audio_controls_frame.setObjectName("AudioControls"); controls_layout = QVBoxLayout(self.audio_controls_frame); controls_layout.setContentsMargins(5, 5, 5, 5)
            self.audio_position_slider = QSlider(Qt.Orientation.Horizontal); self.audio_position_slider.setRange(0, 0); self.audio_position_slider.sliderMoved.connect(self.audio_set_position); controls_layout.addWidget(self.audio_position_slider)
            
            play_time_layout = QHBoxLayout(); self.audio_play_button = QPushButton("▶️"); self.audio_play_button.setObjectName("AudioPlayButton"); self.audio_play_button.setFixedSize(30, 30); self.audio_play_button.clicked.connect(self.audio_toggle_play_pause); play_time_layout.addWidget(self.audio_play_button)
            self.audio_time_label = QLabel("00:00 / 00:00"); play_time_layout.addWidget(self.audio_time_label); play_time_layout.addStretch(); controls_layout.addLayout(play_time_layout)
            audio_layout.addWidget(self.audio_controls_frame); self.audio_controls_frame.setVisible(False)
        
        audio_layout.addStretch(); return audio_container

    def _create_settings_widget(self):
        settings_frame = QFrame(); settings_layout = QVBoxLayout(settings_frame)
        settings_layout.addWidget(self._create_frame_title("TÙY CHỈNH CHỨC NĂNG:")); settings_layout.addSpacing(10)
        
        duration_layout = QHBoxLayout(); duration_layout.addWidget(QLabel("Tổng thời lượng Video (phút):")); self.spin_duration = QSpinBox(); self.spin_duration.setRange(1, 240); self.spin_duration.setValue(self.settings.value("duration", 10, int)); self.spin_duration.valueChanged.connect(lambda val: self.settings.setValue("duration", val)); duration_layout.addWidget(self.spin_duration); duration_layout.addStretch(); settings_layout.addLayout(duration_layout)
        self.mute_checkbox = QCheckBox("Tắt âm thanh gốc của video"); self.mute_checkbox.setStyleSheet("QCheckBox { color: #bfbfbf; font-weight: bold; }"); self.mute_checkbox.setChecked(self.settings.value("muteOriginal", True, bool)); self.mute_checkbox.stateChanged.connect(lambda state: self.settings.setValue("muteOriginal", bool(state))); settings_layout.addWidget(self.mute_checkbox)
        
        volume_layout = QHBoxLayout(); volume_layout.addWidget(QLabel("Âm lượng nhạc nền:")); self.volume_slider_settings = VolumeSlider(Qt.Orientation.Horizontal); self.volume_slider_settings.setRange(0, 200); self.volume_slider_settings.setValue(self.settings.value("volume", 100, int)); self.volume_slider_settings.valueChanged.connect(self.update_volume_label); self.volume_label = QLabel(f"{self.settings.value('volume', 100, int)}%"); self.volume_label.setMinimumWidth(40); volume_layout.addWidget(self.volume_slider_settings); volume_layout.addWidget(self.volume_label); settings_layout.addLayout(volume_layout)
        settings_layout.addStretch(); return settings_frame
    
    def _create_output_dir_widget(self):
        output_frame = QFrame(); output_layout = QVBoxLayout(output_frame); output_layout.setContentsMargins(0, 0, 0, 0)
        output_dir_label = QLabel("Thư mục lưu kết quả:"); output_dir_label.setStyleSheet("font-weight: bold;"); output_layout.addWidget(output_dir_label)
        output_dir_layout = QHBoxLayout(); self.output_dir_line = QLineEdit(); self.output_dir_line.setReadOnly(True); output_dir_layout.addWidget(self.output_dir_line)
        btn_browse_output = self._create_button("Lưu", self.select_output_directory, "#28a745", "#5a6268"); btn_browse_output.setFixedSize(80, 35); output_dir_layout.addWidget(btn_browse_output); output_layout.addLayout(output_dir_layout)
        return output_frame

    def _create_loading_status_widget(self):
        loading_frame = QFrame(); loading_layout = QVBoxLayout(loading_frame); loading_layout.setContentsMargins(0, 0, 0, 0)
        self.progress_bar = QProgressBar(); self.progress_bar.setValue(0); self.progress_bar.setFormat("Chờ xử lý..."); loading_layout.addWidget(self.progress_bar)
        self.progress_message_label = QLabel(""); self.progress_message_label.setStyleSheet("color: #aaaaaa; font-size: 12px; margin-top: 5px;"); loading_layout.addWidget(self.progress_message_label)
        return loading_frame
        
    def _create_action_buttons_widget(self):
        action_buttons_frame = QFrame(); action_buttons_layout = QHBoxLayout(action_buttons_frame); action_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_run = self._create_action_button("🚀 Bắt đầu Xử Lý", self.start_processing, "#00b894", "#00d19a", "#071717"); self.btn_run.setMinimumHeight(40); self.btn_run.setEnabled(False); action_buttons_layout.addWidget(self.btn_run)
        self.btn_cancel = self._create_action_button("❌ Reset", self.handle_cancel_or_reset, "#dc3545", "#c82333", "white"); self.btn_cancel.setObjectName("ResetButton"); self.btn_cancel.setMinimumHeight(40); action_buttons_layout.addWidget(self.btn_cancel)
        return action_buttons_frame
    
    def toggle_play_pause(self):
        if self.media_player:
            if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState: self.media_player.pause()
            else: self.media_player.play()

    def state_changed(self, state):
        if self.play_button:
            self.play_button.setText("⏸️" if state == QMediaPlayer.PlaybackState.PlayingState else "▶️")
            if state == QMediaPlayer.PlaybackState.PlayingState and self.audio_preview_player and self.audio_preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.audio_preview_player.pause()

    def position_changed(self, pos):
        if self.position_slider and not self.position_slider.isSliderDown(): self.position_slider.setValue(pos)
        if self.time_label and self.media_player:
            self.time_label.setText(f"{QTime(0,0,0).addMSecs(pos).toString('mm:ss')} / {QTime(0,0,0).addMSecs(self.media_player.duration()).toString('mm:ss')}")

    def duration_changed(self, dur):
        if self.position_slider: self.position_slider.setRange(0, dur)
        if self.control_panel: self.control_panel.setVisible(dur > 0)
            
    def set_position(self, pos):
        if self.media_player: self.media_player.setPosition(pos)

    def set_volume(self, value):
        if self.audio_output:
            if value > 0 and self.is_muted: self.is_muted = False
            self.audio_output.setVolume(value / 100.0); self._update_volume_icon(value)
            if not self.is_muted: self.last_volume = value
        
    def toggle_mute(self, event):
        if self.audio_output and isinstance(event, QMouseEvent):
            if self.is_muted:
                target_volume = self.last_volume if self.last_volume > 0 else 50; self.is_muted = False
            else:
                if self.volume_slider.value() > 0: self.last_volume = self.volume_slider.value()
                target_volume = 0; self.is_muted = True
            self.volume_slider.setValue(target_volume); self.audio_output.setVolume(target_volume / 100.0); self._update_volume_icon(target_volume)

    def _update_volume_icon(self, vol):
        if self.volume_icon:
            if self.is_muted or vol == 0: self.volume_icon.setText("🔇")
            elif vol > 70: self.volume_icon.setText("🔊")
            else: self.volume_icon.setText("🔉")
            
    def audio_toggle_play_pause(self):
        if self.audio_preview_player:
            if self.audio_preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState: self.audio_preview_player.pause()
            else:
                if self.media_player and self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState: self.media_player.pause()
                self.audio_preview_player.play()

    def audio_state_changed(self, state):
        if self.audio_play_button: self.audio_play_button.setText("⏸️" if state == QMediaPlayer.PlaybackState.PlayingState else "▶️")

    def audio_position_changed(self, pos):
        if self.audio_position_slider and not self.audio_position_slider.isSliderDown(): self.audio_position_slider.setValue(pos)
        if self.audio_time_label and self.audio_preview_player:
            self.audio_time_label.setText(f"{QTime(0,0,0).addMSecs(pos).toString('mm:ss')} / {QTime(0,0,0).addMSecs(self.audio_preview_player.duration()).toString('mm:ss')}")

    def audio_duration_changed(self, dur):
        if self.audio_position_slider: self.audio_position_slider.setRange(0, dur)
        
    def audio_set_position(self, pos):
        if self.audio_preview_player: self.audio_preview_player.setPosition(pos)
            
    def remove_selected_videos_update(self):
        selected_items = self.video_list_widget.selectedItems()
        if not selected_items: return
        
        file_names_to_remove = [item.text() for item in selected_items]
        self.videos = [p for p in self.videos if Path(p).name not in file_names_to_remove]
        
        for item in selected_items: self.video_list_widget.takeItem(self.video_list_widget.row(item))
            
        self.update_video_count_label(); self._update_run_button_state()
        
        if self.media_player and not self.videos:
             self.media_player.stop(); self.control_panel.setVisible(False)
        elif self.media_player and self.videos:
             self.media_player.setSource(QUrl.fromLocalFile(self.videos[0])); self.media_player.play()

    def clear_all_videos(self):
        if self.media_player: self.media_player.stop()
        self.videos.clear(); self.video_list_widget.clear(); self.update_video_count_label(); self._update_run_button_state()
        if self.control_panel: self.control_panel.setVisible(False)
        if self.media_player: self.media_player.setSource(QUrl())

    def select_videos(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Chọn video MP4", self.last_video_dir, "Video (*.mp4)")
        if files:
            self.last_video_dir = os.path.dirname(files[0]); self.settings.setValue("lastVideoDir", self.last_video_dir)
            
            new_files_added = any(f not in self.videos for f in files)
            for file in files:
                if file not in self.videos: self.videos.append(file); self.video_list_widget.addItem(os.path.basename(file))
                    
            if self.media_player and new_files_added and self.videos:
                self.media_player.setSource(QUrl.fromLocalFile(self.videos[0])); self.media_player.play()
            self.update_video_count_label(); self._update_run_button_state()
        
    def _on_list_selection_changed(self):
        selected_items = self.video_list_widget.selectedItems()
        is_running = self.worker_thread and self.worker_thread.isRunning()
        self.btn_remove_video.setEnabled(bool(selected_items) and not is_running)

        if not selected_items:
            if self.media_player: self.media_player.stop()
            return
        
        row = self.video_list_widget.row(selected_items[0])
        if self.media_player and 0 <= row < len(self.videos):
            # Lấy path đúng dựa trên thứ tự hiện tại của self.videos, không phải từ list widget text
            try:
                selected_path = self.videos[row]
                if self.media_player.source() != QUrl.fromLocalFile(selected_path): self.media_player.setSource(QUrl.fromLocalFile(selected_path))
                self.media_player.play()
            except IndexError:
                pass # Bỏ qua nếu có lỗi index khi list đang thay đổi
    
    def update_video_count_label(self):
        self.video_count_label.setText(f"Video đã chọn: {len(self.videos)}")
        
    def select_audio(self):
        file, _ = QFileDialog.getOpenFileName(self, "Chọn nhạc MP3", self.last_audio_dir, "Audio (*.mp3)")
        if file:
            if self.audio_preview_player: self.audio_preview_player.stop()
            self.last_audio_dir = os.path.dirname(file); self.settings.setValue("lastAudioDir", self.last_audio_dir)
            self.audio = file; self.audio_path_line.setText(os.path.basename(file))
            if self.audio_preview_player: self.audio_preview_player.setSource(QUrl.fromLocalFile(file)); self.audio_controls_frame.setVisible(True)
        self._update_run_button_state()

    def clear_audio(self):
        if self.audio_preview_player: self.audio_preview_player.stop()
        self.audio = None; self.audio_path_line.setText("Chưa có nhạc nào được chọn...")
        if hasattr(self, 'audio_controls_frame'): self.audio_controls_frame.setVisible(False)
        self._update_run_button_state()
        
    def select_output_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu", self.output_dir_line.text())
        if directory: self.output_dir_line.setText(directory); self.settings.setValue("outputDir", directory)
            
    def ensure_default_output_dir_exists(self):
        default_dir = Path.home() / "Videos" / "VideoEditorTool_App2"; saved_dir = self.settings.value("outputDir", str(default_dir), str)
        self.output_dir_line.setText(saved_dir)
        if not Path(saved_dir).exists():
            try: Path(saved_dir).mkdir(parents=True, exist_ok=True)
            except Exception: self.output_dir_line.setText(str(Path.home()))

    def update_volume_label(self, value):
        self.volume_label.setText(f"{value}%"); self.settings.setValue("volume", value)
        
    def _update_run_button_state(self):
        is_running = self.worker_thread and self.worker_thread.isRunning()
        can_run = bool(self.videos) and bool(self.audio) and not is_running
        self.btn_run.setEnabled(can_run)
        self.btn_cancel.setText("❌ Hủy" if is_running else "❌ Reset")
        self.set_controls_enabled(not is_running)

    def reset_ui(self):
        self.clear_all_videos(); self.clear_audio()
        if self.audio_preview_player: self.audio_preview_player.stop()
        if hasattr(self, 'audio_controls_frame'): self.audio_controls_frame.setVisible(False)
        
        self.spin_duration.setValue(self.settings.value("duration", 10, int))
        self.mute_checkbox.setChecked(self.settings.value("muteOriginal", True, bool))
        self.volume_slider_settings.setValue(self.settings.value("volume", 100, int))
        self.update_volume_label(self.volume_slider_settings.value())
        
        self.progress_bar.setValue(0); self.progress_message_label.setText(""); self.progress_bar.setFormat("Chờ xử lý...")
        if self.volume_slider: self.volume_slider.setValue(100)
        self.set_controls_enabled(True)
        self._update_run_button_state()
    
    def set_theme(self, theme_name):
        """Set theme for this plugin"""
        if self.theme_manager.set_theme(theme_name):
            self.setStyleSheet(self.theme_manager.get_standard_stylesheet())
            return True
        return False

    def set_controls_enabled(self, enabled):
        widgets_to_toggle = self.findChildren((QPushButton, QSpinBox, QListWidget, QSlider, QCheckBox))
        for child in widgets_to_toggle:
            if child not in [self.btn_run, self.btn_cancel, self.btn_remove_video]:
                child.setEnabled(enabled)
        
        self.btn_remove_video.setEnabled(enabled and bool(self.videos))
        for btn in self.findChildren(QPushButton):
            if btn.text() == "❌ Xóa tất cả": btn.setEnabled(enabled and bool(self.videos))
        
        if self.control_panel: self.control_panel.setEnabled(enabled and bool(self.videos))
        if hasattr(self, 'audio_controls_frame'): self.audio_controls_frame.setEnabled(enabled and bool(self.audio))

    def start_processing(self):
        if not self.videos or not self.audio:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng chọn video và nhạc nền."); return
        
        output_dir = Path(self.output_dir_line.text()); output_dir.mkdir(parents=True, exist_ok=True)
        if self.media_player: self.media_player.stop()
        if self.audio_preview_player: self.audio_preview_player.stop()
        
        self.set_controls_enabled(False); self.btn_run.setEnabled(False); self.progress_bar.setValue(0); self.progress_message_label.setText("Đang khởi tạo..."); QApplication.processEvents()

        # SỬA LỖI: Lấy danh sách video theo thứ tự trên giao diện
        ordered_filenames = [self.video_list_widget.item(i).text() for i in range(self.video_list_widget.count())]
        path_map = {Path(p).name: p for p in self.videos}
        ordered_videos = [path_map[name] for name in ordered_filenames if name in path_map]
        
        self.worker_thread = FFmpegWorker(
            ordered_videos, 
            self.audio, 
            self.spin_duration.value(), 
            output_dir, 
            self.mute_checkbox.isChecked(), 
            self.volume_slider_settings.value()
        )

        self.worker_thread.progress_signal.connect(self.update_progress); self.worker_thread.finished_signal.connect(self.processing_finished)
        self.worker_thread.error_signal.connect(self.processing_error); self.worker_thread.start()

    def handle_cancel_or_reset(self):
        if self.worker_thread and self.worker_thread.isRunning():
            if QMessageBox.question(self, "Xác nhận hủy", "Bạn có muốn dừng quá trình đang chạy không?") == QMessageBox.StandardButton.Yes:
                self.worker_thread.cancel(); self.progress_message_label.setText(""); self.progress_bar.setFormat("Đã hủy bởi người dùng.")
                self.set_controls_enabled(True); self.btn_run.setEnabled(True)
        else: self.reset_ui()
            
    def update_progress(self, percentage, message):
        self.progress_bar.setValue(percentage); self.progress_bar.setFormat(f"{percentage}% - {message.split('...')[0]}"); self.progress_message_label.setText(message)

    def processing_finished(self, output_path_or_dir):
        self.progress_bar.setValue(100); self.progress_bar.setFormat("Hoàn thành!"); self.progress_message_label.setText("")
        QMessageBox.information(self, "Thành công", f"Video đã được ghép và lặp lại, lưu tại:\n{output_path_or_dir}")
        self.set_controls_enabled(True); self._update_run_button_state()
        try: os.startfile(Path(output_path_or_dir).parent)
        except: pass

    def processing_error(self, error_message):
        error_box = QMessageBox(); error_box.setIcon(QMessageBox.Icon.Critical); error_box.setText("Đã xảy ra lỗi trong quá trình xử lý.")
        error_box.setInformativeText("Vui lòng xem chi tiết bên dưới."); error_box.setDetailedText(error_message); error_box.setWindowTitle("Lỗi"); error_box.exec()
        self.progress_message_label.setText(""); self.progress_bar.setValue(0); self.progress_bar.setFormat("Đã xảy ra lỗi.")
        self.set_controls_enabled(True); self._update_run_button_state()
