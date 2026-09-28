@echo off
setlocal
cd /d %~dp0

echo [1/3] 安装依赖...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [2/3] 准备图标...
if not exist assets\icon.ico python make_icon.py

echo [3/3] PyInstaller 打包单文件 exe...
python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin ^
  --name HardwareInspector ^
  --icon assets\icon.ico ^
  --version-file version_info.txt ^
  --add-data "assets;assets" ^
  --add-data "src/report/template.html;src/report" ^
  --hidden-import PySide6.QtCharts ^
  --hidden-import PySide6.QtOpenGL ^
  --hidden-import PySide6.QtOpenGLWidgets ^
  --collect-submodules PySide6 ^
  main.py
if errorlevel 1 goto :error

echo.
echo 完成！输出： dist\HardwareInspector.exe
goto :eof

:error
echo 构建失败，请检查上方错误信息。
exit /b 1
