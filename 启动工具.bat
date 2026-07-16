@echo off
chcp 65001 >nul
title 去水印批量工具
echo.
echo  ================================
echo   去水印批量工具 - 启动中...
echo  ================================
echo.

cd /d "%~dp0"

python server.py
pause
