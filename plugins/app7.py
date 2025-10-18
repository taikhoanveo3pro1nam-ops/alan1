# app7.py - Xử lý Âm thanh (Đã cập nhật lại phương pháp nối file nhanh, có cảnh báo)

import sys
import re
import subprocess
from pathlib import Path
import os
import shutil
import math
import tempfile
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QSpinBox, QMessageBox, QLineEdit, QFrame, QGridLayout, QStackedWidget,
    QComboBox, QApplication, QProgressBar, QListWidget, QListWidgetItem, QSlider,
    QCheckBox, QStackedLayout
)
from PyQt6.QtCore import Qt, QSettings, QThread, pyqtSignal, QUrl, QTime
from PyQt6.QtGui import QFont, QMouseEvent

# Thêm thư viện Multimedia
try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    CAN_PLAY_AUDIO = True
except ImportError:
    CAN_PLAY_AUDIO = False

# Import theme manager
from theme_manager import PluginThemeManager

# --- Custom Slider cho phép click để tua ---
class CustomSlider(QSlider):
    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            if self.orientation() == Qt.Orientation.Horizontal:
                value = self.minimum() + (self.maximum() - self.minimum()) * event.pos().x() / self.width()
                self.setValue(int(value))

# --- LOGIC ĐƯỜNG DẪN FFmpeg ---
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

FFMPEG_EXE = BASE_DIR / "ffmpeg.exe"
FFPROBE_EXE = BASE_DIR / "ffprobe.exe"
# -----------------------------

