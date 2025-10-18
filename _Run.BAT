@echo off
title 10 APP PLUGINS - Tool Runner

echo ==========================================================
echo  DANG KIEM TRA VA CAI DAT CAC THU VIEN CAN THIET...
echo ==========================================================
pip install -r requirements.txt

echo.
echo ==========================================================
echo  KHOI DONG UNG DUNG...
echo ==========================================================
python app.PY

echo.
echo UNG DUNG DA DONG. NHAN PHIM BAT KY DE KET THUC.
pause >nul