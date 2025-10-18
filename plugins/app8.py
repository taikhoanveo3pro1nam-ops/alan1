# app8.py - File Sorter and Renamer (FIXED: Data safety, ordering, and revert logic)

import sys
import os
import shutil
import csv
from pathlib import Path
from collections import defaultdict

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QFrame, QLineEdit, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QComboBox,
    QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor

# Import theme manager
from theme_manager import PluginThemeManager

# --- Classification Constants ---
FILE_CATEGORIES = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg"},
    "Videos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"},
    "Audios": {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"},
    "Texts": {".txt", ".md", ".doc", ".docx", ".pdf", ".rtf", ".csv"},
    "Others": set() # Catch-all
}

def get_file_category(file_path):
    ext = Path(file_path).suffix.lower()
    for category, exts in FILE_CATEGORIES.items():
        if ext in exts:
            return category
    return "Others"

# --- Worker for Scanning Files ---
class FileScannerWorker(QThread):
    file_found = pyqtSignal(dict)
    scan_finished = pyqtSignal(int)
    scan_cancelled = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, source_dirs):
        super().__init__()
        self.source_dirs = source_dirs
        self._is_running = True

    def run(self):
        count = 0
        try:
            for source_dir in self.source_dirs:
                if not self._is_running: break
                for root, _, files in os.walk(source_dir):
                    if not self._is_running: break
                    for name in files:
                        if not self._is_running: break
                        file_path = Path(root) / name
                        try:
                            category = get_file_category(file_path)
                            size = file_path.stat().st_size
                            self.file_found.emit({
                                "name": name, "path": str(file_path),
                                "category": category, "size": size
                            })
                            count += 1
                        except FileNotFoundError: continue
        except Exception as e:
            if self._is_running: self.error_occurred.emit(f"Lỗi khi quét file: {e}")
        finally:
            if self._is_running: self.scan_finished.emit(count)
            else: self.scan_cancelled.emit()

    def stop(self): self._is_running = False

# --- Worker for Processing Files ---
class FileProcessorWorker(QThread):
    progress_updated = pyqtSignal(int, str)
    task_succeeded = pyqtSignal(dict)
    processing_finished = pyqtSignal(int, int, str, str)
    processing_cancelled = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, tasks, is_move_mode, delete_source, source_dirs_to_delete):
        super().__init__()
        self.tasks, self.is_move_mode = tasks, is_move_mode
        self.delete_source, self.source_dirs_to_delete = delete_source, source_dirs_to_delete
        self._is_running = True

    def run(self):
        success_count, error_count, dest_dir, del_err = 0, 0, "", ""
        try:
            for i, task in enumerate(self.tasks):
                if not self._is_running: break
                source_path, dest_path = Path(task["source"]), Path(task["destination"])
                dest_dir = str(dest_path.parent.parent); dest_path.parent.mkdir(parents=True, exist_ok=True)
                self.progress_updated.emit(int((i / len(self.tasks)) * 100), f"Đang xử lý {i+1}/{len(self.tasks)}...")
                try:
                    if self.is_move_mode: shutil.move(source_path, dest_path)
                    else: shutil.copy2(source_path, dest_path)
                    success_count += 1
                    self.task_succeeded.emit(task)
                except Exception as e:
                    print(f"Lỗi xử lý {source_path}: {e}"); error_count += 1
            if self._is_running and self.delete_source and error_count == 0:
                self.progress_updated.emit(100, "Đang xóa thư mục nguồn...")
                try:
                    for source_dir in self.source_dirs_to_delete: shutil.rmtree(source_dir)
                except Exception as e:
                    del_err = f"Xử lý file thành công, nhưng không thể xóa thư mục nguồn.\nLỗi: {e}"
        except Exception as e:
            if self._is_running: self.error_occurred.emit(f"Lỗi nghiêm trọng: {e}")
        finally:
            if self._is_running: self.processing_finished.emit(success_count, error_count, dest_dir, del_err)
            else: self.processing_cancelled.emit()

    def stop(self): self._is_running = False

