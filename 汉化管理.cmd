@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if exist "dist\china-maos-legacy-zh-cn-Setup.exe" (
  start "" "dist\china-maos-legacy-zh-cn-Setup.exe"
  exit /b
)
start "" "https://github.com/lingjieheti/china-maos-legacy-zh-cn/releases/latest/download/china-maos-legacy-zh-cn-Setup.exe"