class DurationCalculator(QThread):
    """Luồng riêng để tính tổng thời lượng mà không làm treo giao diện."""
    finished = pyqtSignal(float)
    error = pyqtSignal(str)

    def __init__(self, files_to_check):
        super().__init__()
        self.files = list(files_to_check)
        self.ffprobe_cmd = [str(FFPROBE_EXE)] if FFPROBE_EXE.exists() else ["ffprobe"]

    def run(self):
        total_duration = 0.0
        try:
            for file_path in self.files:
                cmd = self.ffprobe_cmd + ["-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW, encoding='utf-8')
                total_duration += float(result.stdout.strip())
            self.finished.emit(total_duration)
        except Exception as e:
            self.error.emit(f"Không thể tính thời lượng: {e}")


class FFmpegWorker(QThread):
    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(str, list)
    error_signal = pyqtSignal(str)

    def __init__(self, mode, data):
        super().__init__()
        self.mode = mode
        self.data = data
        self.ffmpeg_cmd = [str(FFMPEG_EXE)] if FFMPEG_EXE.exists() else ["ffmpeg"]
        self.ffprobe_cmd = [str(FFPROBE_EXE)] if FFPROBE_EXE.exists() else ["ffprobe"]
        self._is_cancelled = False
        self.process = None

    def cancel(self):
        self._is_cancelled = True
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except: pass

    def get_duration(self, file_path):
        try:
            cmd = self.ffprobe_cmd + ["-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW, encoding='utf-8')
            return float(result.stdout.strip())
        except Exception: return 0
    
    def _run_command(self, command, message, progress_start, progress_end=None, total_duration=None):
        if self._is_cancelled: return False
        self.progress_signal.emit(progress_start, message)
        
        self.process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, encoding='utf-8', errors='ignore',
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        if total_duration and progress_end:
            time_regex = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.\d{2}")
            for line in self.process.stderr:
                if self._is_cancelled: self.process.terminate(); self.process.wait(); return False
                match = time_regex.search(line)
                if match:
                    h, m, s = map(int, match.groups())
                    current_seconds = h * 3600 + m * 60 + s
                    step_progress = current_seconds / total_duration
                    overall_progress = int(progress_start + (progress_end - progress_start) * step_progress)
                    self.progress_signal.emit(min(progress_end, overall_progress), message)
        else:
            while self.process.poll() is None:
                if self._is_cancelled: self.process.terminate(); self.process.wait(); return False
                self.msleep(100)

        self.process.wait()
        if not self._is_cancelled and self.process.returncode != 0:
            error_output = self.process.stderr.read()
            raise subprocess.CalledProcessError(self.process.returncode, command, stderr=error_output)
            
        return not self._is_cancelled

    def run(self):
        try:
            if self.mode == 'merge':
                self.run_merge()
            elif self.mode == 'convert':
                self.run_convert()
        except Exception as e:
            if not self._is_cancelled:
                self.error_signal.emit(f"Lỗi không mong muốn: {e}\nChi tiết: {getattr(e, 'stderr', 'Không có')}")

    def run_merge(self):
        files = self.data['files']
        target_minutes = self.data['duration']
        output_dir = self.data['output_dir']
        use_original_duration = self.data.get('use_original_duration', False)

        with tempfile.TemporaryDirectory() as temp_dir:
            list_file_path = os.path.join(temp_dir, "audiolist.txt")
            with open(list_file_path, 'w', encoding='utf-8') as f:
                for audio_file in files:
                    clean_path = Path(audio_file).resolve().as_posix()
                    f.write(f"file '{clean_path}'\n")

            base_name = Path(files[0]).stem
            
            if use_original_duration:
                output_filename = f"{base_name}_merged_original.mp3"
                final_output_path = Path(output_dir) / output_filename
                counter = 1
                while final_output_path.exists():
                    final_output_path = Path(output_dir) / f"{base_name}_merged_original({counter}).mp3"
                    counter += 1
                
                # SỬ DỤNG LẠI -c copy THEO YÊU CẦU (NHANH NHƯNG CÓ THỂ LỖI)
                concat_cmd = self.ffmpeg_cmd + ["-f", "concat", "-safe", "0", "-i", list_file_path, "-c", "copy", str(final_output_path), "-y"]
                if not self._run_command(concat_cmd, "Đang ghép các file (chế độ nhanh)...", 10): return
                
                if self._is_cancelled: 
                    if final_output_path.exists(): final_output_path.unlink()
                    return
                self.finished_signal.emit(str(final_output_path), [])
                return

            target_seconds = target_minutes * 60
            concatenated_file = os.path.join(temp_dir, "concatenated.mp3")
            # Nối file vẫn dùng -c copy để nhanh
            concat_cmd = self.ffmpeg_cmd + ["-f", "concat", "-safe", "0", "-i", list_file_path, "-c", "copy", concatenated_file, "-y"]
            if not self._run_command(concat_cmd, "Đang nối các file...", 10): return
            
            concat_duration = self.get_duration(concatenated_file)
            if concat_duration == 0:
                raise Exception("Không thể nối hoặc đọc thời lượng file đã nối. Các file có thể không tương thích.")

            num_loops = math.ceil(target_seconds / concat_duration)
            
            loop_list_file = os.path.join(temp_dir, "looplist.txt")
            with open(loop_list_file, 'w', encoding='utf-8') as f:
                for _ in range(max(1, int(num_loops))):
                    clean_path = Path(concatenated_file).resolve().as_posix()
                    f.write(f"file '{clean_path}'\n")

            looped_file = os.path.join(temp_dir, "looped.mp3")
            loop_cmd = self.ffmpeg_cmd + ["-f", "concat", "-safe", "0", "-i", loop_list_file, "-c", "copy", looped_file, "-y"]
            if not self._run_command(loop_cmd, "Đang lặp lại file...", 60): return

            output_filename = f"{base_name}_merged_{target_minutes}min.mp3"
            final_output_path = Path(output_dir) / output_filename
            counter = 1
            while final_output_path.exists():
                final_output_path = Path(output_dir) / f"{base_name}_merged_{target_minutes}min({counter}).mp3"
                counter += 1

            trim_cmd = self.ffmpeg_cmd + ["-i", looped_file, "-t", str(target_seconds), "-c", "copy", str(final_output_path), "-y"]
            if not self._run_command(trim_cmd, "Đang cắt file cuối...", 80, 99, total_duration=target_seconds): return
            
            if self._is_cancelled:
                if final_output_path.exists(): final_output_path.unlink()
                return

            self.finished_signal.emit(str(final_output_path), [])

    def run_convert(self):
        files = self.data['files']
        output_format = self.data['format']
        output_dir = self.data['output_dir']
        bitrate = self.data['bitrate']
        total_files = len(files)
        failed_files = []

        for i, file_path in enumerate(files):
            if self._is_cancelled: break
            
            base_name = Path(file_path).stem
            output_filename = f"{base_name}.{output_format}"
            output_path = Path(output_dir) / output_filename
            counter = 1
            while output_path.exists():
                output_path = Path(output_dir) / f"{base_name}({counter}).{output_format}"
                counter += 1
            
            cmd = self.ffmpeg_cmd + ["-i", str(file_path), "-vn", "-codec:a", "libmp3lame", "-b:a", f"{bitrate}k", str(output_path), "-y"]
            
            try:
                duration = self.get_duration(file_path)
                message = f"File {i+1}/{total_files}: {base_name}"
                progress_start = int((i / total_files) * 100)
                progress_end = int(((i + 0.9) / total_files) * 100)
                
                if not self._run_command(cmd, message, progress_start, progress_end, duration):
                    if output_path.exists(): output_path.unlink()
                    break 
            except Exception as e:
                failed_files.append(f"{base_name} (Lỗi: {e})")
                if output_path.exists(): output_path.unlink()
                continue

        if not self._is_cancelled:
            self.finished_signal.emit(str(output_dir), failed_files)

class PluginWidget(QWidget):
    PLUGIN_NAME = "Xử lý Âm thanh"
    PLUGIN_DESCRIPTION = "Ghép, lặp lại hoặc chuyển đổi định dạng các file âm thanh (MP3, WAV, etc.)."

    MODE_MERGE = "merge"
    MODE_CONVERT = "convert"

    def __init__(self):
        super().__init__()
        self.settings = QSettings("VideoEditorTool", "App7Settings")
        self.mode = self.MODE_MERGE
        self.files = []
        self.worker = None
        self.duration_worker = None

        if CAN_PLAY_AUDIO:
            self.audio_preview_player = QMediaPlayer()
            self.audio_preview_output = QAudioOutput()
            self.audio_preview_player.setAudioOutput(self.audio_preview_output)
        else:
            self.audio_preview_player = None

        # Initialize theme manager
        self.theme_manager = PluginThemeManager()
        self.setStyleSheet(self.theme_manager.get_standard_stylesheet())
        self._setup_ui()
        self._connect_signals()
        self._load_settings()
        self.update_ui_state()


    def get_stylesheet(self):
        return """
            QWidget { background-color: #1e1e1e; color: #d6d6d6; font-family: 'Segoe UI'; font-size: 14px; }
            QFrame { background-color: #2a2a2a; border-radius: 8px; padding: 10px; }
            QFrame#SettingsFrame { background-color: transparent; padding: 0; }
            QLabel[objectName=\"titleLabel\"] { color: #ffffff; font-size: 20px; font-weight: bold; margin-bottom: 10px; }
            
            QPushButton:disabled { background-color: #555; color: #bbb; }
            
            QPushButton#ModeButton:checked {
                background-color: #dfbb00; color: #071717; border: 1px solid #dfbb00;
            }
            QPushButton#RunButton { background-color: #dfbb00; color: #071717; }
            QPushButton#RunButton:hover { background-color: #eccf3f; }
            
            QProgressBar::chunk { background-color: #28a745; }

            QPushButton#AddButton { background-color: #28a745; color: white; }
            QPushButton#AddButton:hover { background-color: #218838; }

            QPushButton#RemoveButton { background-color: #fd7e14; color: white; }
            QPushButton#RemoveButton:hover { background-color: #e87312; }
            QPushButton#ClearAllButton { background-color: #dc3545; color: white; }
            QPushButton#ClearAllButton:hover { background-color: #c82333; }
            QPushButton#ResetButton { background-color: #dc3545; color: white; }
            QPushButton#ResetButton:hover { background-color: #c82333; }
            
            QPushButton { background-color: #3a3a3a; color: #d6d6d6; padding: 10px; border-radius: 8px; font-weight: bold; border: none; }
            QPushButton:hover { background-color: #4a4a4a; }
            
            QPushButton#ModeButton {
                background-color: #2a2a2a; color: #bfbfbf; padding: 10px 15px; border-radius: 8px;
                font-weight: bold; border: 1px solid #3a3a3a;
            }
            
            QLineEdit, QComboBox, QListWidget { background-color: #3a3a3a; padding: 8px; border-radius: 5px; border: 1px solid #4a4a4a; }
            QSpinBox { background-color: #3a3a3a; padding: 8px; border-radius: 5px; border: 1px solid #4a4a4a; lineedit-padding: 0px; }
            QProgressBar { text-align: center; }
            
            QSlider::groove:horizontal { border: none; height: 6px; background: #3a3a3a; margin: 0px 0; border-radius: 3px; }
            QSlider::handle:horizontal { background: #dfbb00; border: none; width: 14px; margin: -4px 0; border-radius: 7px; }
            QPushButton#AudioPlayButton {
                background-color: transparent; color: #dfbb00; border: none; padding: 0px; font-size: 26px;
                font-weight: bold; text-align: center; min-width: 30px; max-width: 30px;
            }
            QPushButton#AudioPlayButton:hover { color: #eccf3f; }
        """

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 30)

        header_layout = QHBoxLayout()
        title = QLabel("Công cụ xử lý Âm thanh"); title.setObjectName("titleLabel")
        header_layout.addWidget(title)
        header_layout.addStretch()
        self.btn_mode_merge = QPushButton("Nối/Nhân bản MP3"); self.btn_mode_merge.setObjectName("ModeButton"); self.btn_mode_merge.setCheckable(True)
        self.btn_mode_convert = QPushButton("Chuyển đổi Định dạng"); self.btn_mode_convert.setObjectName("ModeButton"); self.btn_mode_convert.setCheckable(True)
        header_layout.addWidget(self.btn_mode_merge)
        header_layout.addWidget(self.btn_mode_convert)
        main_layout.addLayout(header_layout)
        
        self.main_stack = QStackedWidget()
        self.merge_widget = self._create_merge_widget()
        self.convert_widget = self._create_convert_widget()
        self.main_stack.addWidget(self.merge_widget)
        self.main_stack.addWidget(self.convert_widget)
        
        main_layout.addWidget(self.main_stack, 1)

        output_frame, output_layout = self._create_frame("")
        output_layout.addWidget(QLabel("Thư mục lưu:"))
        output_dir_layout = QHBoxLayout()
        self.output_dir_line = QLineEdit(); self.output_dir_line.setReadOnly(True)
        self.btn_browse_output = QPushButton("Lưu vào...")
        output_dir_layout.addWidget(self.output_dir_line, 1)
        output_dir_layout.addWidget(self.btn_browse_output)
        output_layout.addLayout(output_dir_layout)
        self.progress_bar = QProgressBar()
        output_layout.addWidget(self.progress_bar)
        main_layout.addWidget(output_frame)

        action_layout = QHBoxLayout()
        self.btn_run = QPushButton("🚀 Bắt đầu"); self.btn_run.setObjectName("RunButton"); self.btn_run.setMinimumHeight(40)
        self.btn_reset = QPushButton("❌ Reset"); self.btn_reset.setMinimumHeight(40); self.btn_reset.setObjectName("ResetButton")
        action_layout.addWidget(self.btn_run, 1)
        action_layout.addWidget(self.btn_reset)
        main_layout.addLayout(action_layout)

    def _create_frame(self, title, is_transparent=False):
        frame = QFrame()
        if is_transparent: frame.setObjectName("SettingsFrame")
        layout = QVBoxLayout(frame)
        if title:
            title_label = QLabel(title); title_label.setStyleSheet("font-weight:bold; color:#bfbfbf;")
            layout.addWidget(title_label)
        return frame, layout

    def _create_file_list_widget(self):
        container = QWidget(); layout = QVBoxLayout(container); layout.setContentsMargins(0,0,0,0)
        file_list = QListWidget(); file_list.setDragDropMode(QListWidget.DragDropMode.InternalMove); layout.addWidget(file_list, 1)
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("➕ Thêm file"); btn_add.setObjectName("AddButton")
        btn_remove = QPushButton("➖ Xóa"); btn_remove.setObjectName("RemoveButton")
        btn_clear = QPushButton("❌ Xóa tất cả"); btn_clear.setObjectName("ClearAllButton")
        btn_layout.addWidget(btn_add, 1); btn_layout.addWidget(btn_remove); btn_layout.addWidget(btn_clear)
        layout.addLayout(btn_layout)
        return container, file_list, btn_add, btn_remove, btn_clear

    def _create_audio_preview_widget(self):
        if not CAN_PLAY_AUDIO: return QLabel("Cần cài đặt QtMultimedia để nghe trước"), None, None, None
        player_frame = QFrame(); player_layout = QVBoxLayout(player_frame); player_layout.setContentsMargins(5, 5, 5, 5)
        position_slider = CustomSlider(Qt.Orientation.Horizontal); position_slider.setRange(0, 0); player_layout.addWidget(position_slider)
        controls_layout = QHBoxLayout(); play_button = QPushButton("▶️"); play_button.setObjectName("AudioPlayButton"); time_label = QLabel("00:00 / 00:00")
        controls_layout.addWidget(play_button); controls_layout.addWidget(time_label, 1); player_layout.addLayout(controls_layout)
        player_frame.setVisible(False)
        return player_frame, position_slider, play_button, time_label

    def _create_merge_widget(self):
        widget = QWidget(); layout = QGridLayout(widget)
        list_container, self.merge_file_list, self.btn_add_merge, self.btn_remove_merge, self.btn_clear_merge = self._create_file_list_widget()
        layout.addWidget(list_container, 0, 0, 2, 1)
        settings_frame, settings_layout = self._create_frame("Tùy chọn Nối & Lặp lại", is_transparent=True)
        self.duration_container = QWidget(); duration_stack_layout = QStackedLayout(self.duration_container); duration_stack_layout.setContentsMargins(0,0,0,0)
        spinbox_widget = QWidget(); spinbox_layout = QHBoxLayout(spinbox_widget); spinbox_layout.setContentsMargins(0,0,0,0)
        spinbox_layout.addWidget(QLabel("Thời lượng cuối (phút):")); self.duration_spinbox = QSpinBox(); self.duration_spinbox.setRange(1, 1000)
        self.duration_spinbox.setKeyboardTracking(False); spinbox_layout.addWidget(self.duration_spinbox)
        self.total_duration_label = QLabel("Tổng: 0 phút 0 giây"); self.total_duration_label.setStyleSheet("font-weight: bold; color: #dfbb00;"); self.total_duration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        duration_stack_layout.addWidget(spinbox_widget); duration_stack_layout.addWidget(self.total_duration_label); settings_layout.addWidget(self.duration_container)
        self.chk_original_duration = QCheckBox("Ghép theo thời lượng gốc của các file"); settings_layout.addWidget(self.chk_original_duration)
        settings_layout.addStretch(); layout.addWidget(settings_frame, 0, 1)
        self.merge_player_widget, self.merge_slider, self.merge_play_btn, self.merge_time_label = self._create_audio_preview_widget()
        layout.addWidget(self.merge_player_widget, 1, 1)
        return widget

    def _create_convert_widget(self):
        widget = QWidget(); layout = QGridLayout(widget)
        list_container, self.convert_file_list, self.btn_add_convert, self.btn_remove_convert, self.btn_clear_convert = self._create_file_list_widget()
        layout.addWidget(list_container, 0, 0, 2, 1)
        settings_frame, settings_layout = self._create_frame("Tùy chọn chuyển đổi:", is_transparent=True)
        format_layout = QHBoxLayout(); format_layout.addWidget(QLabel("Định dạng đầu ra:")); self.format_combo = QComboBox(); self.format_combo.addItems(["mp3", "wav", "aac", "ogg"]); format_layout.addWidget(self.format_combo); settings_layout.addLayout(format_layout)
        bitrate_layout = QHBoxLayout(); bitrate_layout.addWidget(QLabel("Bitrate (cho MP3):")); self.bitrate_combo = QComboBox(); self.bitrate_combo.addItems(["320", "256", "192", "128"]); bitrate_layout.addWidget(self.bitrate_combo); settings_layout.addLayout(bitrate_layout)
        settings_layout.addStretch(); layout.addWidget(settings_frame, 0, 1)
        self.convert_player_widget, self.convert_slider, self.convert_play_btn, self.convert_time_label = self._create_audio_preview_widget()
        layout.addWidget(self.convert_player_widget, 1, 1)
        return widget

    def _connect_signals(self):
        self.btn_mode_merge.clicked.connect(lambda: self.set_mode(self.MODE_MERGE))
        self.btn_mode_convert.clicked.connect(lambda: self.set_mode(self.MODE_CONVERT))
        
        self.btn_add_merge.clicked.connect(self.add_files)
        self.btn_remove_merge.clicked.connect(self.remove_selected_files)
        self.btn_clear_merge.clicked.connect(self.clear_files)
        self.merge_file_list.itemSelectionChanged.connect(self._on_list_selection_changed)
        self.merge_file_list.model().rowsMoved.connect(self.on_list_reordered)

        self.btn_add_convert.clicked.connect(self.add_files)
        self.btn_remove_convert.clicked.connect(self.remove_selected_files)
        self.btn_clear_convert.clicked.connect(self.clear_files)
        self.convert_file_list.itemSelectionChanged.connect(self._on_list_selection_changed)
        
        self.chk_original_duration.stateChanged.connect(self._toggle_duration_widget)
        self.btn_browse_output.clicked.connect(self.select_output_dir)
        self.btn_run.clicked.connect(self.start_processing)
        self.btn_reset.clicked.connect(self.handle_cancel_or_reset)

        if CAN_PLAY_AUDIO:
            for btn in [self.merge_play_btn, self.convert_play_btn]: btn.clicked.connect(self.audio_toggle_play_pause)
            for slider in [self.merge_slider, self.convert_slider]: slider.sliderMoved.connect(self.audio_set_position)
            self.audio_preview_player.positionChanged.connect(self.audio_position_changed)
            self.audio_preview_player.durationChanged.connect(self.audio_duration_changed)
            self.audio_preview_player.playbackStateChanged.connect(self.audio_state_changed)

    def _load_settings(self):
        self.duration_spinbox.setValue(self.settings.value("mergeDuration", 60, type=int))
        self.format_combo.setCurrentText(self.settings.value("convertFormat", "mp3"))
        self.bitrate_combo.setCurrentText(self.settings.value("convertBitrate", "192"))
        default_dir = str(Path.home() / "Music" / "AudioToolOutput")
        output_dir = self.settings.value("outputDir", default_dir)
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        self.output_dir_line.setText(output_dir)
        self.set_mode(self.settings.value("mode", self.MODE_MERGE), force=True)

    def set_mode(self, new_mode, force=False):
        if self.mode == new_mode and not force: return
        if self.worker and self.worker.isRunning():
            self.btn_mode_merge.setChecked(self.mode == self.MODE_MERGE)
            self.btn_mode_convert.setChecked(self.mode == self.MODE_CONVERT)
            return
        self.mode = new_mode
        self.settings.setValue("mode", new_mode)
        if new_mode == self.MODE_MERGE:
            self.main_stack.setCurrentIndex(0); self.btn_mode_merge.setChecked(True); self.btn_mode_convert.setChecked(False)
        else:
            self.main_stack.setCurrentIndex(1); self.btn_mode_merge.setChecked(False); self.btn_mode_convert.setChecked(True)
        self.clear_files(); self.update_ui_state()

    def get_current_list_widget(self):
        return self.merge_file_list if self.mode == self.MODE_MERGE else self.convert_file_list

    def add_files(self):
        last_dir = self.settings.value("lastAudioDir", str(Path.home()))
        file_filter = "Audio Files (*.mp3 *.wav *.aac *.m4a *.ogg)" if self.mode == self.MODE_MERGE else "Media Files (*.mp3 *.wav *.mp4 *.mkv)"
        files, _ = QFileDialog.getOpenFileNames(self, "Chọn file", last_dir, file_filter)
        if files:
            list_widget = self.get_current_list_widget()
            for f in files:
                if f not in self.files: self.files.append(f); list_widget.addItem(Path(f).name)
            self.settings.setValue("lastAudioDir", str(Path(files[0]).parent))
            self.update_ui_state()
            if list_widget.count() > 0: list_widget.setCurrentRow(0)
            if self.mode == self.MODE_MERGE: self._update_total_duration_display()

    def on_list_reordered(self):
        list_widget = self.get_current_list_widget()
        ordered_names = [list_widget.item(i).text() for i in range(list_widget.count())]
        path_map = {Path(p).name: p for p in self.files}
        self.files = [path_map[name] for name in ordered_names if name in path_map]
        if self.mode == self.MODE_MERGE:
            self._update_total_duration_display()

    def _on_list_selection_changed(self):
        list_widget = self.get_current_list_widget()
        player_widget, _, _, _ = self._get_current_player_controls()
        selected = list_widget.selectedItems()
        if not selected or not CAN_PLAY_AUDIO:
            if self.audio_preview_player: self.audio_preview_player.stop()
            if player_widget: player_widget.setVisible(False)
            return
        row = list_widget.row(selected[0])
        if 0 <= row < len(self.files):
            path = self.files[row]
            if self.audio_preview_player:
                if self.audio_preview_player.source() != QUrl.fromLocalFile(path):
                    self.audio_preview_player.setSource(QUrl.fromLocalFile(path))
                if player_widget: player_widget.setVisible(True)
    
    def _toggle_duration_widget(self, state):
        is_checked = (state == Qt.CheckState.Checked.value)
        self.duration_container.layout().setCurrentIndex(1 if is_checked else 0)
        if is_checked: self._update_total_duration_display()
            
    def _update_total_duration_display(self):
        if not self.chk_original_duration.isChecked() or not self.files:
            self.total_duration_label.setText("Tổng: 0 phút 0 giây")
            return
        
        if self.duration_worker and self.duration_worker.isRunning(): self.duration_worker.terminate()
        self.total_duration_label.setText("Đang tính toán...")
        self.duration_worker = DurationCalculator(self.files)
        self.duration_worker.finished.connect(lambda sec: self.total_duration_label.setText(f"Tổng: {int(sec // 60)} phút {int(sec % 60)} giây"))
        self.duration_worker.error.connect(lambda err: self.total_duration_label.setText("Lỗi tính toán"))
        self.duration_worker.start()

    def remove_selected_files(self):
        list_widget = self.get_current_list_widget()
        selected = list_widget.selectedItems()
        if not selected: return
        rows = sorted([list_widget.row(item) for item in selected], reverse=True)
        for row in rows: list_widget.takeItem(row); del self.files[row]
        self.update_ui_state()
        if self.mode == self.MODE_MERGE: self._update_total_duration_display()

    def clear_files(self):
        if self.audio_preview_player: self.audio_preview_player.stop()
        player_widget, _, _, _ = self._get_current_player_controls()
        if player_widget: player_widget.setVisible(False)
        self.get_current_list_widget().clear(); self.files.clear(); self.update_ui_state()
        if self.mode == self.MODE_MERGE: self._update_total_duration_display()

    def select_output_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Chọn thư mục", self.output_dir_line.text())
        if directory: self.output_dir_line.setText(directory); self.settings.setValue("outputDir", directory)

    def update_ui_state(self):
        is_running = self.worker and self.worker.isRunning()
        can_run = bool(self.files) and bool(self.output_dir_line.text())
        self.btn_run.setEnabled(can_run and not is_running)
        self.btn_reset.setText("❌ Hủy" if is_running else "❌ Reset")
        self.main_stack.setEnabled(not is_running)
        self.btn_browse_output.setEnabled(not is_running)
        self.btn_mode_merge.setEnabled(not is_running); self.btn_mode_convert.setEnabled(not is_running)

    def handle_cancel_or_reset(self):
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(self, "Xác nhận", "Dừng tác vụ đang chạy?") == QMessageBox.StandardButton.Yes:
                self.worker.cancel()
        else:
            self.clear_files(); self.progress_bar.setValue(0); self.progress_bar.setFormat("Sẵn sàng."); self._load_settings()

    def start_processing(self):
        if self.audio_preview_player: self.audio_preview_player.stop()
        
        # THÊM MỚI: Cảnh báo an toàn
        if self.mode == self.MODE_MERGE and self.chk_original_duration.isChecked():
            reply = QMessageBox.question(self, "Cảnh báo", 
                "Chế độ 'Ghép theo thời lượng gốc' sử dụng phương pháp nối file nhanh, nhưng có thể gây lỗi hoặc văng ứng dụng nếu các file MP3 có thông số kỹ thuật (bitrate, sample rate) khác nhau.\n\nBạn có muốn tiếp tục không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                return

        output_dir = Path(self.output_dir_line.text())
        try:
            test_file = output_dir / f"write_test_{os.urandom(8).hex()}.tmp"
            test_file.touch(); test_file.unlink()
        except (OSError, PermissionError) as e:
            QMessageBox.critical(self, "Lỗi Thư mục", f"Không thể ghi vào thư mục đầu ra:\n{output_dir}\n\nLỗi: {e}"); return
            
        self.settings.setValue("mergeDuration", self.duration_spinbox.value())
        self.settings.setValue("convertFormat", self.format_combo.currentText())
        self.settings.setValue("convertBitrate", self.bitrate_combo.currentText())
        
        data = {'files': self.files, 'duration': self.duration_spinbox.value(), 'use_original_duration': self.chk_original_duration.isChecked(),
                'format': self.format_combo.currentText(), 'bitrate': self.bitrate_combo.currentText(), 'output_dir': self.output_dir_line.text()}

        self.progress_bar.setValue(0); self.progress_bar.setFormat("Đang khởi tạo..."); self.update_ui_state()
        self.worker = FFmpegWorker(self.mode, data)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.processing_finished)
        self.worker.error_signal.connect(self.processing_error)
        self.worker.start()

    def update_progress(self, percentage, message):
        self.progress_bar.setValue(percentage); self.progress_bar.setFormat(f"{percentage}% - {message}")

    def processing_finished(self, output_path, failed_files):
        self.progress_bar.setValue(100); self.progress_bar.setFormat("Hoàn tất!")
        action = "nối" if self.mode == self.MODE_MERGE else "chuyển đổi"
        
        if failed_files:
            msg = f"Đã {action} file hoàn tất nhưng có {len(failed_files)} file lỗi:\n\n" + "\n".join(failed_files)
            QMessageBox.warning(self, "Hoàn tất với lỗi", msg)
        else:
            QMessageBox.information(self, "Hoàn tất", f"Đã {action} file thành công và lưu tại:\n{output_path}")

        self.worker = None; self.update_ui_state()
        try: os.startfile(Path(output_path).parent if Path(output_path).is_file() else output_path)
        except: pass

    def processing_error(self, error_message):
        self.progress_bar.setValue(0); self.progress_bar.setFormat("Đã xảy ra lỗi.")
        error_box = QMessageBox(); error_box.setIcon(QMessageBox.Icon.Critical); error_box.setText("Đã xảy ra lỗi trong quá trình xử lý.")
        error_box.setInformativeText("Vui lòng xem chi tiết bên dưới."); error_box.setDetailedText(str(error_message)); error_box.exec()
        self.worker = None; self.update_ui_state()
    
    def _get_current_player_controls(self):
        if self.mode == self.MODE_MERGE: return self.merge_player_widget, self.merge_slider, self.merge_play_btn, self.merge_time_label
        else: return self.convert_player_widget, self.convert_slider, self.convert_play_btn, self.convert_time_label

    def audio_toggle_play_pause(self):
        if self.audio_preview_player and self.audio_preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.audio_preview_player.pause()
        elif self.audio_preview_player: self.audio_preview_player.play()

    def audio_state_changed(self, state):
        _, _, play_btn, _ = self._get_current_player_controls()
        if play_btn: play_btn.setText("⏸️" if state == QMediaPlayer.PlaybackState.PlayingState else "▶️")

    def audio_position_changed(self, position):
        _, slider, _, time_label = self._get_current_player_controls()
        duration = self.audio_preview_player.duration()
        if slider and not slider.isSliderDown(): slider.setValue(position)
        if time_label: time_label.setText(f"{self.format_ms(position)} / {self.format_ms(duration)}")

    def audio_duration_changed(self, duration):
        _, slider, _, time_label = self._get_current_player_controls()
        position = self.audio_preview_player.position()
        if slider: slider.setRange(0, duration)
        if time_label: time_label.setText(f"{self.format_ms(position)} / {self.format_ms(duration)}")

    def audio_set_position(self, position):
        if self.audio_preview_player: self.audio_preview_player.setPosition(position)
            
    def format_ms(self, ms):
        return QTime(0, 0, 0).addMSecs(int(ms)).toString('mm:ss')
    
    def set_theme(self, theme_name):
        """Set theme for this plugin"""
        if self.theme_manager.set_theme(theme_name):
            self.setStyleSheet(self.theme_manager.get_standard_stylesheet())
            return True
        return False
