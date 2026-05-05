@echo off
setlocal
echo === TCMSearch build ===

pip install -r requirements.txt
if errorlevel 1 (echo pip failed & exit /b 1)

:: Set UPX folder path here (no trailing backslash)
set UPX_DIR=c:\Program Files (x86)\upx-5.1.1-win64

set UPX_ARG=
if exist "%UPX_DIR%\upx.exe" set UPX_ARG=--upx-dir "%UPX_DIR%"

pyinstaller ^
  --onefile ^
  --noconsole ^
  --name TCMSearch ^
  --icon app.ico ^
  --add-data "app.ico;." ^
  --hidden-import PyQt6.QtCore ^
  --hidden-import PyQt6.QtGui ^
  --hidden-import PyQt6.QtWidgets ^
  --exclude-module PyQt6.QtWebEngine ^
  --exclude-module PyQt6.QtWebEngineWidgets ^
  --exclude-module PyQt6.QtWebEngineCore ^
  --exclude-module PyQt6.QtMultimedia ^
  --exclude-module PyQt6.QtMultimediaWidgets ^
  --exclude-module PyQt6.QtNetwork ^
  --exclude-module PyQt6.QtSql ^
  --exclude-module PyQt6.QtBluetooth ^
  --exclude-module PyQt6.QtPdf ^
  --exclude-module PyQt6.QtPdfWidgets ^
  --exclude-module PyQt6.Qt3DCore ^
  --exclude-module PyQt6.Qt3DRender ^
  --exclude-module PyQt6.Qt3DInput ^
  --exclude-module PyQt6.Qt3DLogic ^
  --exclude-module PyQt6.Qt3DAnimation ^
  --exclude-module PyQt6.Qt3DExtras ^
  --exclude-module PyQt6.QtCharts ^
  --exclude-module PyQt6.QtDataVisualization ^
  --exclude-module PyQt6.QtNfc ^
  --exclude-module PyQt6.QtPositioning ^
  --exclude-module PyQt6.QtRemoteObjects ^
  --exclude-module PyQt6.QtSensors ^
  --exclude-module PyQt6.QtSerialPort ^
  --exclude-module PyQt6.QtTextToSpeech ^
  --exclude-module PyQt6.QtOpenGL ^
  --exclude-module PyQt6.QtOpenGLWidgets ^
  --exclude-module PyQt6.QtTest ^
  --exclude-module PyQt6.QtXml ^
  --exclude-module tkinter ^
  --exclude-module unittest ^
  --exclude-module email ^
  --exclude-module html ^
  --exclude-module http ^
  --exclude-module xml ^
  --exclude-module pydoc ^
  %UPX_ARG% ^
  main.py

if errorlevel 1 (echo Build failed & exit /b 1)

echo.
echo Done: dist\TCMSearch.exe
echo.
echo Size:
for %%F in (dist\TCMSearch.exe) do echo %%~zF bytes
endlocal
