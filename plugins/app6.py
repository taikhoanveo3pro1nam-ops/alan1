# app6.py - Biến Ảnh Thành Video (Hoàn thiện UX, thêm Hủy/Reset, Tối ưu FFmpeg, Thay đổi giao diện thành 4 ô 2x2)

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QSpinBox, QMessageBox, QListWidget, QListWidgetItem, QFrame, QLineEdit,
    QProgressBar, QApplication, QScrollArea, QSizePolicy, QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QSettings
from PyQt6.QtGui import QFont, QIcon, QPixmap, QImage

import subprocess, tempfile, os, shutil
import sys
from pathlib import Path
import time

# Import theme manager
from theme_manager import PluginThemeManager

# --- START: Standard Stylesheet and FFmpeg Path Logic ---

def get_standard_stylesheet():
    return """
        QWidget {
            background-color: #1e1e1e; /* Nền tối thống nhất */
            color: #d6d6d6;
            font-family: 'Segoe UI'; /* Font chữ thống nhất */
            font-size: 14px; /* Cỡ chữ cơ bản thống nhất */
        }
        QLabel { color: #d6d6d6; font-size: 14px; }
        QLabel[objectName=\"titleLabel\"] {
            color: #ffffff;
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 15px;
        }
        QPushButton {
            background-color: #00b894; /* Màu chủ đạo: Teal */
            color: #071717;
            padding: 10px 15px;
            border-radius: 8px;
            font-weight: bold;
            border: none;
        }
        QPushButton:hover { background-color: #00d19a; }
        QLineEdit, QSpinBox, QComboBox, QListWidget {
            background-color: #3a3a3a;
            border: 1px solid #4a4a4a;
            border-radius: 6px;
            padding: 8px;
            color: #e0e0e0;
            font-size: 13px;
        }
        QFrame {
            background-color: #2a2a2a; /* Nền frame */
            border-radius: 8px;
            padding: 10px;
        }
        QProgressBar {
            background-color: #3a3a3a;
            color: #ffffff;
            border-radius: 5px;
            text-align: center;
        }
        QProgressBar::chunk {
            background-color: #00b894; /* Màu tiến trình thống nhất */
            border-radius: 5px;
        }
        /* Custom styling for QSpinBox */
        QSpinBox::up-button, QSpinBox::down-button {
            subcontrol-origin: border;
            width: 20px;
            border-left: 1px solid #4a4a4a;
            background-color: #555555;
        }
        QSpinBox::up-button { subcontrol-position: top right; border-bottom: 1px solid #4a4a4a; border-top-right-radius: 5px; }
        QSpinBox::down-button { subcontrol-position: bottom right; border-bottom-right-radius: 5px; }
        QSpinBox::up-arrow { content: '+'; color: white; font-weight: bold; }
        QSpinBox::down-arrow { content: '-'; color: white; font-weight: bold; }
        QScrollArea { border: none; } /* Đảm bảo thanh cuộn không có viền xấu */
    """

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    # Sửa đường dẫn để trỏ ra thư mục gốc, không phải thư mục plugins
    BASE_DIR = Path(__file__).resolve().parent.parent

FFMPEG_EXE = BASE_DIR / "ffmpeg.exe"

# --- END: Standard Stylesheet and FFmpeg Path Logic ---


