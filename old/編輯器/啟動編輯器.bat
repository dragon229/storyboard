@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 分鏡稿編輯器 - http://127.0.0.1:8420

echo ============================================
echo   分鏡稿編輯器
echo   網址： http://127.0.0.1:8420
echo.
echo   關閉這個視窗就會停止伺服器
echo ============================================
echo.

start "" http://127.0.0.1:8420
python storyboard_editor\server.py

echo.
echo 伺服器已停止。按任意鍵關閉視窗...
pause >nul
