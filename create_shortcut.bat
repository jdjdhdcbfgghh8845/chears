@echo off
REM Создание ярлыка для скрытого запуска бота

echo Создаем ярлык для скрытого запуска...

REM Создаем VBScript для создания ярлыка
set "vbs_file=%temp%\create_shortcut.vbs"

(
echo Set objShell = CreateObject^("WScript.Shell"^)
echo Set objDesktop = objShell.SpecialFolders^("Desktop"^)
echo Set objShortcut = objShell.CreateShortcut^(objDesktop ^& "\Telegram Bot ^(Hidden^).lnk"^)
echo objShortcut.TargetPath = "%~dp0start_silent.vbs"
echo objShortcut.WorkingDirectory = "%~dp0"
echo objShortcut.Description = "Запуск Telegram бота в скрытом режиме"
echo objShortcut.IconLocation = "shell32.dll,25"
echo objShortcut.WindowStyle = 7
echo objShortcut.Save
) > "%vbs_file%"

REM Выполняем создание ярлыка
cscript //nologo "%vbs_file%"

REM Удаляем временный файл
del "%vbs_file%" >nul 2>&1

echo.
echo ✅ Ярлык создан на рабочем столе!
echo 📱 Теперь можно запускать бота двойным кликом
echo 👻 Бот будет работать полностью скрыто
echo.
pause
