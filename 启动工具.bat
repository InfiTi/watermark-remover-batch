@echo off
chcp 65001 >nul
title ComfyUI 去水印批量处理工具
echo ========================================
echo   ComfyUI 去水印批量处理工具
echo   正在启动本地服务器...
echo ========================================
echo.
python "%~dp0server.py"
pause
