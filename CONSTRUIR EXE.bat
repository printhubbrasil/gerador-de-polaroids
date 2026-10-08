@echo off
setlocal
cd /d "%~dp0"
title Construir o GeradordePolaroids.exe

set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY (where python >nul 2>nul && set PY=python)
if not defined PY (
  echo  Nao achei o Python neste computador. Instale em https://www.python.org/downloads/
  pause
  exit /b 1
)

echo  1/3  Instalando as bibliotecas e o PyInstaller...
%PY% -m pip install --disable-pip-version-check -q -r requirements.txt pyinstaller pymupdf
if errorlevel 1 goto erro

echo  2/3  Testando o motor antes de empacotar...
%PY% testes\rodar.py
if errorlevel 1 (
  echo.
  echo  Os testes falharam - o .exe NAO foi feito. Mande a tela acima pro suporte.
  pause
  exit /b 1
)

echo  3/3  Empacotando (leva alguns minutos)...
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name GeradordePolaroids --icon "%~dp0icone.ico" --add-data "%~dp0icone.ico;." --collect-data cv2 --workpath "%TEMP%\polaroid-build" --specpath "%TEMP%\polaroid-build" --distpath "%~dp0dist" "%~dp0iniciar.pyw"
if errorlevel 1 goto erro

echo.
echo  Pronto! O programa esta em:  %CD%\dist\GeradordePolaroids.exe
echo.
explorer dist
pause
exit /b 0

:erro
echo.
echo  Deu erro no passo acima. Confira a internet e tente de novo.
pause
exit /b 1