# --- Worker for Reverting Files ---
class FileReverterWorker(QThread):
    progress_updated = pyqtSignal(int, str)
    revert_finished = pyqtSignal(int, int)
    revert_cancelled = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, revert_tasks, was_move_mode):
        super().__init__()
        self.revert_tasks, self.was_move_mode = revert_tasks, was_move_mode
        self._is_running = True

    def run(self):
        success, errors = 0, 0; processed_dirs = set()
        try:
            for i, task in enumerate(self.revert_tasks):
                if not self._is_running: break
                source_original_path, dest_processed_path = Path(task["source"]), Path(task["destination"])
                processed_dirs.add(dest_processed_path.parent)
                self.progress_updated.emit(int((i / len(self.revert_tasks)) * 100), f"Đang hoàn tác {i+1}/{len(self.revert_tasks)}...")
                try:
                    if dest_processed_path.exists():
                        if self.was_move_mode:
                            source_original_path.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(dest_processed_path, source_original_path)
                        else: # Was copy mode, just delete the copy
                            os.remove(dest_processed_path)
                        success += 1
                    else: errors += 1
                except Exception as e:
                    print(f"Lỗi hoàn tác {dest_processed_path}: {e}"); errors += 1
            if self._is_running:
                self.progress_updated.emit(100, "Đang dọn dẹp thư mục rỗng...")
                for directory in sorted(processed_dirs, key=lambda p: len(str(p)), reverse=True):
                    try:
                        if directory.exists() and not any(directory.iterdir()): directory.rmdir()
                    except OSError: continue
        except Exception as e:
            if self._is_running: self.error_occurred.emit(f"Lỗi khi hoàn tác: {e}")
        finally:
            if self._is_running: self.revert_finished.emit(success, errors)
            else: self.revert_cancelled.emit()

    def stop(self): self._is_running = False

