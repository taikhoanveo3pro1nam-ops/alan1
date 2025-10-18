# app5.py - Giao diện gốc, màu vàng (ĐÃ CẬP NHẬT)

import sys
import re
import subprocess
from pathlib import Path
import os
import shutil
import math

# Thư viện PyQt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QSpinBox, QComboBox, QMessageBox, QLineEdit, QFrame, QGridLayout, QSizePolicy,
    QProgressBar, QApplication, QSlider, QCheckBox
)
from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal, QTime, QSettings
from PyQt6.QtGui import QFont, QCursor, QMouseEvent

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
    BASE_DIR = Path(__file__).resolve().parent.parent

FFMPEG_EXE = BASE_DIR / "ffmpeg.exe"
FFPROBE_EXE = BASE_DIR / "ffprobe.exe"
# -----------------------------

class VolumeSlider(QSlider):
    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            if self.orientation() == Qt.Orientation.Horizontal:
                value = self.minimum() + (self.maximum() - self.minimum()) * event.pos().x() / self.width()
            else:
                value = self.maximum() - (self.maximum() - self.minimum()) * event.pos().y() / self.height()
            self.setValue(int(value))

class CutVideoWorker(QThread):
    progress_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str, int)
    error_signal = pyqtSignal(str)

    # THAY ĐỔI: Nhận start_seconds và end_seconds thay vì spin_start/spin_end
    def __init__(self, video_path, output_directory, mode, spin_fixed, start_seconds, end_seconds, mute_audio, flip_video):
        super().__init__()
        self.video_path = video_path
        self.output_directory = output_directory
        self.mode = mode
        self.spin_fixed = spin_fixed
        self.start_seconds = start_seconds # Đã là tổng số giây
        self.end_seconds = end_seconds     # Đã là tổng số giây
        self.mute_audio = mute_audio
        self.flip_video = flip_video
        self.ffmpeg_cmd = [str(FFMPEG_EXE)] if FFMPEG_EXE.exists() else ["ffmpeg"]
        self.ffprobe_cmd = [str(FFPROBE_EXE)] if FFPROBE_EXE.exists() else ["ffprobe"]
        self._is_cancelled = False
        self.current_process = None

    def cancel(self):
        self._is_cancelled = True
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=2)
            except: pass

    def get_duration(self, path):
        if not self.ffprobe_cmd: return 0.0
        try:
            result = subprocess.run(
                self.ffprobe_cmd + ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            return float(result.stdout.strip())
        except Exception: return 0.0

    def _build_ffmpeg_command(self, input_path, output_path, start_sec, end_sec):
        cmd = self.ffmpeg_cmd + ["-i", str(input_path)]

        if start_sec is not None:
            cmd.extend(["-ss", str(start_sec)])
        if end_sec is not None:
            cmd.extend(["-to", str(end_sec)])

        video_filters = []
        if self.flip_video:
            video_filters.append("hflip")

        if video_filters:
            cmd.extend(["-vf", ",".join(video_filters)])
            cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"])
        else:
            cmd.extend(["-c:v", "copy"])

        if self.mute_audio:
            cmd.append("-an")
        elif video_filters:
            cmd.extend(["-c:a", "aac", "-b:a", "128k"])
        else:
            cmd.extend(["-c:a", "copy"])

        cmd.extend(["-y", str(output_path)])
        return cmd

    def run(self):
        if not self.ffmpeg_cmd or not self.ffprobe_cmd:
            self.error_signal.emit("Lỗi: Không tìm thấy FFmpeg hoặc FFprobe.")
            return

        video_input_path = Path(self.video_path)
        total_duration = self.get_duration(video_input_path)

        if total_duration == 0:
            self.error_signal.emit("Không thể lấy thời lượng của video. Video có thể bị hỏng.")
            return

        try:
            self.status_signal.emit("Đang khởi tạo tác vụ cắt...")

            if self.mode == "Cắt theo thời lượng cố định":
                sec_per_clip = self.spin_fixed
                if sec_per_clip <= 0:
                    self.error_signal.emit("Thời lượng mỗi clip phải lớn hơn 0 giây.")
                    return

                outputs_count = 0
                clip_count = int(math.ceil(total_duration / sec_per_clip))

                for i in range(clip_count):
                    if self._is_cancelled: return
                    start_sec = i * sec_per_clip
                    end_sec = min((i + 1) * sec_per_clip, total_duration)
                    if start_sec >= end_sec: continue

                    self.status_signal.emit(f"Đang cắt clip {i+1}/{clip_count}...")
                    self.progress_signal.emit(int((i / clip_count) * 95))

                    output_clip_name = f"{video_input_path.stem}_clip_{i+1:03d}.mp4"
                    out_path = Path(self.output_directory) / output_clip_name

                    cmd = self._build_ffmpeg_command(video_input_path, out_path, start_sec, end_sec)

                    subprocess.run(
                        cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW,
                        capture_output=True, text=True, encoding='utf-8', errors='ignore'
                    )
                    outputs_count += 1

                if outputs_count == 0:
                    self.error_signal.emit("Không có clip nào được tạo. Vui lòng kiểm tra lại thời lượng cắt.")
                    return
                self.finished_signal.emit(self.output_directory, outputs_count)

            else: # Cắt từ A đến B
                # THAY ĐỔI: Sử dụng trực tiếp giá trị đã tính toán, không cần nhân 60
                start_sec = self.start_seconds
                end_sec = self.end_seconds
                start_sec = min(start_sec, total_duration)
                end_sec = min(end_sec, total_duration)

                if start_sec >= end_sec:
                    self.error_signal.emit("Khoảng thời gian cắt không hợp lệ hoặc nằm ngoài thời lượng video.")
                    return

                self.status_signal.emit("Đang cắt video...")
                self.progress_signal.emit(30)

                # THAY ĐỔI: Cập nhật tên file output cho rõ ràng hơn
                start_m, start_s = divmod(self.start_seconds, 60)
                end_m, end_s = divmod(self.end_seconds, 60)
                output_clip_name = f"{video_input_path.stem}_cat_{start_m}m{start_s}s_den_{end_m}m{end_s}s.mp4"
                out_path = Path(self.output_directory) / output_clip_name

                trim_duration = end_sec - start_sec

                cmd = self._build_ffmpeg_command(video_input_path, out_path, start_sec, end_sec)

                self._run_ffmpeg_with_progress(cmd, trim_duration, 10, 95, "Đang cắt video...")

                if self._is_cancelled: return

                self.finished_signal.emit(str(out_path), 1)

        except subprocess.CalledProcessError as e:
            self.error_signal.emit(f"Lỗi FFmpeg:\nLệnh: {' '.join(e.cmd)}\nMã lỗi: {e.returncode}\nStderr: {e.stderr.strip()}")
        except Exception as e:
            self.error_signal.emit(f"Đã xảy ra lỗi: {e}")
        finally:
            self.status_signal.emit("Hoàn tất!")

    def _run_ffmpeg_with_progress(self, command, total_duration, start_progress, end_progress, message):
        if self._is_cancelled: return
        self.current_process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, encoding='utf-8', errors='ignore',
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        time_regex = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.\d{2}")

        for line in self.current_process.stderr:
            if self._is_cancelled: break
            match = time_regex.search(line)
            if match:
                h, m, s = map(int, match.groups())
                current_seconds = h * 3600 + m * 60 + s
                if total_duration > 0:
                    step_progress = current_seconds / total_duration
                    overall_progress = int(start_progress + (end_progress - start_progress) * step_progress)
                    self.progress_signal.emit(min(end_progress, overall_progress))
                    self.status_signal.emit(message)

        self.current_process.wait()
        if self._is_cancelled:
            if self.current_process.poll() is None: self.current_process.terminate()
            return

        if self.current_process.returncode != 0:
            error_output = self.current_process.stderr.read()
            raise subprocess.CalledProcessError(self.current_process.returncode, command, stderr=error_output)

        self.progress_signal.emit(end_progress)
        self.status_signal.emit("Đang hoàn tất...")

class PluginWidget(QWidget):
    PLUGIN_NAME = "Cắt Video MP4"
    PLUGIN_DESCRIPTION = "Cắt video thành nhiều đoạn theo thời gian tùy chỉnh hoặc chia đều video."

    def __init__(self):
        super().__init__()
        self.video_path = None; self.worker = None; self.is_muted = False; self.last_volume = 100
        self.settings = QSettings("VideoEditorTool", "App5Settings")

        if CAN_PLAY_VIDEO:
            self.media_player = QMediaPlayer(); self.audio_output = QAudioOutput()
            self.media_player.setAudioOutput(self.audio_output)
        else:
            self.media_player, self.audio_output = None, None

        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #d6d6d6; font-family: 'Segoe UI'; }
            QLabel { font-size: 14px; color: #d6d6d6; }
            QLabel[objectName=\"titleLabel\"] { color: #ffffff; font-size: 20px; font-weight: bold; margin-bottom: 15px; }
            QPushButton { background-color: #dfbb00; color: #071717; padding: 10px 15px; border-radius: 8px; font-weight: bold; font-size: 14px; border: none; }
            QPushButton:hover { background-color: #eccf3f; }
            QPushButton:disabled { background-color: #555555; color: #bbbbbb; }
            QLineEdit, QSpinBox, QComboBox { background-color: #3a3a3a; border: 1px solid #4a4a4a; border-radius: 6px; padding: 8px; color: #d6d6d6; font-size: 13px; }
            QSpinBox::up-button, QSpinBox::down-button { subcontrol-origin: border; width: 20px; border-left: 1px solid #4a4a4a; background-color: #555555; }
            QSpinBox::up-button { subcontrol-position: top right; border-bottom: 1px solid #4a4a4a; border-top-right-radius: 5px; }
            QSpinBox::down-button { subcontrol-position: bottom right; border-bottom-right-radius: 5px; }
            QSpinBox::up-arrow { content: '+'; color: white; font-weight: bold; }
            QSpinBox::down-arrow { content: '-'; color: white; font-weight: bold; }
            QFrame { background-color: #2a2a2a; border-radius: 8px; padding: 10px; }
            QProgressBar { background-color: #3a3a3a; color: #ffffff; border-radius: 5px; text-align: center; }
            QProgressBar::chunk { background-color: #dfbb00; border-radius: 5px; }
            QPushButton#ResetButton { background-color: #dc3545; color: white; }
            QPushButton#ResetButton:hover { background-color: #c82333; }
            QSlider::groove:horizontal { border: none; height: 6px; background: #3a3a3a; margin: 0px 0; border-radius: 3px; }
            QSlider::handle:horizontal { background: #dfbb00; border: none; width: 14px; margin: -4px 0; border-radius: 7px; }
            QSlider#VolumeSlider::groove:horizontal { height: 4px; background: #3a3a3a; border-radius: 2px; }
            QSlider#VolumeSlider::handle:horizontal { background: #d6d6d6; border: none; width: 10px; margin: -3px 0; border-radius: 5px; }
            QPushButton#PlayPauseButton { background-color: transparent; color: #dfbb00; border: none; padding: 0px; font-size: 26px; font-weight: bold; text-align: center; min-width: 30px; max-width: 30px; }
            QPushButton#PlayPauseButton:hover { color: #eccf3f; }
        """)

        layout = QVBoxLayout(); layout.setContentsMargins(30, 30, 30, 30); layout.setSpacing(15); self.setLayout(layout)
        title_label = QLabel("Cắt Video MP4 (Thành nhiều đoạn)"); title_label.setObjectName("titleLabel"); layout.addWidget(title_label)

        grid_layout = QGridLayout(); grid_layout.setSpacing(15); grid_layout.setColumnStretch(0, 1); grid_layout.setColumnStretch(1, 1); grid_layout.setRowStretch(0, 1); grid_layout.setRowStretch(1, 1)

        self.video_player_frame = self._create_video_player_widget(); grid_layout.addWidget(self.video_player_frame, 0, 0)
        self.video_info_frame = self._create_video_info_widget(); grid_layout.addWidget(self.video_info_frame, 0, 1)
        self.cutting_mode_frame = self._create_cutting_mode_widget(); grid_layout.addWidget(self.cutting_mode_frame, 1, 0)
        self.action_status_frame = self._create_action_status_widget(); grid_layout.addWidget(self.action_status_frame, 1, 1)

        layout.addLayout(grid_layout); layout.addStretch()
        self.update_mode_fields(0); self.ensure_default_output_dir_exists(); self.reset_ui_state()

    def _create_video_player_widget(self):
        frame, layout = self._create_frame(""); frame.setMinimumHeight(300)
        if CAN_PLAY_VIDEO:
            self.video_widget = QVideoWidget(); self.video_widget.setStyleSheet("background-color: black; border-radius: 4px;")
            if self.media_player:
                self.media_player.setVideoOutput(self.video_widget); self.media_player.positionChanged.connect(self.position_changed)
                self.media_player.durationChanged.connect(self.duration_changed); self.media_player.playbackStateChanged.connect(self.state_changed)
            layout.addWidget(self.video_widget, 1)

            self.control_panel = QFrame(); self.control_panel.setStyleSheet("QFrame { background-color: transparent; border: none; padding: 0px; }")
            control_layout = QHBoxLayout(self.control_panel); control_layout.setContentsMargins(0, 0, 0, 0); control_layout.setSpacing(5)

            self.play_button = QPushButton("▶️"); self.play_button.setObjectName("PlayPauseButton"); self.play_button.clicked.connect(self.toggle_play_pause); control_layout.addWidget(self.play_button, alignment=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.time_label = QLabel("00:00 / 00:00"); self.time_label.setStyleSheet("font-weight: bold; margin-left: 5px;"); control_layout.addWidget(self.time_label)
            self.position_slider = VolumeSlider(Qt.Orientation.Horizontal); self.position_slider.setRange(0, 0); self.position_slider.sliderMoved.connect(self.set_position); control_layout.addWidget(self.position_slider, 1)

            self.volume_icon = QLabel("🔊"); self.volume_icon.setStyleSheet("font-size: 16px; margin-left: 10px; margin-right: 5px;"); self.volume_icon.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)); self.volume_icon.mousePressEvent = lambda event: self.toggle_mute(event); control_layout.addWidget(self.volume_icon)
            self.volume_slider = VolumeSlider(Qt.Orientation.Horizontal); self.volume_slider.setObjectName("VolumeSlider"); self.volume_slider.setRange(0, 100); self.volume_slider.setValue(100); self.volume_slider.setFixedWidth(80); self.volume_slider.valueChanged.connect(self.set_volume); control_layout.addWidget(self.volume_slider)

            layout.addWidget(self.control_panel); self.control_panel.setVisible(False)
        else:
            self.video_widget = QLabel("⚠️ Cần cài đặt QtMultimedia để xem trước."); self.video_widget.setAlignment(Qt.AlignmentFlag.AlignCenter); self.video_widget.setStyleSheet("background-color: #1a1a1a; padding: 20px; border-radius: 4px; color: #e74c3c; font-weight: bold;"); layout.addWidget(self.video_widget, 1)
            self.play_button, self.position_slider, self.time_label = None, None, None
        return frame

    def toggle_play_pause(self):
        if self.media_player and self.video_path:
            if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState: self.media_player.pause()
            else: self.media_player.play()

    def state_changed(self, state):
        if self.play_button: self.play_button.setText("⏸️" if state == QMediaPlayer.PlaybackState.PlayingState else "▶️")

    def position_changed(self, position):
        if self.position_slider and not self.position_slider.isSliderDown(): self.position_slider.setValue(position)
        if self.time_label: self.time_label.setText(f"{self.format_ms(position)} / {self.format_ms(self.media_player.duration())}")

    def duration_changed(self, duration):
        if self.position_slider: self.position_slider.setRange(0, duration)
        if hasattr(self, 'control_panel'): self.control_panel.setVisible(duration > 0)

    def set_position(self, position):
        if self.media_player: self.media_player.setPosition(position)

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

    def _create_frame(self, title):
        frame = QFrame(); frame_layout = QVBoxLayout(frame); frame_layout.setContentsMargins(10, 10, 10, 10)
        if title:
            title_label = QLabel(title); title_label.setStyleSheet("color: #bfbfbf; font-weight: bold; margin-bottom: 5px;"); frame_layout.addWidget(title_label)
        return frame, frame_layout

    def _create_video_info_widget(self):
        frame, layout = self._create_frame("")
        video_selection_layout = QHBoxLayout(); self.selected_video_display = QLineEdit("Chưa có video nào được chọn"); self.selected_video_display.setReadOnly(True); video_selection_layout.addWidget(self.selected_video_display)
        self.btn_video = QPushButton("Chọn MP4"); self.btn_video.clicked.connect(self.select_video); self.btn_video.setCursor(Qt.CursorShape.PointingHandCursor); self.btn_video.setStyleSheet("background-color: #007bff; color: white; padding: 8px 12px; border-radius: 6px; font-weight: bold;"); video_selection_layout.addWidget(self.btn_video); layout.addLayout(video_selection_layout)
        self.duration_label = QLabel("Thời lượng: Chưa xác định"); self.duration_label.setStyleSheet("color: #2ecc71; font-weight: bold; margin-top: 10px;"); layout.addWidget(self.duration_label)

        options_frame, options_layout = self._create_frame(""); options_layout.setContentsMargins(0, 5, 0, 5)
        self.chk_mute_audio = QCheckBox("Tắt âm thanh"); self.chk_mute_audio.setStyleSheet("color: #d6d6d6;"); options_layout.addWidget(self.chk_mute_audio)
        self.chk_flip_video = QCheckBox("Lật video (Horizontal Flip)"); self.chk_flip_video.setStyleSheet("color: #d6d6d6;"); options_layout.addWidget(self.chk_flip_video)
        layout.addWidget(options_frame); layout.addStretch(); return frame

    def _create_cutting_mode_widget(self):
        frame, layout = self._create_frame("")
        # Cắt theo A-B giờ sẽ là index 1
        self.mode = QComboBox(); self.mode.addItems(["Cắt theo thời lượng cố định", "Cắt từ A đến B"]); self.mode.currentIndexChanged.connect(self.update_mode_fields); layout.addWidget(self.mode)

        self.fixed_duration_container = QWidget(); self.fixed_duration_layout = QVBoxLayout(self.fixed_duration_container); self.fixed_duration_layout.setContentsMargins(0, 5, 0, 5)
        input_layout = QHBoxLayout(); input_layout.addWidget(QLabel("Thời lượng mỗi clip (giây):"))
        self.spin_fixed = QSpinBox(); self.spin_fixed.setRange(1, 3600); self.spin_fixed.setValue(5); self.spin_fixed.valueChanged.connect(self.update_output_count_label); input_layout.addWidget(self.spin_fixed); input_layout.addStretch(); self.fixed_duration_layout.addLayout(input_layout)
        self.output_count_label = QLabel("Số video đầu ra dự kiến: 0"); self.output_count_label.setStyleSheet("color: #f1c40f; font-weight: bold; margin-top: 5px;"); self.fixed_duration_layout.addWidget(self.output_count_label)
        layout.addWidget(self.fixed_duration_container)

        # --- THAY ĐỔI LỚN BẮT ĐẦU TỪ ĐÂY ---
        self.ab_cut_container = QWidget(); self.ab_cut_layout = QVBoxLayout(self.ab_cut_container); self.ab_cut_layout.setContentsMargins(0, 5, 0, 5)

        # -- Hàng cho thời gian bắt đầu --
        start_layout = QHBoxLayout(); start_layout.setSpacing(8)
        start_layout.addWidget(QLabel("Từ:"))
        self.spin_start_min = QSpinBox(); self.spin_start_min.setRange(0, 10000); self.spin_start_min.setValue(0)
        start_layout.addWidget(self.spin_start_min)
        start_layout.addWidget(QLabel("phút"))
        self.spin_start_sec = QSpinBox(); self.spin_start_sec.setRange(0, 59); self.spin_start_sec.setValue(0)
        start_layout.addWidget(self.spin_start_sec)
        start_layout.addWidget(QLabel("giây"))
        start_layout.addStretch()
        self.ab_cut_layout.addLayout(start_layout)

        # -- Hàng cho thời gian kết thúc --
        end_layout = QHBoxLayout(); end_layout.setSpacing(8)
        end_layout.addWidget(QLabel("Đến:"))
        self.spin_end_min = QSpinBox(); self.spin_end_min.setRange(0, 10000); self.spin_end_min.setValue(1)
        end_layout.addWidget(self.spin_end_min)
        end_layout.addWidget(QLabel("phút"))
        self.spin_end_sec = QSpinBox(); self.spin_end_sec.setRange(0, 59); self.spin_end_sec.setValue(0)
        end_layout.addWidget(self.spin_end_sec)
        end_layout.addWidget(QLabel("giây"))
        end_layout.addStretch()
        self.ab_cut_layout.addLayout(end_layout)

        layout.addWidget(self.ab_cut_container); layout.addStretch(); return frame
        # --- THAY ĐỔI LỚN KẾT THÚC TẠI ĐÂY ---

    def _create_action_status_widget(self):
        frame, layout = self._create_frame("")
        output_dir_layout = QHBoxLayout(); self.output_dir_edit = QLineEdit(); self.output_dir_edit.setReadOnly(True); output_dir_layout.addWidget(self.output_dir_edit)
        self.btn_output_dir = QPushButton("Lưu..."); self.btn_output_dir.clicked.connect(self.select_output_directory); self.btn_output_dir.setCursor(Qt.CursorShape.PointingHandCursor); self.btn_output_dir.setStyleSheet("background-color: #28a745; color: white; padding: 8px 12px; border-radius: 6px; font-weight: 500;"); output_dir_layout.addWidget(self.btn_output_dir); layout.addLayout(output_dir_layout)
        self.progress_bar = QProgressBar(); self.progress_bar.setValue(0); self.progress_bar.setFormat("Sẵn sàng."); layout.addWidget(self.progress_bar)
        action_buttons_layout = QHBoxLayout(); self.btn_run = QPushButton("🚀 Bắt Đầu Cắt"); self.btn_run.clicked.connect(self.run); self.btn_run.setCursor(Qt.CursorShape.PointingHandCursor); action_buttons_layout.addWidget(self.btn_run)
        self.btn_reset = QPushButton("❌ Reset"); self.btn_reset.setObjectName("ResetButton"); self.btn_reset.clicked.connect(self.handle_cancel_or_reset); action_buttons_layout.addWidget(self.btn_reset)
        layout.addLayout(action_buttons_layout); return frame

    def reset_ui_state(self):
        if self.worker: self.worker.cancel(); self.worker = None
        if self.media_player: self.media_player.stop()
        self.video_path = None; self.selected_video_display.setText("Chưa có video nào được chọn"); self.duration_label.setText("Thời lượng: Chưa xác định")
        if CAN_PLAY_VIDEO and hasattr(self, 'control_panel'):
            self.control_panel.setVisible(False); self.volume_slider.setValue(100); self.is_muted, self.last_volume = False, 100; self._update_volume_icon(100)
            if self.media_player: self.media_player.setSource(QUrl())
        self.chk_mute_audio.setChecked(False); self.chk_flip_video.setChecked(False)
        self.spin_fixed.setValue(self.settings.value("spinFixed", 5, int))
        
        # THAY ĐỔI: Reset và load giá trị cho cả phút và giây
        self.spin_start_min.setValue(self.settings.value("spinStartMin", 0, int))
        self.spin_start_sec.setValue(self.settings.value("spinStartSec", 0, int))
        self.spin_end_min.setValue(self.settings.value("spinEndMin", 1, int))
        self.spin_end_sec.setValue(self.settings.value("spinEndSec", 0, int))
        
        self.mode.setCurrentIndex(self.settings.value("modeIndex", 0, int))
        self.progress_bar.setValue(0); self.progress_bar.setFormat("Sẵn sàng.")
        self.btn_run.setEnabled(False); self.btn_video.setEnabled(True); self.btn_output_dir.setEnabled(True); self.mode.setEnabled(True)
        self.spin_fixed.setEnabled(True)
        
        # THAY ĐỔI: Enable các spin box mới
        self.spin_start_min.setEnabled(True); self.spin_start_sec.setEnabled(True)
        self.spin_end_min.setEnabled(True); self.spin_end_sec.setEnabled(True)
        
        self.btn_reset.setText("❌ Reset")
        self.setCursor(Qt.CursorShape.ArrowCursor); self.update_output_count_label()

    def select_video(self):
        file, _ = QFileDialog.getOpenFileName(self, "Chọn video", self.settings.value("lastVideoDir", str(Path.home()), str), "Video (*.mp4)")
        if self.media_player: self.media_player.stop()
        if file:
            self.video_path = file; self.settings.setValue("lastVideoDir", os.path.dirname(file)); self.selected_video_display.setText(Path(file).name)
            duration_sec = self._get_video_duration(file)
            if duration_sec > 0:
                self.duration_label.setText(f"Thời lượng: {int(duration_sec//3600):02d}:{int((duration_sec%3600)//60):02d}:{int(duration_sec%60):02d}")
                self.btn_run.setEnabled(True)
                if self.media_player: self.media_player.setSource(QUrl.fromLocalFile(file)); self.media_player.play()
            else:
                self.duration_label.setText("Thời lượng: Lỗi đọc file"); self.btn_run.setEnabled(False)
        else:
            self.video_path = None; self.selected_video_display.setText("Chưa có video nào được chọn"); self.duration_label.setText("Thời lượng: Chưa xác định")
            self.btn_run.setEnabled(False)
            if CAN_PLAY_VIDEO and hasattr(self, 'control_panel'): self.control_panel.setVisible(False)
        self.update_output_count_label()

    def update_output_count_label(self):
        if self.mode.currentIndex() == 0:
            self.settings.setValue("spinFixed", self.spin_fixed.value())
            if not self.video_path: self.output_count_label.setText("Số video đầu ra dự kiến: 0"); return
            duration_sec, clip_duration = self._get_video_duration(self.video_path), self.spin_fixed.value()
            if clip_duration > 0 and duration_sec > 0:
                self.output_count_label.setText(f"Số video đầu ra dự kiến: {int(math.ceil(duration_sec / clip_duration))}")
            else: self.output_count_label.setText("Số video đầu ra dự kiến: 0")
        else: self.output_count_label.setText("")

    def select_output_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Chọn thư mục đầu ra", self.output_dir_edit.text())
        if directory: self.output_dir_edit.setText(directory); self.settings.setValue("outputDir", directory)

    def update_mode_fields(self, index):
        is_fixed_mode = (self.mode.currentIndex() == 0)
        self.fixed_duration_container.setVisible(is_fixed_mode); self.ab_cut_container.setVisible(not is_fixed_mode)
        self.settings.setValue("modeIndex", index); self.update_output_count_label()

    def ensure_default_output_dir_exists(self):
        default_dir_path = Path.home() / "Videos" / "VideoEditorTool_App5"
        saved_dir = self.settings.value("outputDir", str(default_dir_path), str)
        self.output_dir_edit.setText(saved_dir)
        if not Path(saved_dir).exists():
            try: Path(saved_dir).mkdir(parents=True, exist_ok=True)
            except Exception: self.output_dir_edit.setText(str(Path.home()))

    def _get_video_duration(self, path):
        if not FFPROBE_EXE.exists(): return 0.0
        try:
            cmd = [str(FFPROBE_EXE), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", os.path.normpath(path)]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW, encoding='utf-8')
            return float(result.stdout.strip())
        except Exception: return 0.0

    def run(self):
        if not self.video_path or not self.btn_run.isEnabled(): return
        output_directory = self.output_dir_edit.text()
        if not output_directory or not Path(output_directory).is_dir():
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn thư mục đầu ra hợp lệ."); return
        if not (FFMPEG_EXE.exists() and FFPROBE_EXE.exists()):
            QMessageBox.critical(self, "Lỗi FFmpeg", "Không tìm thấy FFmpeg hoặc FFprobe."); return

        mode_text = self.mode.currentText()
        spin_fixed_val = self.spin_fixed.value()
        
        # --- THAY ĐỔI: Tính tổng số giây và lưu cài đặt ---
        start_min_val = self.spin_start_min.value()
        start_sec_val = self.spin_start_sec.value()
        end_min_val = self.spin_end_min.value()
        end_sec_val = self.spin_end_sec.value()

        self.settings.setValue("spinStartMin", start_min_val)
        self.settings.setValue("spinStartSec", start_sec_val)
        self.settings.setValue("spinEndMin", end_min_val)
        self.settings.setValue("spinEndSec", end_sec_val)

        start_total_seconds = (start_min_val * 60) + start_sec_val
        end_total_seconds = (end_min_val * 60) + end_sec_val
        # -----------------------------------------------

        mute_audio, flip_video = self.chk_mute_audio.isChecked(), self.chk_flip_video.isChecked()

        # THAY ĐỔI: Kiểm tra bằng tổng số giây
        if mode_text == "Cắt từ A đến B" and start_total_seconds >= end_total_seconds:
            QMessageBox.warning(self, "Lỗi", "Thời điểm bắt đầu phải nhỏ hơn thời điểm kết thúc."); return
        if self.media_player: self.media_player.stop()

        self.btn_run.setEnabled(False); self.btn_video.setEnabled(False); self.btn_output_dir.setEnabled(False); self.btn_reset.setText("❌ Hủy")
        self.setCursor(Qt.CursorShape.WaitCursor); self.progress_bar.setValue(0); self.progress_bar.setFormat("Đang khởi tạo...")

        # THAY ĐỔI: Truyền tổng số giây vào worker
        self.worker = CutVideoWorker(self.video_path, output_directory, mode_text, spin_fixed_val, start_total_seconds, end_total_seconds, mute_audio, flip_video)
        
        self.worker.progress_signal.connect(self.update_progress); self.worker.status_signal.connect(self.update_status)
        self.worker.finished_signal.connect(self.handle_finished); self.worker.error_signal.connect(self.handle_error); self.worker.start()

    def update_progress(self, value): self.progress_bar.setValue(value)
    def update_status(self, message): self.progress_bar.setFormat(f"{self.progress_bar.value()}% - {message}")

    def handle_finished(self, output_path, count):
        self.progress_bar.setValue(100); self.progress_bar.setFormat("Hoàn thành!"); self.setCursor(Qt.CursorShape.ArrowCursor)
        if count > 1:
            QMessageBox.information(self, "Hoàn tất", f"Đã tạo {count} clip và lưu tại thư mục:\n{output_path}")
        else:
            QMessageBox.information(self, "Hoàn tất", f"Đã cắt video xong và lưu tại:\n{output_path}")
        try: os.startfile(Path(self.output_dir_edit.text()))
        except: pass
        self.reset_ui_state()

    def handle_error(self, message):
        self.progress_bar.setValue(0); self.progress_bar.setFormat("Đã xảy ra lỗi."); self.setCursor(Qt.CursorShape.ArrowCursor)
        QMessageBox.critical(self, "Lỗi Cắt Video", message); self.reset_ui_state()

    def handle_cancel_or_reset(self):
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(self, "Xác nhận Hủy", "Bạn có chắc chắn muốn hủy tác vụ đang chạy?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                self.worker.cancel(); QApplication.processEvents(); self.reset_ui_state(); QMessageBox.information(self, "Đã Hủy", "Tác vụ đã được hủy.")
        else:
            self.reset_ui_state()

    def format_ms(self, ms): return QTime(0, 0, 0).addMSecs(int(ms)).toString('mm:ss')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = PluginWidget()
    main_window.resize(900, 600)
    main_window.show()
    sys.exit(app.exec())
