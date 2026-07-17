@echo off
chcp 65001 >nul
title 视频去水印工具
echo.
echo  ================================
echo   视频去水印工具 - 启动中...
echo  ================================
echo.

cd /d "%~dp0"

python video_server.py
pause
