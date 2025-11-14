' ===============================================
' UNIVERSAL BOT AUTOSTART - Универсальный автозапуск
' Один файл для всего: установка зависимостей + запуск бота
' Автоматически ставится в автозагрузку
' ===============================================

Dim objShell, objFSO, botPath, logPath, startupPath
Dim pythonCmd, requirementsFile, botFile

' Создаем объекты
Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Получаем пути
botPath = objFSO.GetParentFolderName(WScript.ScriptFullName)
logPath = botPath & "\logs"
startupPath = objShell.SpecialFolders("Startup")
requirementsFile = botPath & "\requirements.txt"
botFile = botPath & "\pc_control_bot.py"

' Создаем папку для логов
If Not objFSO.FolderExists(logPath) Then
    objFSO.CreateFolder(logPath)
End If

' Функция логирования
Sub WriteLog(message)
    On Error Resume Next
    Set logFile = objFSO.OpenTextFile(logPath & "\autostart.log", 8, True)
    logFile.WriteLine Now & " - " & message
    logFile.Close
    On Error GoTo 0
End Sub

WriteLog "=== AUTOSTART НАЧАТ ==="

' 1. ПРОВЕРЯЕМ И УСТАНАВЛИВАЕМ PYTHON
WriteLog "Проверяем Python..."

pythonCmd = ""
On Error Resume Next

' Пробуем python
Set objExec = objShell.Exec("python --version")
If Err.Number = 0 And objExec.ExitCode = 0 Then
    pythonCmd = "python"
    WriteLog "Найден python"
Else
    ' Пробуем py
    Set objExec = objShell.Exec("py --version")
    If Err.Number = 0 And objExec.ExitCode = 0 Then
        pythonCmd = "py"
        WriteLog "Найден py"
    End If
End If

On Error GoTo 0

If pythonCmd = "" Then
    WriteLog "ОШИБКА: Python не найден!"
    WScript.Quit 1
End If

' 2. УСТАНАВЛИВАЕМ ЗАВИСИМОСТИ (если нужно)
WriteLog "Проверяем зависимости..."

If objFSO.FileExists(requirementsFile) Then
    WriteLog "Устанавливаем зависимости из requirements.txt..."
    
    ' Устанавливаем зависимости скрыто
    objShell.Run pythonCmd & " -m pip install -r """ & requirementsFile & """", 0, True
    
    WriteLog "Зависимости установлены"
Else
    WriteLog "requirements.txt не найден, пропускаем установку зависимостей"
End If

' 3. ПРОВЕРЯЕМ ФАЙЛ БОТА
If Not objFSO.FileExists(botFile) Then
    WriteLog "ОШИБКА: pc_control_bot.py не найден!"
    WScript.Quit 1
End If

' 4. ПРОВЕРЯЕМ, НЕ ЗАПУЩЕН ЛИ УЖЕ БОТ
WriteLog "Проверяем запущенные процессы..."

Set objWMI = GetObject("winmgmts:")
Set colProcesses = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE CommandLine LIKE '%pc_control_bot.py%'")

If colProcesses.Count > 0 Then
    WriteLog "Бот уже запущен, завершаем"
    WScript.Quit 0
End If

' 5. ДОБАВЛЯЕМ СЕБЯ В АВТОЗАГРУЗКУ (если еще не там)
WriteLog "Проверяем автозагрузку..."

Dim autostartFile
autostartFile = startupPath & "\TelegramBotAutostart.vbs"

If Not objFSO.FileExists(autostartFile) Then
    WriteLog "Добавляем в автозагрузку..."
    objFSO.CopyFile WScript.ScriptFullName, autostartFile, True
    WriteLog "Добавлено в автозагрузку: " & autostartFile
Else
    WriteLog "Уже в автозагрузке"
End If

' 6. ЗАПУСКАЕМ БОТА
WriteLog "Запускаем бота..."

' Устанавливаем рабочую директорию
objShell.CurrentDirectory = botPath

' Запускаем бота полностью скрыто
If pythonCmd = "python" Then
    objShell.Run "pythonw pc_control_bot.py", 0, False
Else
    objShell.Run "pyw pc_control_bot.py", 0, False
End If

WriteLog "Бот запущен успешно!"

' 7. СОЗДАЕМ МАРКЕР УСПЕШНОГО ЗАПУСКА
Set markerFile = objFSO.CreateTextFile(botPath & "\bot_running.tmp", True)
markerFile.WriteLine "Bot started at: " & Now
markerFile.WriteLine "Python command: " & pythonCmd
markerFile.WriteLine "Working directory: " & botPath
markerFile.Close

WriteLog "=== AUTOSTART ЗАВЕРШЕН ==="

' Показываем уведомление (опционально, только при первом запуске)
If Not objFSO.FileExists(botPath & "\first_run_done.tmp") Then
    objShell.Popup "🤖 Telegram Bot запущен!" & vbCrLf & "✅ Добавлен в автозагрузку" & vbCrLf & "👻 Работает скрыто", 3, "Bot Autostart", 64
    
    ' Создаем маркер первого запуска
    Set firstRunFile = objFSO.CreateTextFile(botPath & "\first_run_done.tmp", True)
    firstRunFile.WriteLine "First run completed at: " & Now
    firstRunFile.Close
End If

WScript.Quit 0