# --- Main Application Widget ---
class PluginWidget(QWidget):
    PLUGIN_NAME = "Phân loại & Đổi tên File"
    PLUGIN_DESCRIPTION = "Quét các thư mục, tự động phân loại và đổi tên file theo từng nhóm (Video, Audio, Ảnh, etc.)."

    def __init__(self):
        super().__init__()
        self.source_dirs, self.output_dir, self.worker = [], "", None
        self.file_signatures, self.last_processed_tasks = defaultdict(list), []
        self.last_operation_was_move = False

        main_layout = QHBoxLayout(self); main_layout.setContentsMargins(20, 20, 20, 20)
        # Initialize theme manager
        self.theme_manager = PluginThemeManager()
        self.setStyleSheet(self.theme_manager.get_standard_stylesheet())
        controls_panel = self._create_controls_panel()
        results_panel = self._create_results_panel()
        main_layout.addWidget(controls_panel, 1); main_layout.addWidget(results_panel, 3)
        self._update_all_controls_state()

    def _create_controls_panel(self):
        frame = QFrame(); layout = QVBoxLayout(frame); layout.setSpacing(15)
        title = QLabel("Bảng điều khiển"); title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold)); layout.addWidget(title)
        layout.addWidget(QLabel("1. Chọn thư mục nguồn:"))
        self.btn_select_source = QPushButton("📁 Chọn Nguồn"); self.btn_select_source.clicked.connect(self._select_source_folders)
        self.lbl_source_count = QLabel("Chưa chọn thư mục nào."); layout.addWidget(self.btn_select_source); layout.addWidget(self.lbl_source_count)
        self.btn_scan = QPushButton("🔍 Quét File"); self.btn_scan.clicked.connect(self._start_scan); layout.addWidget(self.btn_scan)
        layout.addSpacing(10); line1 = QFrame(); line1.setFrameShape(QFrame.Shape.HLine); line1.setFrameShadow(QFrame.Shadow.Sunken); layout.addWidget(line1); layout.addSpacing(10)
        layout.addWidget(QLabel("2. Chọn thư mục đích:"))
        output_dir_layout = QHBoxLayout(); self.txt_output_dir = QLineEdit(); self.txt_output_dir.setReadOnly(True); self.txt_output_dir.setPlaceholderText("Nơi lưu file kết quả...")
        self.btn_select_output = QPushButton("📂 Chọn Đích"); self.btn_select_output.clicked.connect(self._select_output_directory)
        output_dir_layout.addWidget(self.txt_output_dir); output_dir_layout.addWidget(self.btn_select_output); layout.addLayout(output_dir_layout)
        layout.addSpacing(10); line2 = QFrame(); line2.setFrameShape(QFrame.Shape.HLine); line2.setFrameShadow(QFrame.Shadow.Sunken); layout.addWidget(line2); layout.addSpacing(10)
        layout.addWidget(QLabel("3. Tùy chọn & Hành động:"))
        self.chk_move_mode = QCheckBox("Di chuyển file (thay vì sao chép)"); self.chk_move_mode.setToolTip("Tùy chọn này sẽ xóa file gốc sau khi xử lý."); layout.addWidget(self.chk_move_mode)
        self.chk_delete_source = QCheckBox("Xóa thư mục nguồn sau khi hoàn tất"); self.chk_delete_source.setToolTip("CẢNH BÁO: Thao tác này sẽ xóa vĩnh viễn thư mục gốc đã chọn!"); layout.addWidget(self.chk_delete_source)
        action_buttons_layout = QHBoxLayout(); self.btn_process = QPushButton("🚀 Bắt đầu"); self.btn_process.clicked.connect(self._start_processing)
        self.btn_stop = QPushButton("🛑 Dừng"); self.btn_stop.clicked.connect(self._stop_worker)
        action_buttons_layout.addWidget(self.btn_process); action_buttons_layout.addWidget(self.btn_stop); layout.addLayout(action_buttons_layout)
        self.btn_reset = QPushButton("🔄 Reset"); self.btn_reset.clicked.connect(self._reset_application); layout.addWidget(self.btn_reset)
        self.btn_revert = QPushButton("↩️ Trả về file gốc"); self.btn_revert.clicked.connect(self._start_revert); layout.addWidget(self.btn_revert)
        layout.addStretch()
        return frame

    def _create_results_panel(self):
        frame = QFrame(); layout = QVBoxLayout(frame); layout.setSpacing(10)
        top_bar_layout = QHBoxLayout(); self.filter_combo = QComboBox(); self.filter_combo.addItems(["Tất cả file", "Images", "Videos", "Audios", "Texts", "Others"]); self.filter_combo.currentIndexChanged.connect(self._filter_table_view)
        self.stats_label = QLabel("Thống kê: | Ảnh: 0 | Video: 0 | Audio: 0 | Text: 0 | Khác: 0")
        top_bar_layout.addWidget(QLabel("Hiển thị:")); top_bar_layout.addWidget(self.filter_combo); top_bar_layout.addStretch(); top_bar_layout.addWidget(self.stats_label); layout.addLayout(top_bar_layout)
        self.table_files = QTableWidget(); self.table_files.setColumnCount(5); self.table_files.setHorizontalHeaderLabels(["Tên File Gốc", "Loại", "Tên Mới (Xem trước)", "Tình Trạng", "Đường Dẫn Gốc"])
        for i, w in enumerate([QHeaderView.ResizeMode.Stretch, QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch, QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.ResizeToContents]): self.table_files.horizontalHeader().setSectionResizeMode(i, w)
        self.table_files.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); layout.addWidget(self.table_files)
        bottom_bar_layout = QHBoxLayout(); self.progress_bar = QProgressBar(); self.progress_bar.setTextVisible(True); self.progress_bar.setFormat("Sẵn sàng")
        self.btn_export_csv = QPushButton("📄 Xuất CSV"); self.btn_export_csv.clicked.connect(self._export_to_csv)
        bottom_bar_layout.addWidget(self.progress_bar, 1); bottom_bar_layout.addWidget(self.btn_export_csv); layout.addLayout(bottom_bar_layout)
        return frame

    def _select_source_folders(self):
        dialog = QFileDialog(self); dialog.setFileMode(QFileDialog.FileMode.Directory); dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        if dialog.exec(): self.source_dirs = dialog.selectedFiles(); self.lbl_source_count.setText(f"Đã chọn {len(self.source_dirs)} thư mục."); self._reset_scan_results()
        self._update_all_controls_state()

    def _select_output_directory(self):
        dialog = QFileDialog(self); dialog.setFileMode(QFileDialog.FileMode.Directory); dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        if dialog.exec(): self.output_dir = dialog.selectedFiles()[0]; self.txt_output_dir.setText(self.output_dir)
        self._update_all_controls_state()

    def _start_scan(self):
        self._reset_scan_results(); self._update_all_controls_state(is_running=True); self.progress_bar.setFormat("Đang quét..."); self.progress_bar.setValue(0)
        self.worker = FileScannerWorker(self.source_dirs); self.worker.file_found.connect(self._add_file_to_table)
        self.worker.scan_finished.connect(self._on_scan_finished); self.worker.scan_cancelled.connect(self._on_task_cancelled)
        self.worker.error_occurred.connect(self._on_error); self.worker.start()

    def _add_file_to_table(self, file_info):
        row = self.table_files.rowCount(); self.table_files.insertRow(row)
        self.table_files.setItem(row, 0, QTableWidgetItem(file_info["name"])); self.table_files.setItem(row, 1, QTableWidgetItem(file_info["category"]))
        self.table_files.setItem(row, 2, QTableWidgetItem("")); self.table_files.setItem(row, 4, QTableWidgetItem(file_info["path"]))
        sig = (file_info["name"], file_info["size"]); status = QTableWidgetItem()
        if sig in self.file_signatures:
            status.setText("Trùng lặp"); [self.table_files.item(row, c).setBackground(QColor(60,20,20)) for c in range(5)]
            if len(self.file_signatures[sig]) == 1:
                orig_row = self.file_signatures[sig][0]; self.table_files.item(orig_row, 3).setText("Trùng lặp"); [self.table_files.item(orig_row, c).setBackground(QColor(60,20,20)) for c in range(5)]
        else: status.setText("OK")
        self.file_signatures[sig].append(row); self.table_files.setItem(row, 3, status)

    def _on_scan_finished(self, count):
        self.progress_bar.setFormat(f"Quét xong! Tìm thấy {count} file."); self.progress_bar.setValue(100)
        if count > 0: self._update_statistics(); self._update_preview()
        self._update_all_controls_state()

    def _start_processing(self):
        if not self.output_dir or not Path(self.output_dir).exists(): QMessageBox.warning(self, "Chưa chọn đích", "Vui lòng chọn thư mục đích."); return
        if self.table_files.rowCount() == 0: QMessageBox.warning(self, "Không có file", "Không có file để xử lý."); return
        
        # --- SAFETY CHECK for duplicate new names before starting ---
        all_new_names = [self.table_files.item(r, 2).text() for r in range(self.table_files.rowCount()) if self.table_files.item(r, 2).text()]
        if len(all_new_names) != len(set(all_new_names)):
            QMessageBox.critical(self, "Lỗi Tên Trùng Lặp", "Phát hiện tên file mới sẽ bị trùng lặp. Vui lòng kiểm tra lại. Hủy tác vụ để tránh mất dữ liệu.")
            return

        if self.chk_delete_source.isChecked():
            reply = QMessageBox.question(self, "XÁC NHẬN HÀNH ĐỘNG NGUY HIỂM", 
                                         "Bạn đã chọn 'Xóa thư mục nguồn'. Thao tác này sẽ **XÓA VĨNH VIỄN** các thư mục gốc sau khi di chuyển file thành công.\n\n"
                                         "Hành động này **KHÔNG THỂ HOÀN TÁC**.\n\nBạn có chắc chắn muốn tiếp tục không?", 
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No: return
        
        self.last_operation_was_move = self.chk_move_mode.isChecked()
        self._update_all_controls_state(is_running=True)
        self.last_processed_tasks.clear()
        tasks = [{"source": self.table_files.item(r, 4).text(), "destination": str(Path(self.output_dir) / self.table_files.item(r, 1).text() / self.table_files.item(r, 2).text())} for r in range(self.table_files.rowCount())]
        self.worker = FileProcessorWorker(tasks, self.chk_move_mode.isChecked(), self.chk_delete_source.isChecked(), self.source_dirs)
        self.worker.progress_updated.connect(lambda val, msg: self.progress_bar.setValue(val) or self.progress_bar.setFormat(msg))
        self.worker.task_succeeded.connect(lambda task: self.last_processed_tasks.append(task))
        self.worker.processing_finished.connect(self._on_processing_finished)
        self.worker.processing_cancelled.connect(self._on_task_cancelled)
        self.worker.error_occurred.connect(self._on_error); self.worker.start()

    def _on_processing_finished(self, success, errors, dest_dir, del_err):
        QMessageBox.information(self, "Hoàn tất", f"Đã xử lý xong!\n- Thành công: {success}\n- Thất bại: {errors}\nLưu tại: {dest_dir}")
        if del_err: QMessageBox.warning(self, "Lỗi Xóa Thư mục", del_err)
        # Disable revert if source was deleted
        if self.chk_delete_source.isChecked(): self.last_processed_tasks.clear()
        self._update_all_controls_state(); self._reset_scan_results()
        
    def _start_revert(self):
        if QMessageBox.question(self, "Xác nhận", "Trả các file vừa xử lý về vị trí gốc?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.No: return
        self._update_all_controls_state(is_running=True)
        self.worker = FileReverterWorker(self.last_processed_tasks, self.last_operation_was_move)
        self.worker.progress_updated.connect(lambda val, msg: self.progress_bar.setValue(val) or self.progress_bar.setFormat(msg))
        self.worker.revert_finished.connect(self._on_revert_finished)
        self.worker.revert_cancelled.connect(self._on_task_cancelled)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.start()

    def _on_revert_finished(self, success, errors):
        QMessageBox.information(self, "Hoàn tất", f"Đã hoàn tác xong!\n- Thành công: {success}\n- Thất bại: {errors}.")
        self.progress_bar.setFormat("Hoàn tác thành công.")
        self.last_processed_tasks.clear(); self._update_all_controls_state()

    def _on_task_cancelled(self):
        self.progress_bar.setFormat("Tác vụ đã được dừng.")
        self._update_all_controls_state()

    def _filter_table_view(self):
        filt = self.filter_combo.currentText()
        for r in range(self.table_files.rowCount()): self.table_files.setRowHidden(r, not (filt == "Tất cả file" or self.table_files.item(r, 1).text() == filt))

    def _update_preview(self):
        all_files_data = [{"row": r, "category": self.table_files.item(r, 1).text(), "original_path": Path(self.table_files.item(r, 4).text())} for r in range(self.table_files.rowCount())]
        counters, cat_map = defaultdict(int), {"Images": "img", "Videos": "vid", "Audios": "aud", "Texts": "txt", "Others": "other"}
        for data in all_files_data:
            cat = data["category"]; counters[cat] += 1; idx = counters[cat]
            try: new_base = f"{cat_map.get(cat, 'file')}_{idx:04d}"; new_name = f"{new_base}{data['original_path'].suffix}"
            except: new_name = "LỖI TÊN"
            self.table_files.item(data["row"], 2).setText(new_name)

    def _export_to_csv(self):
        if self.table_files.rowCount() == 0: return
        path, _ = QFileDialog.getSaveFileName(self, "Lưu CSV", "", "CSV Files (*.csv)")
        if not path: return
        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f); writer.writerow([self.table_files.horizontalHeaderItem(i).text() for i in range(5)])
                for r in range(self.table_files.rowCount()):
                     if not self.table_files.isRowHidden(r): writer.writerow([self.table_files.item(r, i).text() for i in range(5)])
            QMessageBox.information(self, "Thành công", f"Đã xuất ra file:\n{path}")
        except Exception as e: QMessageBox.critical(self, "Lỗi", f"Không thể xuất file CSV: {e}")

    def _on_error(self, message):
        QMessageBox.critical(self, "Lỗi", message); self._update_all_controls_state(); self.progress_bar.setFormat("Lỗi!")

    def _reset_scan_results(self):
        self.table_files.setRowCount(0); self.stats_label.setText("Thống kê: | Ảnh: 0 | Video: 0 | Audio: 0 | Text: 0 | Khác: 0")
        self.file_signatures.clear(); self._update_all_controls_state()

    def _reset_application(self):
        if self.worker and self.worker.isRunning(): self.worker.stop()
        self.source_dirs, self.output_dir, self.last_processed_tasks = [], "", []
        self.txt_output_dir.setText(""); self.lbl_source_count.setText("Chưa chọn thư mục nào.")
        self._reset_scan_results(); self.progress_bar.setValue(0); self.progress_bar.setFormat("Sẵn sàng")

    def _update_statistics(self):
        stats = defaultdict(int)
        for r in range(self.table_files.rowCount()): stats[self.table_files.item(r, 1).text()] += 1
        self.stats_label.setText(f"Ảnh: {stats['Images']} | Video: {stats['Videos']} | Audio: {stats['Audios']} | Text: {stats['Texts']} | Khác: {stats['Others']}")
        
    def _stop_worker(self):
        if self.worker and self.worker.isRunning(): self.worker.stop(); self.progress_bar.setFormat("Đang dừng..."); self.btn_stop.setEnabled(False)

    def _update_all_controls_state(self, is_running=False):
        can_scan = len(self.source_dirs) > 0 and not is_running
        can_process = self.table_files.rowCount() > 0 and bool(self.output_dir) and not is_running
        can_export = self.table_files.rowCount() > 0 and not is_running
        can_revert = len(self.last_processed_tasks) > 0 and not is_running
        for w in [self.btn_select_source, self.btn_select_output, self.chk_move_mode, self.chk_delete_source, self.filter_combo, self.btn_reset]: w.setEnabled(not is_running)
        self.btn_scan.setEnabled(can_scan); self.btn_process.setEnabled(can_process); self.btn_export_csv.setEnabled(can_export); self.btn_revert.setEnabled(can_revert)
        self.btn_stop.setVisible(is_running); self.btn_stop.setEnabled(is_running); self.btn_process.setVisible(not is_running)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning(): self.worker.stop(); self.worker.wait()
        event.accept()
    
    def set_theme(self, theme_name):
        """Set theme for this plugin"""
        if self.theme_manager.set_theme(theme_name):
            self.setStyleSheet(self.theme_manager.get_standard_stylesheet())
            return True
        return False


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = PluginWidget()
    window.setWindowTitle("App8 - File Sorter and Renamer")
    window.resize(1200, 700)
    window.show()
    sys.exit(app.exec())
