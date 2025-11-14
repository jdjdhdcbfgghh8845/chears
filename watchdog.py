#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Watchdog для автоматического перезапуска Telegram бота
Следит за работой бота и перезапускает его при сбоях
"""

import os
import sys
import time
import subprocess
import psutil
import logging
from pathlib import Path
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_watchdog.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class BotWatchdog:
    def __init__(self):
        self.script_dir = Path(__file__).parent.absolute()
        self.bot_script = self.script_dir / "pc_control_bot.py"
        self.process = None
        self.restart_count = 0
        self.max_restarts_per_hour = 10
        self.restart_times = []
        
    def is_bot_running(self):
        """Проверить, запущен ли бот"""
        if self.process is None:
            return False
            
        try:
            # Проверяем, существует ли процесс
            if self.process.poll() is None:
                return True
            else:
                logger.warning(f"Процесс бота завершился с кодом: {self.process.returncode}")
                return False
        except Exception as e:
            logger.error(f"Ошибка проверки процесса: {e}")
            return False
    
    def start_bot(self):
        """Запустить бота"""
        try:
            if not self.bot_script.exists():
                logger.error(f"Файл бота не найден: {self.bot_script}")
                return False
            
            # Запускаем бота с оптимизированными параметрами
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'  # Отключаем буферизацию вывода
            env['PYTHONOPTIMIZE'] = '1'    # Включаем оптимизацию Python
            
            self.process = subprocess.Popen([
                sys.executable, 
                str(self.bot_script)
            ], 
            env=env,
            cwd=str(self.script_dir),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
            )
            
            logger.info(f"Бот запущен с PID: {self.process.pid}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска бота: {e}")
            return False
    
    def stop_bot(self):
        """Остановить бота"""
        if self.process:
            try:
                self.process.terminate()
                # Ждем 5 секунд для корректного завершения
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Принудительно завершаем процесс
                    self.process.kill()
                    self.process.wait()
                logger.info("Бот остановлен")
            except Exception as e:
                logger.error(f"Ошибка остановки бота: {e}")
            finally:
                self.process = None
    
    def can_restart(self):
        """Проверить, можно ли перезапустить бота (защита от частых перезапусков)"""
        now = datetime.now()
        # Удаляем старые записи (старше часа)
        self.restart_times = [t for t in self.restart_times if (now - t).seconds < 3600]
        
        if len(self.restart_times) >= self.max_restarts_per_hour:
            logger.warning(f"Превышен лимит перезапусков ({self.max_restarts_per_hour}/час)")
            return False
        return True
    
    def restart_bot(self):
        """Перезапустить бота"""
        if not self.can_restart():
            return False
            
        logger.info("Перезапуск бота...")
        self.stop_bot()
        time.sleep(2)  # Небольшая пауза
        
        if self.start_bot():
            self.restart_count += 1
            self.restart_times.append(datetime.now())
            logger.info(f"Бот перезапущен (перезапуск #{self.restart_count})")
            return True
        else:
            logger.error("Не удалось перезапустить бота")
            return False
    
    def cleanup_old_processes(self):
        """Очистить зависшие процессы бота"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] in ['python.exe', 'pythonw.exe']:
                        cmdline = proc.info['cmdline']
                        if cmdline and 'pc_control_bot.py' in ' '.join(cmdline):
                            if proc.pid != (self.process.pid if self.process else -1):
                                logger.info(f"Завершаю зависший процесс бота: PID {proc.pid}")
                                proc.terminate()
                                proc.wait(timeout=3)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                    pass
        except Exception as e:
            logger.error(f"Ошибка очистки процессов: {e}")
    
    def stop_all_bot_processes(self):
        """Остановить все процессы бота и watchdog"""
        try:
            logger.info("🛑 Остановка всех процессов бота...")
            
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
                                logger.info(f"Завершаю процесс: PID {proc.pid} - {cmdline_str}")
                                proc.terminate()
                                try:
                                    proc.wait(timeout=5)
                                except psutil.TimeoutExpired:
                                    proc.kill()
                                    proc.wait()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                    pass
                    
            logger.info("✅ Все процессы бота остановлены")
            
        except Exception as e:
            logger.error(f"Ошибка остановки процессов: {e}")
    
    def check_stop_signal(self):
        """Проверить сигнал остановки"""
        stop_file = self.script_dir / "stop_bot.signal"
        if stop_file.exists():
            logger.info("🛑 Обнаружен сигнал остановки")
            try:
                stop_file.unlink()  # Удаляем файл-сигнал
            except:
                pass
            self.stop_all_bot_processes()
            return True
        return False
    
    def run(self):
        """Основной цикл watchdog"""
        logger.info("🐕 Watchdog запущен")
        
        # Очищаем старые процессы при запуске
        self.cleanup_old_processes()
        
        # Запускаем бота
        if not self.start_bot():
            logger.error("Не удалось запустить бота при старте")
            return
        
        try:
            while True:
                time.sleep(10)  # Проверяем каждые 10 секунд
                
                # Проверяем сигнал остановки
                if self.check_stop_signal():
                    logger.info("🛑 Получен сигнал остановки, завершаем работу")
                    break
                
                if not self.is_bot_running():
                    logger.warning("Бот не запущен, попытка перезапуска...")
                    
                    if not self.restart_bot():
                        logger.error("Критическая ошибка: не удалось перезапустить бота")
                        time.sleep(60)  # Ждем минуту перед следующей попыткой
                        continue
                
                # Проверяем использование ресурсов
                try:
                    if self.process:
                        proc = psutil.Process(self.process.pid)
                        memory_mb = proc.memory_info().rss / 1024 / 1024
                        cpu_percent = proc.cpu_percent()
                        
                        # Если бот использует слишком много памяти (>500MB), перезапускаем
                        if memory_mb > 500:
                            logger.warning(f"Высокое использование памяти: {memory_mb:.1f}MB, перезапуск...")
                            self.restart_bot()
                            
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    logger.warning("Процесс бота недоступен")
                    
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки")
        except Exception as e:
            logger.error(f"Критическая ошибка watchdog: {e}")
        finally:
            self.stop_bot()
            logger.info("Watchdog остановлен")

if __name__ == "__main__":
    watchdog = BotWatchdog()
    watchdog.run()
