@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
    py -3 start.py
    goto done
)
where python >nul 2>&1
if not errorlevel 1 (
    python start.py
    goto done
)
echo Python non trovato. Installa Python 3.12 o successivo da:
echo https://www.python.org/downloads/
echo Durante l'installazione abilita "Add Python to PATH".
:done
echo.
echo Se il browser non si apre, leggi il messaggio qui sopra.
pause
