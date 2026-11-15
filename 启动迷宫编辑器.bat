@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0maze_studio"
title Marble Maze DIY
echo.
echo   Marble Maze DIY   http://127.0.0.1:8000
echo   Close this window to stop the server.
echo.
python server.py --port 8000 --open
if errorlevel 1 (
  echo.
  echo Failed to start. Requires Python 3.10+ and:
  echo     pip install flask trimesh manifold3d numpy scipy pillow vtk
  echo.
  pause
)
