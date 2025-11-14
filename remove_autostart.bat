@echo off
echo ===============================================
echo    УДАЛЕНИЕ ИЗ АВТОЗАГРУЗКИ
echo ===============================================
echo.

REM Получаем путь к автозагрузке
for /f "tokens=3*" %%i in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders" /v Startup 2^>nul') do set "startup_path=%%i %%j"

if "%startup_path%"=="" (
    set "startup_path=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
)

echo 🗑️ Удаляем из автозагрузки...
echo 📁 Путь: %startup_path%
echo.

REM Удаляем файл из автозагрузки
if exist "%startup_path%\TelegramBotAutostart.vbs" (
    del "%startup_path%\TelegramBotAutostart.vbs"
    echo ✅ Удалено из автозагрузки!
) else (
    echo ℹ️ Файл в автозагрузке не найден
)

echo.
echo 🛑 Останавливаем текущий процесс бота...

REM Останавливаем процесс бота
taskkill /f /im pythonw.exe 2>nul
taskkill /f /im python.exe 2>nul

echo.
echo ✅ Готово! Бот удален из автозагрузки
echo 🔄 При следующей перезагрузке бот НЕ запустится
echo.
pause
