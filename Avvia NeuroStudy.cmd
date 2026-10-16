@echo off
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 goto try_python
py -3 start.py %*
set "STUDY_EXIT_CODE=%errorlevel%"
goto done
:try_python
where python >nul 2>&1
if errorlevel 1 goto missing_python
python start.py %*
set "STUDY_EXIT_CODE=%errorlevel%"
goto done
:missing_python
echo Python non trovato. Installa Python 3.12 o successivo da:
echo https://www.python.org/downloads/
echo Durante l'installazione abilita "Add Python to PATH".
set "STUDY_EXIT_CODE=1"
:done
echo.
echo Se il browser non si apre, leggi il messaggio qui sopra.
if not defined CI pause
exit /b %STUDY_EXIT_CODE%
