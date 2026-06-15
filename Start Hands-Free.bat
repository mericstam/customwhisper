@echo off
cd /d "C:\repos\customwhisper"
echo Starting WhisperWriter + wake-word listener...
start "WhisperWriter" venv\Scripts\python.exe run.py
start "Wake Listener (say Hey Jarvis)" venv\Scripts\python.exe wake_listener.py
echo.
echo Both started in separate windows.
echo Say "Hey Jarvis" to dictate, or tap Right-Ctrl+Space.
