@echo off
rem Dois cliques aqui sobem o back-end e abrem o navegador, sem depender do programa associado ao .py.
title English Assistant
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py run.py
) else (
    python run.py
)
if errorlevel 1 pause