# Worker thread for FFmpeg operations
class VideoGenerationWorker(QThread):
    progress_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(list, str) 
    error_signal = pyqtSignal(str)
    cancelled_signal = pyqtSignal()

    def __init__(self, images, duration_sec, temp_dir):
        super().__init__()
        self.images = images
        self.duration_sec = duration_sec
        self.temp_dir = temp_dir
        self.ffmpeg_cmd = [str(FFMPEG_EXE)] if FFMPEG_EXE.exists() else ["ffmpeg"]
        self._is_cancelled = False
        self.current_process = None

    def cancel(self):
        self._is_cancelled = True
        if self.current_process and self.current_process.poll() is None:
            # Gửi tín hiệu hủy cho process FFmpeg đang chạy
            self.current_process.terminate()
            self.current_process.wait()
            self.cancelled_signal.emit()

    def run(self):
        if not self.ffmpeg_cmd:
            self.error_signal.emit("Lỗi: Không tìm thấy FFmpeg (ffmpeg.exe). Vui lòng đặt ffmpeg.exe trong cùng thư mục với ứng dụng hoặc trong biến môi trường PATH.")
            return

        output_videos = []
        try:
            total_images = len(self.images)
            
            # 95% progress là dành cho việc mã hóa, 5% còn lại là cho việc di chuyển/lưu file
            max_encoding_progress = 95 
            
            for i, img_path in enumerate(self.images):
                if self._is_cancelled: break
                
                video_path = Path(img_path) 
                base_name = video_path.stem
                out_path = os.path.join(self.temp_dir, f"{base_name}.mp4")
                
                self.status_signal.emit(f"Đang xử lý ảnh: {os.path.basename(img_path)} ({i+1}/{total_images})")
                
                # --- MÃ NGUỒN GỐC (CPU libx264 -preset veryfast) ---
                cmd = self.ffmpeg_cmd + [
                    "-y", 
                    "-loop", "1", "-i", img_path, 
                    "-t", str(self.duration_sec),
                    # Filter gốc (Sử dụng CPU)
                    "-vf", "scale=iw:-1,setsar=1:1,pad=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p", 
                    # Codec gốc
                    "-c:v", "libx264", 
                    "-preset", "veryfast", "-crf", "23", "-r", "25",
                    out_path
                ]
                # --- END MÃ NGUỒN GỐC ---
                
                self.current_process = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True, 
                    encoding='utf-8', 
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                if self._is_cancelled: 
                    if os.path.exists(out_path): os.remove(out_path)
                    break
                    
                if self.current_process.returncode != 0:
                    error_msg = f"Lỗi FFmpeg khi xử lý ảnh '{os.path.basename(img_path)}':\n{self.current_process.stderr}"
                    raise Exception(error_msg)
                
                output_videos.append(out_path)
                
                # Cập nhật tiến trình chính xác: Progress = (Số ảnh đã làm / Tổng số ảnh) * 95%
                progress_step = (max_encoding_progress / total_images)
                current_progress = int((i + 1) * progress_step)
                self.progress_signal.emit(current_progress)
            
            # Cập nhật tiến trình cuối cùng sau khi hoàn thành mã hóa
            if not self._is_cancelled:
                self.progress_signal.emit(max_encoding_progress)
                self.finished_signal.emit(output_videos, self.temp_dir)
            
        except Exception as e:
            if not self._is_cancelled:
                self.error_signal.emit(str(e))
        finally:
            self.current_process = None


