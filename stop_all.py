#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для полной остановки всех процессов бота
Останавливает бота, watchdog и все связанные процессы
"""

import os
import sys
import psutil
import time
from pathlib import Path

def stop_all_bot_processes():
    """Остановить все процессы бота и watchdog"""
    print("🛑 Остановка всех процессов бота...")
    stopped_count = 0
    
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] in ['python.exe', 'pythonw.exe']:
                    cmdline = proc.info['cmdline']
                    if cmdline:
                        cmdline_str = ' '.join(cmdline)
                        # Останавливаем бота и watchdog
                        if ('pc_control_bot.py' in cmdline_str or 
                            'watchdog.py' in cmdline_str or
                            'run_hidden.pyw' in cmdline_str or
                            'run_watchdog.pyw' in cmdline_str):
                            print(f"⏹️  Завершаю процесс: PID {proc.pid}")
                            proc.terminate()
                            try:
                                proc.wait(timeout=5)
                                stopped_count += 1
                            except psutil.TimeoutExpired:
                                print(f"🔥 Принудительно завершаю процесс: PID {proc.pid}")
                                proc.kill()
                                proc.wait()
                                stopped_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                pass
                
        print(f"✅ Остановлено процессов: {stopped_count}")
        
    except Exception as e:
        print(f"❌ Ошибка остановки процессов: {e}")

def create_stop_signal():
    """Создать сигнал остановки для watchdog"""
    try:
        script_dir = Path(__file__).parent.absolute()
        stop_signal_file = script_dir / "stop_bot.signal"
        
        with open(stop_signal_file, 'w') as f:
            f.write(f"MANUAL_STOP_{time.time()}")
        
        print("📶 Сигнал остановки создан")
        return True
    except Exception as e:
        print(f"❌ Ошибка создания сигнала: {e}")
        return False

def remove_from_autostart():
    """Удалить из автозагрузки Windows"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, "TelegramPCBot")
            winreg.CloseKey(key)
            print("🚀 Удален из автозагрузки Windows")
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            print("ℹ️  Бот не находился в автозагрузке")
            return False
    except ImportError:
        print("⚠️  winreg недоступен - пропускаем удаление из автозагрузки")
        return False
    except Exception as e:
        print(f"❌ Ошибка удаления из автозагрузки: {e}")
        return False

def main():
    print("🛑 Полная остановка Telegram бота для управления ПК")
    print("=" * 50)
    
    # Создаем сигнал остановки
    create_stop_signal()
    
    # Ждем немного для обработки сигнала
    print("⏳ Ожидание обработки сигнала...")
    time.sleep(3)
    
    # Принудительно останавливаем все процессы
    stop_all_bot_processes()
    
    # Удаляем из автозагрузки
    remove_from_autostart()
    
    # Очищаем временные файлы
    try:
        script_dir = Path(__file__).parent.absolute()
        signal_file = script_dir / "stop_bot.signal"
        if signal_file.exists():
            signal_file.unlink()
            print("🧹 Временные файлы очищены")
    except Exception as e:
        print(f"⚠️  Ошибка очистки файлов: {e}")
    
    print("=" * 50)
    print("✅ Все процессы бота остановлены!")
    print("📝 Для запуска используйте start.bat или python pc_control_bot.py")
    
    input("\nНажмите Enter для выхода...")

if __name__ == "__main__":
    main()
