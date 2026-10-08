@echo off
setlocal
cd /d "%~dp0"
title Gerador de Polaroids - PrintHub

set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY (where python >nul 2>nul && set PY=python)
if not defined PY (
  echo.
  echo  Nao achei o Python neste computador.
  echo  Instale em https://www.python.org/downloads/  marcando "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)

%PY% -c "import tkinter" 2>nul
if errorlevel 1 (
  echo.
  echo  O Python deste computador veio sem o tkinter, que desenha a janela.
  echo  Instale o Python de https://www.python.org/downloads/  ^(o da Microsoft Store nao serve^).
  echo.
  pause
  exit /b 1
)

%PY% -c "import PIL, reportlab, numpy, cv2" 2>nul
if errorlevel 1 (
  echo  Primeira vez: instalando o que o programa precisa. Leva um ou dois minutos...
  %PY% -m pip install --disable-pip-version-check -q -r requirements.txt
  if errorlevel 1 (
    echo.
    echo  Nao consegui instalar. Confira a internet e tente de novo.
    pause
    exit /b 1
  )
)

%PY% iniciar.pyw
if errorlevel 1 (
  echo.
  echo  O programa fechou com erro. O detalhe fica em %%APPDATA%%\PrintHub\Gerador de Polaroids
  pause
)