# Sửa tên class thành PluginWidget để tương thích với app.PY
class PluginWidget(QWidget):
    # Thêm thuộc tính để app.PY nhận diện
    PLUGIN_NAME = "Tạo Video từ Ảnh"
    PLUGIN_DESCRIPTION = "Chuyển đổi một hoặc nhiều hình ảnh thành các file video riêng lẻ."

    def __init__(self):
        super().__init__()
        self.current_temp_dir = None 
        self.output_dir = "" 
        self.worker = None 

        # Initialize theme manager
        self.theme_manager = PluginThemeManager()
        self.setStyleSheet(self.theme_manager.get_standard_stylesheet()) 
        
        # Khởi tạo QSettings
        self.settings = QSettings("VideoEditorTool", "App6Settings")
        
        # --- BỌC NỘI DUNG VÀO QScrollArea ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")
        
        content_widget = QWidget()
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)
        
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(30, 30, 30, 30) 
        # ------------------------------------

        # Tiêu đề công cụ
        title_label = QLabel("Tạo ảnh thành Video tĩnh")
        title_label.setObjectName("titleLabel") 
        layout.addWidget(title_label)
        
        # --- BỐ CỤC LƯỚI 2x2 ---
        grid_layout = QGridLayout()
        grid_layout.setSpacing(15) 
        
        # Thiết lập các cột/hàng có độ giãn bằng nhau (để 4 ô bằng nhau)
        grid_layout.setColumnStretch(0, 1)
        grid_layout.setColumnStretch(1, 1)
        grid_layout.setRowStretch(0, 1)
        grid_layout.setRowStretch(1, 1)
        
        # Ô 1 (Trên Trái): HIỂN THỊ ẢNH
        self.image_display_frame = self._create_image_display_widget()
        grid_layout.addWidget(self.image_display_frame, 0, 0)
        
        # Ô 2 (Trên Phải): CHỌN & DANH SÁCH ẢNH
        self.list_images_frame = self._create_list_controls_widget()
        grid_layout.addWidget(self.list_images_frame, 0, 1)

        # Ô 3 (Dưới Trái): CÀI ĐẶT THỜI LƯỢNG VÀ THƯ MỤC LƯU
        self.settings_frame = self._create_settings_widget()
        grid_layout.addWidget(self.settings_frame, 1, 0)
        
        # Ô 4 (Dưới Phải): PROGRESS & NÚT CHẠY
        self.action_status_frame = self._create_action_status_widget()
        grid_layout.addWidget(self.action_status_frame, 1, 1)
        
        layout.addLayout(grid_layout)
        # ------------------------
        
        layout.addStretch()

        self.images_paths = []
        # KẾT NỐI SỰ KIỆN CHỌN HÌNH ẢNH
        self.list_widget_images.itemSelectionChanged.connect(self._on_list_selection_changed)
        
        self._update_run_button_state() 
        self.check_ffmpeg_initial()
        self.ensure_default_output_dir_exists()


    # --- CÁC HÀM HỖ TRỢ TẠO KHUNG GIAO DIỆN MỚI ---
    def _create_frame(self, title):
        frame = QFrame()
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(10, 10, 10, 10)
        
        if title:
             title_label = QLabel(title)
             title_label.setStyleSheet("color: #bfbfbf; font-weight: bold; margin-bottom: 5px;")
             frame_layout.addWidget(title_label)
        
        return frame, frame_layout

    def _create_image_display_widget(self):
        """Ô 1: Hiển thị Hình ảnh được chọn."""
        frame, layout = self._create_frame("Xem trước Hình ảnh")
        frame.setMinimumHeight(250)
        
        self.image_label = QLabel("Chọn một ảnh để xem trước")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: #1a1a1a; border-radius: 4px; border: 1px dashed #4a4a4a;")
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        layout.addWidget(self.image_label, 1)
        
        return frame
        
    def _create_list_controls_widget(self):
        """Ô 2: Danh sách và Nút Thao tác Ảnh."""
        frame, layout = self._create_frame("")
        frame.setMinimumHeight(250)

        description_label = QLabel("Chọn tệp ảnh (PNG, JPG) để tạo thành video.")
        description_label.setStyleSheet("color: #aaaaaa; font-size: 14px;")
        layout.addWidget(description_label)
        
        self.label_selected_images = QLabel("Chưa có ảnh nào được chọn.")
        self.label_selected_images.setStyleSheet("color: #bfbfbf; font-size: 14px; margin-top: 5px;")
        layout.addWidget(self.label_selected_images)
        
        # ListWidget và các nút thêm/xóa
        list_controls_layout = QHBoxLayout()
        self.list_widget_images = QListWidget()
        self.list_widget_images.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list_widget_images.setStyleSheet(self.list_widget_images.styleSheet() + """
            QListWidget::item:selected { background-color: #00b894; color: #071717; }
        """)
        list_controls_layout.addWidget(self.list_widget_images, 1)

        button_col_layout = QVBoxLayout()
        button_col_layout.setSpacing(5)
        button_col_layout.addStretch()

        self.btn_add_image = QPushButton("➕")
        self.btn_add_image.setFixedSize(30, 30)
        self.btn_add_image.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.btn_add_image.setStyleSheet("""
            QPushButton { background-color: #28a745; color: white; border-radius: 5px; padding: 0px; }
            QPushButton:hover { background-color: #218838; }
        """)
        self.btn_add_image.clicked.connect(self._add_images_to_list) 
        button_col_layout.addWidget(self.btn_add_image)

        self.btn_remove_image = QPushButton("➖")
        self.btn_remove_image.setFixedSize(30, 30)
        self.btn_remove_image.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.btn_remove_image.setStyleSheet("""
            QPushButton { background-color: #dc3545; color: white; border-radius: 5px; padding: 0px; }
            QPushButton:hover { background-color: #c82333; }
        """)
        self.btn_remove_image.clicked.connect(self._remove_selected_images)
        self.btn_remove_image.setEnabled(False)
        button_col_layout.addWidget(self.btn_remove_image)
        
        button_col_layout.addStretch()

        list_controls_layout.addLayout(button_col_layout)
        layout.addLayout(list_controls_layout, 1)
        
        self.btn_select_images = QPushButton("Chọn ảnh ban đầu / Xóa và chọn lại") 
        self.btn_select_images.setStyleSheet("""
            QPushButton { background-color: #007bff; color: white; padding: 10px 15px; border-radius: 6px; font-weight: bold; margin-top: 10px; }
            QPushButton:hover { background-color: #0056b3; }
        """)
        self.btn_select_images.clicked.connect(self.select_initial_images)
        layout.addWidget(self.btn_select_images)
        
        return frame

    def _create_settings_widget(self):
        """Ô 3: Cài đặt Thời lượng và Thư mục Lưu."""
        frame, layout = self._create_frame("Cài đặt Video")
        
        # Phần cài đặt thời lượng
        duration_layout = QHBoxLayout()
        
        duration_label = QLabel("Thời lượng mỗi ảnh:")
        duration_label.setStyleSheet("color: #bfbfbf; font-size: 14px;")
        duration_layout.addWidget(duration_label)
        
        self.duration_input = QSpinBox()
        self.duration_input.setRange(1, 60) 
        self.duration_input.setValue(self.settings.value("duration", 5, int))  
        self.duration_input.setSuffix(" giây")
        self.duration_input.valueChanged.connect(lambda val: self.settings.setValue("duration", val))
        duration_layout.addWidget(self.duration_input)
        duration_layout.addStretch()
        layout.addLayout(duration_layout)
        
        layout.addSpacing(10)

        # Phần chọn thư mục đầu ra
        output_dir_label = QLabel("Thư mục lưu video đầu ra:")
        output_dir_label.setStyleSheet("color: #bfbfbf; font-size: 14px;")
        layout.addWidget(output_dir_label)

        output_dir_selector_layout = QHBoxLayout()
        self.output_dir_line_edit = QLineEdit()
        self.output_dir_line_edit.setPlaceholderText("Chọn thư mục lưu...")
        self.output_dir_line_edit.setReadOnly(True) 
        output_dir_selector_layout.addWidget(self.output_dir_line_edit)

        self.btn_select_output_dir = QPushButton("Lưu")
        self.btn_select_output_dir.setFixedSize(60, 35)
        self.btn_select_output_dir.setStyleSheet("""
            QPushButton { background-color: #28a745; color: white; padding: 6px 12px; border-radius: 6px; font-weight: bold; }
            QPushButton:hover { background-color: #5a6268; }
        """)
        self.btn_select_output_dir.clicked.connect(self.select_output_directory)
        output_dir_selector_layout.addWidget(self.btn_select_output_dir)
        layout.addLayout(output_dir_selector_layout)

        layout.addStretch()
        return frame

    def _create_action_status_widget(self):
        """Ô 4: Progress Bar và Nút Chạy/Hủy."""
        frame, layout = self._create_frame("Trạng thái Xử lý")
        
        layout.addStretch()

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Sẵn sàng.")
        self.status_label.setStyleSheet("color: #aaaaaa; font-size: 12px; margin-top: 5px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)


        # Nút chạy và NÚT HỦY
        action_buttons_layout = QHBoxLayout()
        
        self.btn_run = QPushButton("🚀 Bắt Đầu Tạo Video")
        self.btn_run.clicked.connect(self.run)
        self.btn_run.setEnabled(False)
        action_buttons_layout.addWidget(self.btn_run)
        
        self.btn_cancel_reset = QPushButton("❌ Reset")
        self.btn_cancel_reset.setObjectName("ResetButton")
        self.btn_cancel_reset.setStyleSheet("""
            QPushButton { background-color: #dc3545; color: white; padding: 10px 15px; border-radius: 8px; font-weight: bold; }
            QPushButton:hover { background-color: #c82333; }
        """)
        self.btn_cancel_reset.clicked.connect(self.handle_cancel_or_reset)
        action_buttons_layout.addWidget(self.btn_cancel_reset)


        layout.addLayout(action_buttons_layout)
        
        return frame
        
    # --- CÁC HÀM XỬ LÝ ẢNH VÀ LIST ---
    
    def _on_list_selection_changed(self):
        """Xử lý khi mục trong list được chọn để xem trước ảnh."""
        selected_items = self.list_widget_images.selectedItems()
        
        is_running = self.worker and self.worker.isRunning()
        self.btn_remove_image.setEnabled(bool(selected_items) and not is_running)
        
        if not selected_items:
            self.image_label.setText("Chọn một ảnh để xem trước")
            self.image_label.setPixmap(QPixmap()) # Xóa ảnh cũ
            return
            
        # Lấy tên file từ item được chọn
        selected_item = selected_items[0]
        file_name = selected_item.text()
        
        # Tìm đường dẫn đầy đủ
        selected_path = next((path for path in self.images_paths if os.path.basename(path) == file_name), None)

        if selected_path and Path(selected_path).exists():
            self._display_image_preview(selected_path)
        else:
            self.image_label.setText("Lỗi: Không tìm thấy ảnh.")
            self.image_label.setPixmap(QPixmap()) 

    def _display_image_preview(self, image_path):
        """Hiển thị ảnh trong QLabel, đảm bảo nó vừa với khung."""
        try:
            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                self.image_label.setText("Lỗi: Không thể tải ảnh.")
                return

            # Scale pixmap để vừa với QLabel
            scaled_pixmap = pixmap.scaled(self.image_label.size(), 
                                          Qt.AspectRatioMode.KeepAspectRatio, 
                                          Qt.TransformationMode.SmoothTransformation)
            
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.setText("") # Xóa text nếu hiển thị ảnh thành công
            
        except Exception as e:
            self.image_label.setText(f"Lỗi tải ảnh: {e}")
            self.image_label.setPixmap(QPixmap()) 

    def resizeEvent(self, event):
        """Khi widget thay đổi kích thước, cần cập nhật lại ảnh xem trước."""
        super().resizeEvent(event)
        selected_items = self.list_widget_images.selectedItems()
        if selected_items:
            file_name = selected_items[0].text()
            selected_path = next((path for path in self.images_paths if os.path.basename(path) == file_name), None)
            if selected_path:
                self._display_image_preview(selected_path)

    # --- CÁC HÀM XỬ LÝ LỖI VÀ TÁC VỤ (ĐÃ SỬA _remove_selected_images) ---
    def check_ffmpeg_initial(self):
        if not self._check_ffmpeg():
            QMessageBox.critical(self, "Lỗi FFmpeg", 
                                 "Không tìm thấy FFmpeg (ffmpeg.exe).\n"
                                 "Vui lòng đặt ffmpeg.exe trong cùng thư mục với ứng dụng hoặc trong biến môi trường PATH.")
            self.btn_run.setEnabled(False)
            self.output_dir_line_edit.setToolTip("FFmpeg không được tìm thấy.")
        else:
            self.output_dir_line_edit.setToolTip("")

    def _add_images_to_list(self):
        last_dir = self.settings.value("lastImageDir", str(Path.home()), str)
        files, _ = QFileDialog.getOpenFileNames(
            self, 
            "Thêm ảnh", 
            last_dir, 
            "Tệp ảnh (*.png *.jpg *.jpeg);;Tất cả tệp (*.*)"
        )
        if files:
            self.settings.setValue("lastImageDir", os.path.dirname(files[0]))
            for f in files:
                if f not in self.images_paths:
                    self.images_paths.append(f)
                    QListWidgetItem(os.path.basename(f), self.list_widget_images)
            self.label_selected_images.setText(f"Đã chọn {len(self.images_paths)} ảnh:")
            self._update_run_button_state()
            if self.list_widget_images.count() > 0:
                 self.list_widget_images.setCurrentRow(self.list_widget_images.count() - 1)

    def _remove_selected_images(self):
        """
        Xóa ngay lập tức ảnh được chọn.
        """
        selected_items = self.list_widget_images.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Thông báo", "Vui lòng chọn ít nhất một ảnh để xóa.")
            return

        # Lấy danh sách các đường dẫn để xóa từ self.images_paths
        files_to_remove = [item.text() for item in selected_items]
        
        # Xóa từ list widget (phải theo thứ tự từ dưới lên)
        rows_to_remove = [self.list_widget_images.row(item) for item in selected_items]
        rows_to_remove.sort(reverse=True)
        for row in rows_to_remove:
             self.list_widget_images.takeItem(row)
             
        # Cập nhật self.images_paths
        self.images_paths = [path for path in self.images_paths if os.path.basename(path) not in files_to_remove]
        
        self.label_selected_images.setText(f"Đã chọn {len(self.images_paths)} ảnh:")
        self._update_run_button_state()
        self._on_list_selection_changed() # Cập nhật preview


    def select_initial_images(self):
        last_dir = self.settings.value("lastImageDir", str(Path.home()), str)
        files, _ = QFileDialog.getOpenFileNames(
            self, 
            "Chọn ảnh", 
            last_dir, 
            "Tệp ảnh (*.png *.jpg *.jpeg);;Tất cả tệp (*.*)"
        )
        if files:
            self.settings.setValue("lastImageDir", os.path.dirname(files[0]))
            self.images_paths = files
            self.label_selected_images.setText(f"Đã chọn {len(files)} ảnh:")
            self.list_widget_images.clear()
            for f in files:
                QListWidgetItem(os.path.basename(f), self.list_widget_images)
            if self.list_widget_images.count() > 0:
                 self.list_widget_images.setCurrentRow(0)
        else:
            self.images_paths = []
            self.label_selected_images.setText("Chưa có ảnh nào được chọn.")
            self.list_widget_images.clear()
            self.image_label.setText("Chọn một ảnh để xem trước")
            self.image_label.setPixmap(QPixmap()) 
            
        self._update_run_button_state() 

    def select_output_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu video đầu ra", self.output_dir_line_edit.text())
        if directory:
            self.output_dir = directory
            self.output_dir_line_edit.setText(self.output_dir)
            self.settings.setValue("outputDir", self.output_dir)
        else:
            self.output_dir = ""
            self.output_dir_line_edit.setText(self.settings.value("outputDir", str(Path.home() / "Videos" / "VideoEditorTool_App6"), str))
        self._update_run_button_state() 
        
    def ensure_default_output_dir_exists(self):
        """Đặt thư mục đầu ra mặc định là Videos/VideoEditorTool_App6 và tạo nếu chưa có."""
        default_dir = Path.home() / "Videos" / "VideoEditorTool_App6"
        saved_dir = self.settings.value("outputDir", str(default_dir), str)
        self.output_dir = saved_dir
        self.output_dir_line_edit.setText(self.output_dir)
        if not Path(saved_dir).exists():
            try:
                Path(saved_dir).mkdir(parents=True, exist_ok=True)
            except Exception:
                # Fallback nếu không thể tạo thư mục
                self.output_dir = str(Path.home() / "Videos")
                self.output_dir_line_edit.setText(self.output_dir)


    def _update_run_button_state(self):
        """Cập nhật trạng thái kích hoạt của nút Run và Cancel dựa trên các điều kiện."""
        worker_running = self.worker and self.worker.isRunning()
        can_run = bool(self.images_paths) and bool(self.output_dir) and self._check_ffmpeg() and (not worker_running)
        self.btn_run.setEnabled(can_run)
        
        self.btn_cancel_reset.setText("❌ Hủy" if worker_running else "❌ Reset")
        
        is_controls_enabled = not worker_running
        self.btn_add_image.setEnabled(is_controls_enabled)
        self.btn_select_images.setEnabled(is_controls_enabled)
        self.btn_select_output_dir.setEnabled(is_controls_enabled)
        self.duration_input.setEnabled(is_controls_enabled)
        self.btn_remove_image.setEnabled(bool(self.list_widget_images.selectedItems()) and is_controls_enabled)
        self.list_widget_images.setEnabled(is_controls_enabled)
        
        # Cập nhật style nút Run
        if can_run:
            self.btn_run.setStyleSheet("background-color: #00b894; color: #071717; padding: 10px 15px; border-radius: 8px; font-weight: bold; border: none;")
        else:
            self.btn_run.setStyleSheet("background-color: #555555; color: #bbbbbb; padding: 10px 15px; border-radius: 8px; font-weight: bold; border: none;")


    def _check_ffmpeg(self):
        if FFMPEG_EXE.exists():
            return True
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def run(self):
        if not self.images_paths or not self.output_dir or not self._check_ffmpeg():
             return

        self.btn_run.setEnabled(False) 
        self.setCursor(Qt.CursorShape.WaitCursor) 
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Đang khởi tạo...")
        QApplication.processEvents()

        self.current_temp_dir = tempfile.mkdtemp() 
        duration_sec = self.duration_input.value()

        self.worker = VideoGenerationWorker(self.images_paths, duration_sec, self.current_temp_dir)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.status_signal.connect(self.update_status)
        self.worker.finished_signal.connect(self.handle_finished)
        self.worker.error_signal.connect(self.handle_error)
        self.worker.cancelled_signal.connect(self.handle_cancelled)
        self.worker.start()
        
        self._update_run_button_state()

    def handle_cancel_or_reset(self):
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(self, "Xác nhận Hủy", 
                                         "Bạn có chắc chắn muốn hủy tác vụ đang chạy?\nCác file dở dang sẽ bị xóa.", 
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.status_label.setText("Đang yêu cầu hủy tác vụ...")
                self.worker.cancel()
        else:
            self._reset_ui_after_run(self.current_temp_dir)

    def handle_cancelled(self):
        QMessageBox.information(self, "Đã Hủy", "Tác vụ đã được hủy thành công bởi người dùng.")
        self._reset_ui_after_run(self.current_temp_dir)

    def _reset_ui_after_run(self, temp_dir_to_clean):
        # Dọn dẹp thư mục tạm thời
        if temp_dir_to_clean and os.path.exists(temp_dir_to_clean):
            try:
                shutil.rmtree(temp_dir_to_clean)
                self.current_temp_dir = None
            except Exception as e:
                QMessageBox.warning(self, "Dọn dẹp lỗi", f"Không thể xóa thư mục tạm thời '{temp_dir_to_clean}': {e}")

        # Reset các trạng thái UI
        self.worker = None 
        self._update_run_button_state() 
        self.setCursor(Qt.CursorShape.ArrowCursor) 
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Sẵn sàng.")
        
        # Reset các thành phần khác
        self.images_paths = []
        self.list_widget_images.clear()
        self.label_selected_images.setText("Chưa có ảnh nào được chọn.")
        self.image_label.setText("Chọn một ảnh để xem trước")
        self.image_label.setPixmap(QPixmap()) 


    def handle_finished(self, output_videos, temp_dir):
        # --- LOGIC MỚI: CHỈ DI CHUYỂN FILE ---
        self.status_label.setText("Đang hoàn tất và lưu file...")
        self.progress_bar.setValue(98)
        QApplication.processEvents()
        
        successful_moves = 0
        
        try:
            for i, v in enumerate(output_videos):
                final_video_path = Path(self.output_dir) / Path(v).name
                
                # Xử lý trường hợp tên file trùng
                final_output_name = Path(v).name
                counter = 1
                while final_video_path.exists():
                     base_name = Path(final_output_name).stem
                     ext = Path(final_output_name).suffix
                     final_output_name = f"{base_name}({counter}){ext}"
                     final_video_path = Path(self.output_dir) / final_output_name
                     counter += 1
                     
                shutil.move(v, final_video_path)
                successful_moves += 1
            
            self.progress_bar.setValue(100)
            
            if successful_moves > 0:
                QMessageBox.information(self, "Hoàn tất", 
                                        f"Đã tạo {successful_moves} video và lưu tại thư mục:\n{self.output_dir}")
                os.startfile(self.output_dir) 
            else:
                 QMessageBox.warning(self, "Thông báo", "Không có video nào được tạo.")
                 
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Đã xảy ra lỗi trong quá trình lưu file:\n{e}")
        finally:
            self._reset_ui_after_run(temp_dir)

    def handle_error(self, message):
        QMessageBox.critical(self, "Lỗi", f"Đã xảy ra lỗi trong quá trình tạo video:\n{message}")
        self._reset_ui_after_run(self.current_temp_dir)

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_status(self, message):
        # CHỈ HIỂN THỊ CHỮ KHI CHƯA CHẠY XONG
        if self.worker and self.worker.isRunning():
            self.status_label.setText(message)
    
    def set_theme(self, theme_name):
        """Set theme for this plugin"""
        if self.theme_manager.set_theme(theme_name):
            self.setStyleSheet(self.theme_manager.get_standard_stylesheet())
            return True
        return False

# Xóa hàm này để tương thích với app.PY
# def run_tool():
#    return ImageToVideoWidget()
