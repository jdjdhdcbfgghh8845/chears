#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Bot для управления ПК
Автор: Assistant
Оптимизирован для быстрой работы и автоперезапуска
"""

# Оптимизации производительности
import gc
gc.set_threshold(700, 10, 10)  # Оптимизация сборщика мусора

import os
import sys
import subprocess
import psutil
import platform
import socket
import time
import threading
from datetime import datetime
import json
import cv2
import numpy as np
from PIL import ImageGrab, Image
import io
import logging
import requests
try:
    import win32gui
    import win32con
    import win32process
    WINDOWS_AVAILABLE = True
except ImportError:
    WINDOWS_AVAILABLE = False
    print("⚠️ win32gui не установлен. Функции управления окнами недоступны.")

try:
    import winreg
    REGISTRY_AVAILABLE = True
except ImportError:
    REGISTRY_AVAILABLE = False
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Настройка логирования
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Отключаем слишком подробное логирование HTTP запросов
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# Конфигурация
BOT_TOKEN = "7795955454:AAE5x_ZakPn7-FqdaF37T_okRlko8bsRIXM"
ADMIN_ID = 1854451325  # ID администратора (владельца бота)
AUTHORIZED_USERS = [1854451325]  # ID пользователей с доступом
USERS_DB_FILE = "users_db.json"  # Файл для хранения пользователей

class PCControlBot:
    def __init__(self):
        self.app = None
        self.load_users_db()
        
        # Оптимизации для быстрой работы
        self._cache = {}  # Кэш для часто используемых данных
        self._last_sysinfo_time = 0
        self._last_processes_time = 0
        self._cache_timeout = 5  # Кэш на 5 секунд
        
        # Трансляция экрана
        self._stream_active = False
        self._stream_thread = None
        self._stream_chat_id = None
        self._stream_quality = 'medium'  # low, medium, high
        self._last_stream_message_id = None  # ID последнего сообщения с фото
        
        # GitHub браузер
        self._current_github_repo = None
        self._current_github_path = ""
        self._github_cache = {}  # Кэш для GitHub API
        self._file_path_cache = {}  # Кэш для длинных путей к файлам
        
        # Скрытый режим - всё в фоне
        self._stealth_mode = True
        self._editing_file = None  # Файл для редактирования
        
    def load_users_db(self):
        """Загрузить базу пользователей"""
        try:
            if os.path.exists(USERS_DB_FILE):
                with open(USERS_DB_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    global AUTHORIZED_USERS
                    AUTHORIZED_USERS = data.get('authorized_users', [ADMIN_ID])
        except Exception as e:
            logger.error(f"Ошибка загрузки базы пользователей: {e}")
            
    def save_users_db(self):
        """Сохранить базу пользователей"""
        try:
            data = {
                'authorized_users': AUTHORIZED_USERS,
                'last_updated': datetime.now().isoformat()
            }
            with open(USERS_DB_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения базы пользователей: {e}")
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        user_id = update.effective_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await update.message.reply_text("❌ У вас нет прав для использования этого бота!")
            return
            
        keyboard = [
            [InlineKeyboardButton("💻 Системная информация", callback_data="sysinfo")],
            [InlineKeyboardButton("📊 Процессы", callback_data="processes")],
            [InlineKeyboardButton("📁 Файлы", callback_data="files")],
            [InlineKeyboardButton("📸 Скриншот", callback_data="screenshot")],
            [InlineKeyboardButton("🎥 Веб-камера", callback_data="webcam")],
            [InlineKeyboardButton("📺 Трансляция экрана", callback_data="screen_stream")],
            [InlineKeyboardButton("📝 CMD Команды", callback_data="cmd_menu")],
            [InlineKeyboardButton("🐙 GitHub Браузер", callback_data="github_menu")],
            [InlineKeyboardButton("🖥️ Управление окнами", callback_data="windows_management")],
            [InlineKeyboardButton("⚡ Команды", callback_data="commands")]
        ]
        
        # Добавляем кнопки для админа
        if user_id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("👥 Управление пользователями", callback_data="users_management")])
            keyboard.append([InlineKeyboardButton("🚀 Автозагрузка", callback_data="autostart_management")])
            keyboard.append([InlineKeyboardButton("🛑 Остановить бота", callback_data="stop_bot")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🤖 *Бот управления ПК активен!*\n\n"
            "Выберите действие из меню ниже:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопок"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return

        if query.data == "sysinfo":
            await self.system_info(query)
        elif query.data == "processes":
            await self.show_processes(query)
        elif query.data == "files":
            await self.show_files(query)
        elif query.data == "screenshot":
            await self.take_screenshot(query)
        elif query.data == "webcam":
            await self.take_webcam_photo(query)
        elif query.data == "screen_stream":
            await self.show_screen_stream_menu(query)
        elif query.data == "start_stream":
            await self.start_screen_stream(query)
        elif query.data == "stop_stream":
            await self.stop_screen_stream(query)
        elif query.data.startswith("quality_"):
            quality = query.data.split("_")[1]
            await self.change_stream_quality(query, quality)
        elif query.data == "cmd_menu":
            await self.show_cmd_menu(query)
        elif query.data == "write_cmd":
            await self.request_cmd_input(query)
        elif query.data.startswith("quick_cmd_"):
            cmd = query.data.replace("quick_cmd_", "")
            await self.execute_quick_cmd(query, cmd)
        elif query.data.startswith("force_cmd_"):
            cmd = query.data.replace("force_cmd_", "")
            await self.force_execute_cmd(query, cmd)
        elif query.data.startswith("repeat_cmd_"):
            cmd = query.data.replace("repeat_cmd_", "")
            await self.force_execute_cmd(query, cmd)
        elif query.data == "github_menu":
            await self.show_github_menu(query)
        elif query.data == "github_input_url":
            await self.request_github_url(query)
        elif query.data == "github_browse_root":
            if self._current_github_repo:
                await self.browse_github_path(query, "")
            else:
                await query.edit_message_text("❌ Сначала введите GitHub URL!")
        elif query.data.startswith("github_browse_"):
            path = query.data.replace("github_browse_", "")
            await self.browse_github_path(query, path)
        elif query.data.startswith("github_download_pc_"):
            file_path = query.data.replace("github_download_pc_", "")
            await self.download_github_file_to_pc(query, file_path)
        elif query.data.startswith("github_download_"):
            file_path = query.data.replace("github_download_", "")
            await self.download_github_file(query, file_path)
        elif query.data.startswith("open_folder_"):
            folder_path_or_id = query.data.replace("open_folder_", "")
            folder_path = self.get_file_path_from_id(folder_path_or_id)
            await self.open_folder(query, folder_path)
        elif query.data.startswith("file_actions_"):
            file_path_or_id = query.data.replace("file_actions_", "")
            await self.show_file_actions(query, file_path_or_id)
        elif query.data.startswith("run_file_"):
            file_path_or_id = query.data.replace("run_file_", "")
            await self.run_file(query, file_path_or_id)
        elif query.data.startswith("view_file_"):
            file_path_or_id = query.data.replace("view_file_", "")
            await self.view_file(query, file_path_or_id)
        elif query.data.startswith("extract_file_"):
            file_path_or_id = query.data.replace("extract_file_", "")
            await self.extract_file(query, file_path_or_id)
        elif query.data.startswith("edit_file_"):
            file_path_or_id = query.data.replace("edit_file_", "")
            await self.edit_file(query, file_path_or_id)
        elif query.data.startswith("view_image_"):
            file_path_or_id = query.data.replace("view_image_", "")
            await self.view_image(query, file_path_or_id)
        elif query.data.startswith("delete_file_"):
            file_path_or_id = query.data.replace("delete_file_", "")
            await self.delete_file(query, file_path_or_id)
        elif query.data == "save_file_changes":
            await self.save_file_changes_prompt(query)
        elif query.data == "toggle_stealth_mode":
            await self.toggle_stealth_mode(query)
        elif query.data == "main_menu":
            await self.show_main_menu(query)
        elif query.data.startswith("browse_folder_"):
            folder_path_or_id = query.data.replace("browse_folder_", "")
            folder_path = self.get_file_path_from_id(folder_path_or_id)
            await self.browse_folder_contents(query, folder_path)
        elif query.data.startswith("browse_subfolder_"):
            data = query.data.replace("browse_subfolder_", "")
            data = self.get_file_path_from_id(data)
            if "|" in data:
                folder_path, current_path = data.split("|", 1)
                await self.browse_folder_contents(query, folder_path, current_path)
            else:
                await self.browse_folder_contents(query, data)
        elif query.data == "file_explorer":
            await self.show_file_explorer(query)
        elif query.data.startswith("explore_drive_"):
            drive = query.data.replace("explore_drive_", "")
            await self.explore_drive(query, drive)
        elif query.data.startswith("explore_folder_"):
            folder_data = query.data.replace("explore_folder_", "")
            folder_data = self.get_file_path_from_id(folder_data)
            if "|" in folder_data:
                base_path, current_path = folder_data.split("|", 1)
                await self.explore_folder(query, base_path, current_path)
            else:
                await self.explore_folder(query, folder_data)
        elif query.data == "commands":
            await self.show_commands(query)
        elif query.data == "windows_management":
            await self.show_windows_management(query)
        elif query.data == "show_windows":
            await self.show_all_windows(query)
        elif query.data.startswith("close_window_"):
            window_handle = int(query.data.split("_")[-1])
            await self.close_window(query, window_handle)
        elif query.data.startswith("minimize_window_"):
            window_handle = int(query.data.split("_")[-1])
            await self.minimize_window(query, window_handle)
        elif query.data.startswith("maximize_window_"):
            window_handle = int(query.data.split("_")[-1])
            await self.maximize_window(query, window_handle)
        elif query.data == "autostart_management":
            await self.show_autostart_management(query)
        elif query.data == "add_to_autostart":
            await self.add_to_autostart(query)
        elif query.data == "remove_from_autostart":
            await self.remove_from_autostart(query)
        elif query.data == "stop_bot":
            await self.stop_bot_confirm(query)
        elif query.data == "confirm_stop_bot":
            await self.stop_bot_now(query)
        elif query.data == "cancel_stop_bot":
            await self.show_main_menu(query)
        elif query.data == "users_management":
            await self.show_users_management(query)
        elif query.data == "show_users":
            await self.show_all_users(query)
        elif query.data == "main_menu":
            await self.show_main_menu(query)
        elif query.data.startswith("remove_user_"):
            user_to_remove = int(query.data.split("_")[-1])
            await self.remove_user_access(query, user_to_remove)
        elif query.data.startswith("add_user_"):
            await self.add_user_prompt(query)
        elif query.data.startswith("approve_user_"):
            user_to_approve = int(query.data.split("_")[-1])
            await self.approve_user_access(query, user_to_approve)
        elif query.data.startswith("deny_user_"):
            user_to_deny = int(query.data.split("_")[-1])
            await self.deny_user_access(query, user_to_deny)

    async def system_info(self, query):
        """Получить системную информацию (оптимизировано с кэшированием)"""
        try:
            current_time = time.time()
            
            # Проверяем кэш
            if (current_time - self._last_sysinfo_time < self._cache_timeout and 
                'sysinfo' in self._cache):
                await query.edit_message_text(self._cache['sysinfo'], parse_mode='Markdown')
                return
            
            # Основная информация о системе (кэшируем статичные данные)
            if 'static_info' not in self._cache:
                uname = platform.uname()
                boot_time = datetime.fromtimestamp(psutil.boot_time())
                cpu_count = psutil.cpu_count(logical=False)
                cpu_count_logical = psutil.cpu_count(logical=True)
                
                self._cache['static_info'] = {
                    'uname': uname,
                    'boot_time': boot_time,
                    'cpu_count': cpu_count,
                    'cpu_count_logical': cpu_count_logical
                }
            
            static = self._cache['static_info']
            
            # Динамические данные (быстрое получение)
            cpu_freq = psutil.cpu_freq()
            cpu_percent = psutil.cpu_percent(interval=0.1)  # Уменьшаем интервал для скорости
            memory = psutil.virtual_memory()
            
            # Сеть (кэшируем)
            if 'network_info' not in self._cache:
                hostname = socket.gethostname()
                try:
                    ip = socket.gethostbyname(hostname)
                except:
                    ip = 'Недоступен'
                self._cache['network_info'] = {'hostname': hostname, 'ip': ip}
            
            network = self._cache['network_info']
            
            # Диск (только если Windows)
            try:
                disk = psutil.disk_usage('C:' if os.name == 'nt' else '/')
                disk_info = f"💿 *Диск:*\n• Всего: {disk.total // (1024**3)} GB\n• Свободно: {disk.free // (1024**3)} GB\n• Использовано: {(disk.total - disk.free) // (1024**3)} GB\n"
            except:
                disk_info = "💿 *Диск:* Недоступен\n"
            
            info_text = f"""
💻 *Системная информация*

🖥️ *Система:* {static['uname'].system} {static['uname'].release}
🏷️ *Имя ПК:* {static['uname'].node}
⚙️ *Процессор:* {static['uname'].processor[:50]}...
🔄 *Загрузка:* {static['boot_time'].strftime('%Y-%m-%d %H:%M:%S')}

📊 *CPU:*
• Ядра: {static['cpu_count']} физических, {static['cpu_count_logical']} логических
• Частота: {cpu_freq.current:.0f} MHz
• Загрузка: {cpu_percent:.1f}%

💾 *Память:*
• Всего: {memory.total // (1024**3)} GB
• Доступно: {memory.available // (1024**3)} GB
• Использовано: {memory.percent:.1f}%

{disk_info}
🌐 *Сеть:*
• Hostname: {network['hostname']}
• IP: {network['ip']}
            """
            
            # Кэшируем результат
            self._cache['sysinfo'] = info_text
            self._last_sysinfo_time = current_time
            
            await query.edit_message_text(info_text, parse_mode='Markdown')
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка получения системной информации: {str(e)}")

    async def show_processes(self, query):
        """Показать процессы"""
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Сортировка по использованию CPU
            processes.sort(key=lambda x: x['cpu_percent'] or 0, reverse=True)
            
            text = "📊 *Топ процессов по CPU:*\n\n"
            for i, proc in enumerate(processes[:10]):
                text += f"{i+1}. *{proc['name']}* (PID: {proc['pid']})\n"
                text += f"   CPU: {proc['cpu_percent']:.1f}% | RAM: {proc['memory_percent']:.1f}%\n\n"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="processes")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка получения процессов: {str(e)}")

    async def show_files(self, query):
        """Показать файлы в текущей директории"""
        try:
            current_dir = os.getcwd()
            files = os.listdir(current_dir)
            
            # Используем инлайн-код для путей/имен, чтобы избежать ошибок Markdown
            text = f"📁 Файлы в `{current_dir}`:\n\n"
            
            dirs = [f for f in files if os.path.isdir(f)]
            files_list = [f for f in files if os.path.isfile(f)]
            
            # Показываем папки
            for d in dirs[:5]:
                text += f"📂 `{d}`\n"
            
            # Показываем файлы
            for f in files_list[:10]:
                size = os.path.getsize(f)
                text += f"📄 `{f}` ({size} bytes)\n"
            
            if len(dirs) > 5 or len(files_list) > 10:
                text += f"\n... и еще {len(dirs) + len(files_list) - 15} элементов"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="files")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка получения файлов: {str(e)}")

    async def take_screenshot(self, query):
        """Сделать скриншот"""
        try:
            await query.edit_message_text("📸 Делаю скриншот...")
            
            # Делаем скриншот
            screenshot = ImageGrab.grab()
            
            # Сохраняем в буфер
            bio = io.BytesIO()
            screenshot.save(bio, format='PNG')
            bio.seek(0)
            
            # Отправляем
            await query.message.reply_photo(
                photo=bio,
                caption=f"📸 Скриншот от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            await query.delete_message()
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка создания скриншота: {str(e)}")

    async def take_webcam_photo(self, query):
        """Сделать фото с веб-камеры"""
        try:
            await query.edit_message_text("🎥 Делаю фото с веб-камеры...")
            
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                await query.edit_message_text("❌ Веб-камера недоступна!")
                return
            
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                await query.edit_message_text("❌ Не удалось сделать фото!")
                return
            
            # Конвертируем в PIL Image
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            
            # Сохраняем в буфер
            bio = io.BytesIO()
            pil_image.save(bio, format='JPEG')
            bio.seek(0)
            
            # Отправляем
            await query.message.reply_photo(
                photo=bio,
                caption=f"🎥 Фото с веб-камеры от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            await query.delete_message()
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка работы с веб-камерой: {str(e)}")

    async def show_commands(self, query):
        """Показать доступные команды"""
        commands_text = """
⚡ *Доступные команды:*

💻 */sysinfo* - системная информация
📊 */processes* - список процессов
📁 */files* - файлы в текущей папке
📸 */screenshot* - сделать скриншот
🎥 */webcam* - фото с веб-камеры
🔄 */restart* - перезагрузить ПК
⚡ */shutdown* - выключить ПК
💤 */sleep* - режим сна
🔒 */lock* - заблокировать экран
📝 */cmd [команда]* - выполнить команду
🔍 */find [файл]* - найти файл
📂 */cd [путь]* - сменить директорию
        """
        
        keyboard = [
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(commands_text, parse_mode='Markdown', reply_markup=reply_markup)

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений как CMD команд"""
        user_id = update.effective_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await update.message.reply_text("❌ У вас нет прав!")
            return
            
        command = update.message.text.strip()
        
        # Проверяем, если редактируем файл
        if self._editing_file:
            await self.save_file_content(update, command)
            return
        
        # Проверяем, что это GitHub URL
        if 'github.com' in command.lower():
            await self.handle_github_url_message(update, command)
            return
        
        # Проверяем, что это похоже на CMD команду
        cmd_indicators = ['dir', 'cd', 'ls', 'ping', 'ipconfig', 'netstat', 'tasklist', 'systeminfo', 'wmic', 'echo', 'type', 'copy', 'move', 'del', 'md', 'rd']
        
        # Проверяем первое слово команды
        first_word = command.split()[0].lower() if command.split() else ''
        
        if first_word in cmd_indicators or '\\' in command or ':' in command:
            # Это похоже на CMD команду, выполняем
            await self.execute_text_command(update, command)
        else:
            # Обычное сообщение, показываем подсказку
            keyboard = [
                [InlineKeyboardButton("📝 CMD Меню", callback_data="cmd_menu")],
                [InlineKeyboardButton("🅰️ Выполнить как команду", callback_data=f"force_cmd_{command[:50]}")],
                [InlineKeyboardButton("🅰️ Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"🤔 *Не понял, это CMD команда?*\n\n"
                f"💬 Ваше сообщение: `{command}`\n\n"
                f"📝 Если это CMD команда - нажмите кнопку ниже.",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

    async def execute_text_command(self, update, command):
        """Выполнить текстовую команду"""
        # Отправляем сообщение о выполнении
        status_msg = await update.message.reply_text(
            f"⏳ Выполняю команду: `{command}`",
            parse_mode='Markdown'
        )
        
        try:
            import subprocess
            
            if self._stealth_mode:
                # Скрытое выполнение без окон
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    encoding='cp866',  # Для Windows кодировки
                    startupinfo=startupinfo
                )
            else:
                # Обычное выполнение
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    encoding='cp866'  # Для Windows кодировки
                )
            
            output = result.stdout
            if result.stderr:
                output += f"\n\n❌ Ошибки:\n{result.stderr}"
                
            if not output.strip():
                output = "ℹ️ Команда выполнена, но не вернула результат."
            
            # Ограничиваем длину вывода
            if len(output) > 4000:
                output = output[:4000] + "\n\n... (вывод обрезан)"
                
            keyboard = [
                [InlineKeyboardButton("📝 CMD Меню", callback_data="cmd_menu")],
                [InlineKeyboardButton("🆕 Повторить", callback_data=f"repeat_cmd_{command[:50]}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await status_msg.edit_text(
                f"📝 *Результат команды:* `{command}`\n\n```\n{output}\n```",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
        except subprocess.TimeoutExpired:
            keyboard = [[InlineKeyboardButton("📝 CMD Меню", callback_data="cmd_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await status_msg.edit_text(
                f"⏰ Команда `{command}` превысила лимит времени (30 сек).",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as e:
            keyboard = [[InlineKeyboardButton("📝 CMD Меню", callback_data="cmd_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await status_msg.edit_text(
                f"❌ Ошибка выполнения команды: {str(e)}",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

    async def force_execute_cmd(self, query, command):
        """Принудительно выполнить команду через callback"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        await query.edit_message_text(
            f"⏳ Выполняю команду: `{command}`",
            parse_mode='Markdown'
        )
        
        try:
            import subprocess
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                encoding='cp866'  # Для Windows кодировки
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\n\n❌ Ошибки:\n{result.stderr}"
                
            if not output.strip():
                output = "ℹ️ Команда выполнена, но не вернула результат."
            
            # Ограничиваем длину вывода
            if len(output) > 4000:
                output = output[:4000] + "\n\n... (вывод обрезан)"
                
            keyboard = [
                [InlineKeyboardButton("⬅️ Назад", callback_data="cmd_menu")],
                [InlineKeyboardButton("🆕 Повторить", callback_data=f"repeat_cmd_{command[:50]}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"📝 *Результат команды:* `{command}`\n\n```\n{output}\n```",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
        except subprocess.TimeoutExpired:
            keyboard = [[
                InlineKeyboardButton("⬅️ Назад", callback_data="cmd_menu")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"⏰ Команда `{command}` превысила лимит времени (30 сек).",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as e:
            keyboard = [[
                InlineKeyboardButton("⬅️ Назад", callback_data="cmd_menu")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"❌ Ошибка выполнения команды: {str(e)}",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

    async def execute_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выполнить системную команду"""
        user_id = update.effective_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await update.message.reply_text("❌ У вас нет прав!")
            return
        
        if not context.args:
            await update.message.reply_text("❌ Укажите команду для выполнения!")
            return
        
        command = ' '.join(context.args)
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            output = result.stdout if result.stdout else result.stderr
            if not output:
                output = "Команда выполнена успешно (без вывода)"
            
            # Ограничиваем длину вывода
            if len(output) > 4000:
                output = output[:4000] + "\n... (вывод обрезан)"
            
            await update.message.reply_text(f"```\n{output}\n```", parse_mode='Markdown')
            
        except subprocess.TimeoutExpired:
            await update.message.reply_text("❌ Команда выполняется слишком долго!")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка выполнения команды: {str(e)}")

    async def shutdown_pc(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выключить ПК"""
        user_id = update.effective_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await update.message.reply_text("❌ У вас нет прав!")
            return
        
        await update.message.reply_text("⚡ Выключаю ПК через 10 секунд...")
        os.system("shutdown /s /t 10")

    async def restart_pc(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Перезагрузить ПК"""
        user_id = update.effective_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await update.message.reply_text("❌ У вас нет прав!")
            return
        
        await update.message.reply_text("🔄 Перезагружаю ПК через 10 секунд...")
        os.system("shutdown /r /t 10")

    async def sleep_pc(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Режим сна"""
        user_id = update.effective_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await update.message.reply_text("❌ У вас нет прав!")
            return
        
        await update.message.reply_text("💤 Переводу ПК в режим сна...")
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")

    async def lock_pc(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Заблокировать ПК"""
        user_id = update.effective_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await update.message.reply_text("❌ У вас нет прав!")
            return
        
        await update.message.reply_text("🔒 Блокирую ПК...")
        os.system("rundll32.exe user32.dll,LockWorkStation")

    async def show_users_management(self, query):
        """Показать меню управления пользователями"""
        user_id = query.from_user.id
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Только администратор может управлять пользователями!")
            return
            
        keyboard = [
            [InlineKeyboardButton("👥 Показать всех пользователей", callback_data="show_users")],
            [InlineKeyboardButton("➕ Добавить пользователя", callback_data="add_user_prompt")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = f"""
👥 *Управление пользователями*

👤 *Администратор:* {ADMIN_ID}
📊 *Всего пользователей:* {len(AUTHORIZED_USERS)}

Выберите действие:
        """
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    async def show_all_users(self, query):
        """Показать всех пользователей"""
        user_id = query.from_user.id
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Нет прав доступа!")
            return
            
        text = "👥 *Список пользователей:*\n\n"
        
        keyboard = []
        for i, user_id_in_list in enumerate(AUTHORIZED_USERS):
            if user_id_in_list == ADMIN_ID:
                text += f"{i+1}. `{user_id_in_list}` - 👑 *Администратор*\n"
            else:
                text += f"{i+1}. `{user_id_in_list}` - 👤 Пользователь\n"
                keyboard.append([InlineKeyboardButton(f"❌ Удалить {user_id_in_list}", callback_data=f"remove_user_{user_id_in_list}")])
        
        keyboard.append([InlineKeyboardButton("➕ Добавить пользователя", callback_data="add_user_prompt")])
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="users_management")])
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    async def add_user_prompt(self, query):
        """Просьба ввести ID пользователя"""
        user_id = query.from_user.id
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Нет прав доступа!")
            return
            
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад", callback_data="users_management")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = """
➕ *Добавление пользователя*

Отправьте команду:
`/adduser [ID пользователя]`

📝 *Пример:* `/adduser 123456789`

📌 *Как узнать ID:*
1. Попросите пользователя написать @userinfobot
2. Или попросите написать команду `/request_access`
        """
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    async def remove_user_access(self, query, user_to_remove):
        """Удалить доступ пользователя"""
        user_id = query.from_user.id
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Нет прав доступа!")
            return
            
        if user_to_remove == ADMIN_ID:
            await query.edit_message_text("❌ Нельзя удалить администратора!")
            return
            
        if user_to_remove in AUTHORIZED_USERS:
            AUTHORIZED_USERS.remove(user_to_remove)
            self.save_users_db()
            await query.edit_message_text(f"✅ Пользователь `{user_to_remove}` удален из списка доступа!", parse_mode='Markdown')
        else:
            await query.edit_message_text(f"❌ Пользователь `{user_to_remove}` не найден!", parse_mode='Markdown')

    async def show_main_menu(self, query):
        """Показать главное меню"""
        user_id = query.from_user.id
        
        stealth_status = "🕵️ Скрытый" if self._stealth_mode else "👁️ Обычный"
        
        keyboard = [
            [InlineKeyboardButton("💻 Системная информация", callback_data="sysinfo")],
            [InlineKeyboardButton("📊 Процессы", callback_data="processes")],
            [InlineKeyboardButton("📁 Файлы", callback_data="files")],
            [InlineKeyboardButton("📸 Скриншот", callback_data="screenshot")],
            [InlineKeyboardButton("🎥 Веб-камера", callback_data="webcam")],
            [InlineKeyboardButton("📺 Трансляция экрана", callback_data="screen_stream")],
            [InlineKeyboardButton("📝 CMD Команды", callback_data="cmd_menu")],
            [InlineKeyboardButton("🐙 GitHub Браузер", callback_data="github_menu")],
            [InlineKeyboardButton("📁 File Explorer", callback_data="file_explorer")],
            [InlineKeyboardButton("🖥️ Управление окнами", callback_data="windows_management")],
            [InlineKeyboardButton("⚡ Команды", callback_data="commands")],
            [InlineKeyboardButton(f"{stealth_status} Режим", callback_data="toggle_stealth_mode")]
        ]
        
        if user_id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("👥 Управление пользователями", callback_data="users_management")])
            keyboard.append([InlineKeyboardButton("🚀 Автозагрузка", callback_data="autostart_management")])
            keyboard.append([InlineKeyboardButton("🛑 Остановить бота", callback_data="stop_bot")])
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🤖 *Бот управления ПК активен!*\n\n"
            "Выберите действие из меню ниже:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    async def add_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для добавления пользователя"""
        user_id = update.effective_user.id
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ Только администратор может добавлять пользователей!")
            return
            
        if not context.args:
            await update.message.reply_text("❌ Укажите ID пользователя!\n\n📝 *Пример:* `/adduser 123456789`", parse_mode='Markdown')
            return
            
        try:
            new_user_id = int(context.args[0])
            
            if new_user_id in AUTHORIZED_USERS:
                await update.message.reply_text(f"ℹ️ Пользователь `{new_user_id}` уже имеет доступ!", parse_mode='Markdown')
                return
                
            AUTHORIZED_USERS.append(new_user_id)
            self.save_users_db()
            
            await update.message.reply_text(f"✅ Пользователь `{new_user_id}` добавлен в список доступа!\n\n📊 *Всего пользователей:* {len(AUTHORIZED_USERS)}", parse_mode='Markdown')
            
        except ValueError:
            await update.message.reply_text("❌ Некорректный ID пользователя! ID должен быть числом.")

    async def request_access_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для запроса доступа"""
        user_id = update.effective_user.id
        username = update.effective_user.username or "Не указан"
        first_name = update.effective_user.first_name or "Не указан"
        
        if user_id in AUTHORIZED_USERS:
            await update.message.reply_text("✅ У вас уже есть доступ к боту!")
            return
            
        # Отправляем запрос админу
        try:
            keyboard = [
                [InlineKeyboardButton("✅ Разрешить", callback_data=f"approve_user_{user_id}")],
                [InlineKeyboardButton("❌ Отклонить", callback_data=f"deny_user_{user_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            admin_message = f"""
🔔 *Запрос доступа к боту*

👤 *Пользователь:* {first_name}
🏷️ *Username:* @{username}
🆔 *ID:* `{user_id}`
🕰️ *Время:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            
            await self.app.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_message,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
            await update.message.reply_text(
                f"📨 *Запрос отправлен!*\n\n"
                f"Ваш ID: `{user_id}`\n"
                f"Запрос отправлен администратору. Ожидайте одобрения.",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка отправки запроса: {str(e)}")

    async def approve_user_access(self, query, user_to_approve):
        """Одобрить запрос доступа"""
        user_id = query.from_user.id
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Нет прав доступа!")
            return
            
        if user_to_approve not in AUTHORIZED_USERS:
            AUTHORIZED_USERS.append(user_to_approve)
            self.save_users_db()
            
            # Уведомляем пользователя
            try:
                await self.app.bot.send_message(
                    chat_id=user_to_approve,
                    text=f"✅ *Доступ одобрен!*\n\nВаш запрос на доступ к боту был одобрен.\nНапишите /start для начала работы.",
                    parse_mode='Markdown'
                )
            except Exception:
                pass  # Пользователь мог заблокировать бота
            
            await query.edit_message_text(
                f"✅ *Запрос одобрен!*\n\n"
                f"👤 Пользователь `{user_to_approve}` добавлен в список доступа.\n"
                f"📊 *Всего пользователей:* {len(AUTHORIZED_USERS)}",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(f"ℹ️ Пользователь `{user_to_approve}` уже имеет доступ!", parse_mode='Markdown')

    async def deny_user_access(self, query, user_to_deny):
        """Отклонить запрос доступа"""
        user_id = query.from_user.id
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Нет прав доступа!")
            return
            
        # Уведомляем пользователя
        try:
            await self.app.bot.send_message(
                chat_id=user_to_deny,
                text=f"❌ *Запрос отклонен*\n\nВаш запрос на доступ к боту был отклонен администратором.",
                parse_mode='Markdown'
            )
        except Exception:
            pass  # Пользователь мог заблокировать бота
        
        await query.edit_message_text(
            f"❌ *Запрос отклонен*\n\n"
            f"👤 Пользователю `{user_to_deny}` отказано в доступе.",
            parse_mode='Markdown'
        )

    def get_window_list(self):
        """Получить список всех окон"""
        if not WINDOWS_AVAILABLE:
            return []
            
        windows = []
        
        def enum_windows_callback(hwnd, windows_list):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                window_title = win32gui.GetWindowText(hwnd)
                if window_title and len(window_title.strip()) > 0:
                    try:
                        # Получаем информацию о процессе
                        _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                        process = psutil.Process(process_id)
                        process_name = process.name()
                        
                        windows_list.append({
                            'hwnd': hwnd,
                            'title': window_title,
                            'process_name': process_name,
                            'process_id': process_id
                        })
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        windows_list.append({
                            'hwnd': hwnd,
                            'title': window_title,
                            'process_name': 'Неизвестно',
                            'process_id': 0
                        })
            return True
        
        try:
            win32gui.EnumWindows(enum_windows_callback, windows)
        except Exception as e:
            logger.error(f"Ошибка получения списка окон: {e}")
            
        return windows

    async def show_windows_management(self, query):
        """Показать меню управления окнами"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        if not WINDOWS_AVAILABLE:
            await query.edit_message_text(
                "❌ *Функции управления окнами недоступны*\n\n"
                "Для работы с окнами необходимо установить:\n"
                "`pip install pywin32`",
                parse_mode='Markdown'
            )
            return
            
        windows = self.get_window_list()
        
        keyboard = [
            [InlineKeyboardButton("🖥️ Показать все окна", callback_data="show_windows")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = f"""
🖥️ *Управление окнами*

📊 *Открыто окон:* {len(windows)}

Выберите действие:
        """
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    async def show_all_windows(self, query):
        """Показать все открытые окна"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        if not WINDOWS_AVAILABLE:
            await query.edit_message_text("❌ Функции управления окнами недоступны!")
            return
            
        windows = self.get_window_list()
        
        if not windows:
            await query.edit_message_text("ℹ️ Открытые окна не найдены.")
            return
            
        text = "🖥️ *Открытые окна:*\n\n"
        keyboard = []
        
        # Показываем первые 10 окон
        for i, window in enumerate(windows[:10]):
            title = window['title'][:30] + '...' if len(window['title']) > 30 else window['title']
            process_name = window['process_name']
            
            text += f"{i+1}. *{title}*\n"
            text += f"   💻 {process_name} (PID: {window['process_id']})\n\n"
            
            # Кнопки для каждого окна
            window_buttons = [
                InlineKeyboardButton(f"❌ Закрыть {i+1}", callback_data=f"close_window_{window['hwnd']}"),
                InlineKeyboardButton(f"➖ Свернуть {i+1}", callback_data=f"minimize_window_{window['hwnd']}"),
                InlineKeyboardButton(f"➕ Развернуть {i+1}", callback_data=f"maximize_window_{window['hwnd']}")
            ]
            keyboard.append(window_buttons)
        
        if len(windows) > 10:
            text += f"\n... и еще {len(windows) - 10} окон"
        
        keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="show_windows")])
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="windows_management")])
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    async def close_window(self, query, window_handle):
        """Закрыть окно"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        if not WINDOWS_AVAILABLE:
            await query.edit_message_text("❌ Функции управления окнами недоступны!")
            return
            
        try:
            window_title = win32gui.GetWindowText(window_handle)
            if win32gui.IsWindow(window_handle):
                win32gui.PostMessage(window_handle, win32con.WM_CLOSE, 0, 0)
                await query.edit_message_text(
                    f"✅ *Окно закрыто!*\n\n"
                    f"🖥️ Окно: `{window_title}`",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ Окно не найдено или уже закрыто.")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка закрытия окна: {str(e)}")

    async def minimize_window(self, query, window_handle):
        """Свернуть окно"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        if not WINDOWS_AVAILABLE:
            await query.edit_message_text("❌ Функции управления окнами недоступны!")
            return
            
        try:
            window_title = win32gui.GetWindowText(window_handle)
            if win32gui.IsWindow(window_handle):
                win32gui.ShowWindow(window_handle, win32con.SW_MINIMIZE)
                await query.edit_message_text(
                    f"➖ *Окно свернуто!*\n\n"
                    f"🖥️ Окно: `{window_title}`",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ Окно не найдено.")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка свертывания окна: {str(e)}")

    async def maximize_window(self, query, window_handle):
        """Развернуть окно"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        if not WINDOWS_AVAILABLE:
            await query.edit_message_text("❌ Функции управления окнами недоступны!")
            return
            
        try:
            window_title = win32gui.GetWindowText(window_handle)
            if win32gui.IsWindow(window_handle):
                win32gui.ShowWindow(window_handle, win32con.SW_MAXIMIZE)
                win32gui.SetForegroundWindow(window_handle)  # Переводим окно на передний план
                await query.edit_message_text(
                    f"➕ *Окно развернуто!*\n\n"
                    f"🖥️ Окно: `{window_title}`",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ Окно не найдено.")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка развертывания окна: {str(e)}")

    def is_in_autostart(self):
        """Проверить, находится ли бот в автозагрузке"""
        if not REGISTRY_AVAILABLE:
            return False
            
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, "TelegramPCBot")
                winreg.CloseKey(key)
                return True
            except FileNotFoundError:
                winreg.CloseKey(key)
                return False
        except Exception:
            return False

    async def show_autostart_management(self, query):
        """Показать меню управления автозагрузкой"""
        user_id = query.from_user.id
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Только администратор может управлять автозагрузкой!")
            return
            
        if not REGISTRY_AVAILABLE:
            await query.edit_message_text(
                "❌ *Функции автозагрузки недоступны*\n\n"
                "Не удалось импортировать winreg.",
                parse_mode='Markdown'
            )
            return
            
        is_enabled = self.is_in_autostart()
        status_text = "✅ Включена" if is_enabled else "❌ Отключена"
        
        keyboard = []
        if is_enabled:
            keyboard.append([InlineKeyboardButton("❌ Удалить из автозагрузки", callback_data="remove_from_autostart")])
        else:
            keyboard.append([InlineKeyboardButton("✅ Добавить в автозагрузку", callback_data="add_to_autostart")])
            
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = f"""
🚀 *Управление автозагрузкой*

📊 *Статус:* {status_text}

📝 *Возможности:*
🐕 Автоперезапуск при сбоях
⚡ Оптимизированная работа
🔇 Скрытый режим (без консоли)
🛡️ Мониторинг ресурсов
        """
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    async def add_to_autostart(self, query):
        """Добавить бота в автозагрузку"""
        user_id = query.from_user.id
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Нет прав доступа!")
            return
            
        if not REGISTRY_AVAILABLE:
            await query.edit_message_text("❌ Функции автозагрузки недоступны!")
            return
            
        try:
            # Путь к скрипту watchdog для автоперезапуска
            script_dir = os.path.dirname(os.path.abspath(__file__))
            watchdog_script = os.path.join(script_dir, "run_watchdog.pyw")
            
            if not os.path.exists(watchdog_script):
                await query.edit_message_text("❌ Файл run_watchdog.pyw не найден!")
                return
            
            # Команда для запуска watchdog без консоли
            python_exe = sys.executable.replace("python.exe", "pythonw.exe")
            if not os.path.exists(python_exe):
                python_exe = sys.executable
            
            command = f'"{python_exe}" "{watchdog_script}"'
            
            # Добавляем в реестр
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "TelegramPCBot", 0, winreg.REG_SZ, command)
            winreg.CloseKey(key)
            
            keyboard = [
                [InlineKeyboardButton("⬅️ Назад", callback_data="autostart_management")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"✅ *Бот добавлен в автозагрузку!*\n\n"
                f"🚀 Теперь бот будет автоматически запускаться при старте Windows\n\n"
                f"🐕 *Watchdog активен:* Автоперезапуск при сбоях\n"
                f"⚡ *Оптимизация:* Ускоренная работа\n"
                f"🔇 *Скрытый режим:* Без консоли\n\n"
                f"📝 *Команда:* `{command}`",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
        except Exception as e:
            keyboard = [
                [InlineKeyboardButton("⬅️ Назад", callback_data="autostart_management")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"❌ Ошибка добавления в автозагрузку: {str(e)}", reply_markup=reply_markup)

    async def remove_from_autostart(self, query):
        """Удалить бота из автозагрузки"""
        user_id = query.from_user.id
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Нет прав доступа!")
            return
            
        if not REGISTRY_AVAILABLE:
            await query.edit_message_text("❌ Функции автозагрузки недоступны!")
            return
            
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            try:
                winreg.DeleteValue(key, "TelegramPCBot")
                winreg.CloseKey(key)
                
                keyboard = [
                    [InlineKeyboardButton("⬅️ Назад", callback_data="autostart_management")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"✅ *Бот удален из автозагрузки!*\n\n"
                    f"❌ Бот больше не будет автоматически запускаться при старте Windows.",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
                
            except FileNotFoundError:
                winreg.CloseKey(key)
                keyboard = [
                    [InlineKeyboardButton("⬅️ Назад", callback_data="autostart_management")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("ℹ️ Бот не находится в автозагрузке.", reply_markup=reply_markup)
                
        except Exception as e:
            keyboard = [
                [InlineKeyboardButton("⬅️ Назад", callback_data="autostart_management")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"❌ Ошибка удаления из автозагрузки: {str(e)}", reply_markup=reply_markup)

    async def stop_bot_confirm(self, query):
        """Показать подтверждение остановки бота"""
        user_id = query.from_user.id
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Только администратор может остановить бота!")
            return
            
        keyboard = [
            [InlineKeyboardButton("✅ Да, остановить", callback_data="confirm_stop_bot")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_stop_bot")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = """
🛑 *Остановка бота*

⚠️ *Внимание!*
Бот будет полностью остановлен.

📝 *После остановки:*
• Бот перестанет отвечать
• Если включен Watchdog - он перезапустит бота
• Для ручного запуска используйте start.bat

Вы уверены?
        """
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    async def stop_bot_now(self, query):
        """Остановить бота немедленно"""
        user_id = query.from_user.id
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Нет прав доступа!")
            return
            
        try:
            await query.edit_message_text(
                "🛑 *Бот остановлен!*\n\n"
                "👋 До свидания! Останавливаем все процессы...",
                parse_mode='Markdown'
            )
            
            # Логируем остановку
            logger.info(f"🛑 Бот остановлен администратором (ID: {user_id})")
            
            # Создаем сигнал для watchdog
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                stop_signal_file = os.path.join(script_dir, "stop_bot.signal")
                with open(stop_signal_file, 'w') as f:
                    f.write(f"STOP_SIGNAL_{user_id}_{time.time()}")
                logger.info("📶 Сигнал остановки отправлен watchdog")
            except Exception as e:
                logger.error(f"Ошибка создания сигнала: {e}")
            
            # Останавливаем трансляцию экрана
            if hasattr(self, '_stream_active') and self._stream_active:
                self._stream_active = False
                if hasattr(self, '_stream_thread') and self._stream_thread and self._stream_thread.is_alive():
                    self._stream_thread.join(timeout=3)
                logger.info("📺 Трансляция экрана остановлена при завершении бота")
            
            # Очищаем ресурсы
            if hasattr(self, '_cache'):
                self._cache.clear()
            gc.collect()
            
            # Останавливаем приложение
            if self.app:
                await self.app.stop()
                await self.app.shutdown()
            
            # Короткая пауза для обработки сигнала
            import time
            time.sleep(2)
            
            # Завершаем процесс
            import sys
            sys.exit(0)
            
        except Exception as e:
            logger.error(f"Ошибка при остановке бота: {e}")
            await query.edit_message_text(f"❌ Ошибка остановки: {str(e)}")

    async def show_screen_stream_menu(self, query):
        """Показать меню трансляции экрана"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        status_text = "✅ Активна" if self._stream_active else "❌ Остановлена"
        quality_text = {
            'turbo': '🔥 Турбо (240x180, 0.5 сек)',
            'low': '🔴 Низкое (320x240, 1 сек)',
            'medium': '🟡 Среднее (640x480, 1.5 сек)',
            'high': '🟢 Высокое (1280x720, 2 сек)',
            'ultra': '🟣 Ультра (1920x1080, 0.2 сек)'
        }.get(self._stream_quality, '🟡 Среднее')
        
        keyboard = []
        if self._stream_active:
            keyboard.append([InlineKeyboardButton("❌ Остановить трансляцию", callback_data="stop_stream")])
        else:
            keyboard.append([InlineKeyboardButton("✅ Начать трансляцию", callback_data="start_stream")])
            
        # Кнопки качества (три строки для всех режимов)
        quality_row1 = [
            InlineKeyboardButton("🔥 Турбо", callback_data="quality_turbo"),
            InlineKeyboardButton("🔴 Низкое", callback_data="quality_low")
        ]
        quality_row2 = [
            InlineKeyboardButton("🟡 Среднее", callback_data="quality_medium"),
            InlineKeyboardButton("🟢 Высокое", callback_data="quality_high")
        ]
        quality_row3 = [
            InlineKeyboardButton("🟣 Ультра", callback_data="quality_ultra")
        ]
        keyboard.append(quality_row1)
        keyboard.append(quality_row2)
        keyboard.append(quality_row3)
        
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = f"""
📺 *Трансляция экрана*

📊 *Статус:* {status_text}
🎨 *Качество:* {quality_text}

📝 *Описание:*
Просмотр экрана в реальном времени через Telegram.
🔄 Одно сообщение обновляется - не засоряет чат!
🔥 *Турбо:* 0.5 сек | 🟣 *Ультра:* 0.2 сек в Full HD!
Качество влияет на разрешение и частоту обновления.
        """
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    async def show_github_menu(self, query):
        """Показать меню GitHub браузера"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        keyboard = [
            [InlineKeyboardButton("🔗 Ввести ссылку GitHub", callback_data="github_input_url")],
            [
                InlineKeyboardButton("📁 Просмотр файлов", callback_data="github_browse_root"),
                InlineKeyboardButton("💾 Скачать ZIP", callback_data="github_download_zip")
            ],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        current_repo_text = ""
        if self._current_github_repo:
            current_repo_text = f"\n📂 *Текущий репозиторий:*\n`{self._current_github_repo}`\n"
        
        text = f"""
🐙 *GitHub Браузер*
{current_repo_text}
📝 *Возможности:*
• 🔗 Просмотр любого GitHub репозитория
• 📁 Навигация по папкам и файлам
• 💾 Скачивание отдельных файлов
• 📦 Скачивание всего репозитория

📝 *Пример ссылки:*
`https://github.com/username/repository`
        """
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    async def request_github_url(self, query):
        """Запросить ввод GitHub URL"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад", callback_data="github_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = """
🔗 *Введите GitHub URL*

💬 Напишите ссылку на GitHub репозиторий.

📝 *Примеры:*
• `https://github.com/jdjdhdcbfgghh8845/rep`
• `https://github.com/microsoft/vscode`
• `https://github.com/python/cpython`

ℹ️ *Поддерживаются публичные репозитории.*
        """
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    async def parse_github_url(self, url):
        """Парсинг GitHub URL"""
        import re
        
        # Убираем лишние символы
        url = url.strip()
        
        # Паттерн для GitHub URL
        pattern = r'https?://github\.com/([^/]+)/([^/]+)/?.*'
        match = re.match(pattern, url)
        
        if match:
            owner = match.group(1)
            repo = match.group(2)
            # Убираем .git если есть
            if repo.endswith('.git'):
                repo = repo[:-4]
            return owner, repo
        return None, None

    async def fetch_github_contents(self, owner, repo, path=""):
        """Получить содержимое GitHub репозитория"""
        try:
            import requests
            
            # GitHub API URL
            api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
            
            # Проверяем кэш
            cache_key = f"{owner}/{repo}/{path}"
            if cache_key in self._github_cache:
                return self._github_cache[cache_key]
            
            # Запрос к GitHub API
            headers = {
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'TelegramBot-PC-Control'
            }
            
            response = requests.get(api_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                # Кэшируем результат
                self._github_cache[cache_key] = data
                return data
            else:
                return None
                
        except Exception as e:
            logger.error(f"Ошибка GitHub API: {e}")
            return None

    async def handle_github_url_message(self, update, github_url):
        """Обработка GitHub URL из сообщения"""
        owner, repo = await self.parse_github_url(github_url)
        
        if not owner or not repo:
            await update.message.reply_text(
                "❌ Неверная ссылка GitHub!\n\n"
                "📝 Пример: `https://github.com/username/repository`",
                parse_mode='Markdown'
            )
            return
        
        # Сохраняем текущий репозиторий
        self._current_github_repo = f"{owner}/{repo}"
        self._current_github_path = ""
        
        # Получаем содержимое
        status_msg = await update.message.reply_text(
            f"⏳ Подключаюсь к репозиторию `{owner}/{repo}`...",
            parse_mode='Markdown'
        )
        
        contents = await self.fetch_github_contents(owner, repo)
        
        if contents is None:
            await status_msg.edit_text(
                f"❌ Не удалось подключиться к `{owner}/{repo}`\n\n"
                "ℹ️ Проверьте, что репозиторий публичный.",
                parse_mode='Markdown'
            )
            return
        
        await self.show_github_contents(status_msg, contents, owner, repo, "")

    async def show_github_contents(self, message, contents, owner, repo, path):
        """Показать содержимое GitHub папки"""
        if not isinstance(contents, list):
            contents = [contents]
        
        # Сортируем: сначала папки, потом файлы
        folders = [item for item in contents if item['type'] == 'dir']
        files = [item for item in contents if item['type'] == 'file']
        
        folders.sort(key=lambda x: x['name'].lower())
        files.sort(key=lambda x: x['name'].lower())
        
        keyboard = []
        
        # Кнопка "Назад" для подпапок
        if path:
            parent_path = '/'.join(path.split('/')[:-1]) if '/' in path else ""
            keyboard.append([InlineKeyboardButton("⬆️ ..", callback_data=f"github_browse_{parent_path}")])
        
        # Папки (ограничиваем 8 папок)
        for folder in folders[:8]:
            folder_path = f"{path}/{folder['name']}" if path else folder['name']
            callback_data = f"github_browse_{folder_path}"
            if len(callback_data) > 64:
                callback_data = callback_data[:64]
            keyboard.append([InlineKeyboardButton(
                f"📁 {folder['name'][:25]}", 
                callback_data=callback_data
            )])
        
        # Файлы (ограничиваем 10 файлов)
        for file in files[:10]:
            file_path = f"{path}/{file['name']}" if path else file['name']
            file_size = self.format_file_size(file.get('size', 0))
            callback_data = f"github_download_{file_path}"
            if len(callback_data) > 64:
                callback_data = callback_data[:64]
            # Две кнопки для каждого файла: Telegram и ПК
            telegram_callback = f"github_download_{file_path}"
            pc_callback = f"github_download_pc_{file_path}"
            
            if len(telegram_callback) > 64:
                telegram_callback = telegram_callback[:64]
            if len(pc_callback) > 64:
                pc_callback = pc_callback[:64]
                
            keyboard.append([
                InlineKeyboardButton(
                    f"📨 {file['name'][:15]} ({file_size})", 
                    callback_data=telegram_callback
                ),
                InlineKeyboardButton(
                    f"💾 На ПК", 
                    callback_data=pc_callback
                )
            ])
        
        # Кнопки управления
        keyboard.append([
            InlineKeyboardButton("📦 Скачать ZIP", callback_data="github_download_zip"),
            InlineKeyboardButton("🆕 Обновить", callback_data=f"github_browse_{path}"[:64])
        ])
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="github_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Формируем текст
        current_path = f"/{path}" if path else "/"
        total_items = len(folders) + len(files)
        
        text = f"""
🐙 *GitHub: {owner}/{repo}*
📂 *Путь:* `{current_path}`

📊 *Статистика:*
📁 Папок: {len(folders)}
💾 Файлов: {len(files)}
📎 Всего: {total_items}

📝 *Навигация:*
• 📁 Нажмите на папку чтобы открыть
• 📨 Скачать в Telegram
• 💾 Скачать на ПК (в Downloads/GitHub/)
        """
        
        await message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    def format_file_size(self, size_bytes):
        """Форматирование размера файла"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"

    async def browse_github_path(self, query, path):
        """Просмотр папки в GitHub репозитории"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        if not self._current_github_repo:
            await query.edit_message_text("❌ Сначала выберите репозиторий!")
            return
        
        owner, repo = self._current_github_repo.split('/')
        
        await query.edit_message_text(
            f"⏳ Загружаю папку `{path or '/'}`...",
            parse_mode='Markdown'
        )
        
        contents = await self.fetch_github_contents(owner, repo, path)
        
        if contents is None:
            await query.edit_message_text(
                f"❌ Не удалось загрузить папку `{path}`",
                parse_mode='Markdown'
            )
            return
        
        await self.show_github_contents(query, contents, owner, repo, path)

    async def download_github_file(self, query, file_path):
        """Скачать файл из GitHub репозитория"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        if not self._current_github_repo:
            await query.edit_message_text("❌ Сначала выберите репозиторий!")
            return
        
        owner, repo = self._current_github_repo.split('/')
        
        await query.edit_message_text(
            f"⏳ Скачиваю файл `{file_path}`...",
            parse_mode='Markdown'
        )
        
        try:
            import requests
            import os
            
            # Получаем информацию о файле
            api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
            headers = {
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'TelegramBot-PC-Control'
            }
            
            response = requests.get(api_url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                await query.edit_message_text(
                    f"❌ Не удалось получить файл `{file_path}`",
                    parse_mode='Markdown'
                )
                return
            
            file_info = response.json()
            
            # Проверяем размер файла (Telegram лимит 50MB)
            file_size = file_info.get('size', 0)
            if file_size > 50 * 1024 * 1024:  # 50MB
                await query.edit_message_text(
                    f"❌ Файл `{file_path}` слишком большой ({self.format_file_size(file_size)})\n\n"
                    "ℹ️ Максимальный размер: 50MB",
                    parse_mode='Markdown'
                )
                return
            
            # Скачиваем файл
            download_url = file_info['download_url']
            file_response = requests.get(download_url, timeout=30)
            
            if file_response.status_code == 200:
                # Сохраняем во временную папку
                import tempfile
                filename = os.path.basename(file_path)
                temp_path = os.path.join(tempfile.gettempdir(), filename)
                
                with open(temp_path, 'wb') as f:
                    f.write(file_response.content)
                
                # Отправляем файл в Telegram
                with open(temp_path, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename=filename,
                        caption=f"💾 *Файл из GitHub:*\n`{owner}/{repo}/{file_path}`\n\n📊 Размер: {self.format_file_size(file_size)}",
                        parse_mode='Markdown'
                    )
                
                # Удаляем временный файл
                os.remove(temp_path)
                
                await query.edit_message_text(
                    f"✅ Файл `{filename}` успешно скачан!",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(
                    f"❌ Ошибка скачивания файла `{file_path}`",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Ошибка скачивания файла: {e}")
            await query.edit_message_text(
                f"❌ Ошибка скачивания: {str(e)}",
                parse_mode='Markdown'
            )

    async def download_github_file_to_pc(self, query, file_path):
        """Скачать файл из GitHub на ПК"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        if not self._current_github_repo:
            await query.edit_message_text("❌ Сначала выберите репозиторий!")
            return
        
        owner, repo = self._current_github_repo.split('/')
        
        await query.edit_message_text(
            f"⏳ Скачиваю файл `{file_path}` на ПК...",
            parse_mode='Markdown'
        )
        
        try:
            import requests
            import os
            
            # Получаем информацию о файле
            api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
            headers = {
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'TelegramBot-PC-Control'
            }
            
            response = requests.get(api_url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                await query.edit_message_text(
                    f"❌ Не удалось получить файл `{file_path}`",
                    parse_mode='Markdown'
                )
                return
            
            file_info = response.json()
            
            # Скачиваем файл
            download_url = file_info['download_url']
            file_response = requests.get(download_url, timeout=60)
            
            if file_response.status_code == 200:
                # Определяем папку для сохранения
                downloads_folder = os.path.join(os.path.expanduser("~"), "Downloads")
                github_folder = os.path.join(downloads_folder, "GitHub", f"{owner}_{repo}")
                
                # Создаем папку если не существует
                os.makedirs(github_folder, exist_ok=True)
                
                # Полный путь к файлу
                filename = os.path.basename(file_path)
                full_path = os.path.join(github_folder, filename)
                
                # Если файл уже существует, добавляем номер
                counter = 1
                original_path = full_path
                while os.path.exists(full_path):
                    name, ext = os.path.splitext(filename)
                    full_path = os.path.join(github_folder, f"{name}_{counter}{ext}")
                    counter += 1
                
                # Сохраняем файл
                with open(full_path, 'wb') as f:
                    f.write(file_response.content)
                
                file_size = len(file_response.content)
                
                keyboard = [
                    [InlineKeyboardButton("📁 Открыть папку", callback_data=self.make_safe_callback("open_folder", github_folder))],
                    [InlineKeyboardButton("🔧 Действия с файлом", callback_data=self.make_safe_callback("file_actions", full_path))],
                    [InlineKeyboardButton("⬅️ Назад", callback_data="github_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"✅ *Файл скачан на ПК!*\n\n"
                    f"💾 *Файл:* `{os.path.basename(full_path)}`\n"
                    f"📁 *Папка:* `{github_folder}`\n"
                    f"📊 *Размер:* {self.format_file_size(file_size)}\n\n"
                    f"🐙 *Источник:* `{owner}/{repo}/{file_path}`",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            else:
                await query.edit_message_text(
                    f"❌ Ошибка скачивания файла `{file_path}`",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Ошибка скачивания файла на ПК: {e}")
            await query.edit_message_text(
                f"❌ Ошибка скачивания: {str(e)}",
                parse_mode='Markdown'
            )

    async def open_folder(self, query, folder_path):
        """Открыть папку в проводнике"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        try:
            import subprocess
            import os
            
            if os.path.exists(folder_path):
                if self._stealth_mode:
                    # В скрытом режиме показываем содержимое в Telegram
                    files = os.listdir(folder_path)
                    files_list = "\n".join([f"📁 {f}" if os.path.isdir(os.path.join(folder_path, f)) else f"💾 {f}" for f in files[:20]])
                    if len(files) > 20:
                        files_list += f"\n... и ещё {len(files) - 20} файлов"
                    
                    await query.edit_message_text(
                        f"📁 *Содержимое папки:*\n`{folder_path}`\n\n{files_list}",
                        parse_mode='Markdown'
                    )
                else:
                    # Обычный режим - открываем проводник
                    subprocess.run(['explorer', folder_path], shell=True)
                    
                    await query.edit_message_text(
                        f"✅ Папка открыта в проводнике!\n\n"
                        f"📁 `{folder_path}`",
                        parse_mode='Markdown'
                    )
            else:
                await query.edit_message_text(
                    f"❌ Папка не найдена:\n`{folder_path}`",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Ошибка открытия папки: {e}")
            await query.edit_message_text(
                f"❌ Ошибка открытия папки: {str(e)}",
                parse_mode='Markdown'
            )

    async def show_file_actions(self, query, file_path_or_id):
        """Показать доступные действия с файлом"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        # Получаем полный путь
        file_path = self.get_file_path_from_id(file_path_or_id)
            
        import os
        
        if not os.path.exists(file_path):
            await query.edit_message_text(
                f"❌ Файл не найден:\n`{file_path}`",
                parse_mode='Markdown'
            )
            return
        
        filename = os.path.basename(file_path)
        file_ext = os.path.splitext(filename)[1].lower()
        file_size = os.path.getsize(file_path)
        
        keyboard = []
        
        # Основные действия
        keyboard.append([
            InlineKeyboardButton("🚀 Запустить", callback_data=self.make_safe_callback("run_file", file_path)),
            InlineKeyboardButton("📄 Просмотреть", callback_data=self.make_safe_callback("view_file", file_path))
        ])
        
        # Действия для архивов
        if file_ext in ['.zip', '.rar', '.7z', '.tar', '.gz']:
            keyboard.append([
                InlineKeyboardButton("📦 Распаковать", callback_data=self.make_safe_callback("extract_file", file_path))
            ])
        
        # Действия для текстовых файлов
        if file_ext in ['.txt', '.py', '.js', '.html', '.css', '.json', '.xml', '.md', '.yml', '.yaml', '.ini', '.cfg']:
            keyboard.append([
                InlineKeyboardButton("✏️ Редактировать", callback_data=self.make_safe_callback("edit_file", file_path))
            ])
        
        # Действия для изображений
        if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
            keyboard.append([
                InlineKeyboardButton("🖼️ Открыть в просмотрщике", callback_data=self.make_safe_callback("view_image", file_path))
            ])
        
        # Дополнительные действия
        keyboard.append([
            InlineKeyboardButton("📁 Открыть папку", callback_data=self.make_safe_callback("open_folder", os.path.dirname(file_path))),
            InlineKeyboardButton("🗑️ Удалить", callback_data=self.make_safe_callback("delete_file", file_path))
        ])
        
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="github_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Определяем тип файла
        file_type = self.get_file_type(file_ext)
        
        text = f"""
🔧 *Действия с файлом*

💾 *Файл:* `{filename}`
📂 *Тип:* {file_type}
📊 *Размер:* {self.format_file_size(file_size)}
📁 *Путь:* `{file_path}`

📝 *Доступные действия:*
• 🚀 Запустить файл
• 📄 Просмотреть содержимое
{'• 📦 Распаковать архив' if file_ext in ['.zip', '.rar', '.7z', '.tar', '.gz'] else ''}
{'• ✏️ Редактировать текст' if file_ext in ['.txt', '.py', '.js', '.html', '.css', '.json', '.xml', '.md'] else ''}
        """
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    def get_file_type(self, file_ext):
        """Определить тип файла"""
        file_types = {
            '.py': '🐍 Python скрипт',
            '.js': '📜 JavaScript',
            '.html': '🌐 HTML страница',
            '.css': '🎨 CSS стили',
            '.json': '📊 JSON данные',
            '.txt': '📄 Текстовый файл',
            '.md': '📝 Markdown',
            '.zip': '📦 ZIP архив',
            '.rar': '📦 RAR архив',
            '.7z': '📦 7-Zip архив',
            '.exe': '⚙️ Исполняемый файл',
            '.jpg': '🖼️ Изображение JPEG',
            '.png': '🖼️ Изображение PNG',
            '.pdf': '📄 PDF документ',
            '.mp4': '🎥 Видео MP4',
            '.mp3': '🎵 Аудио MP3'
        }
        return file_types.get(file_ext, f'💾 {file_ext[1:].upper()} файл')

    def get_short_file_id(self, file_path):
        """Получить короткий ID для длинного пути к файлу"""
        import hashlib
        
        # Создаем короткий хеш из пути
        file_hash = hashlib.md5(file_path.encode()).hexdigest()[:8]
        
        # Сохраняем в кэше
        self._file_path_cache[file_hash] = file_path
        
        return file_hash
    
    def get_file_path_from_id(self, file_id):
        """Получить полный путь по короткому ID"""
        return self._file_path_cache.get(file_id, file_id)

    def make_safe_callback(self, prefix, file_path):
        """Создать безопасный callback_data"""
        if len(f"{prefix}_{file_path}") <= 64:
            return f"{prefix}_{file_path}"
        else:
            short_id = self.get_short_file_id(file_path)
            return f"{prefix}_{short_id}"

    async def run_file(self, query, file_path_or_id):
        """Запустить файл"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        # Получаем полный путь
        file_path = self.get_file_path_from_id(file_path_or_id)
            
        try:
            import subprocess
            import os
            
            if not os.path.exists(file_path):
                await query.edit_message_text(
                    f"❌ Файл не найден: `{file_path}`",
                    parse_mode='Markdown'
                )
                return
            
            filename = os.path.basename(file_path)
            
            await query.edit_message_text(
                f"⏳ Запускаю файл `{filename}`...",
                parse_mode='Markdown'
            )
            
            # Запускаем файл скрыто (без окон)
            if self._stealth_mode:
                # Скрытый запуск без окон
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                subprocess.Popen([file_path], startupinfo=startupinfo, shell=False)
            else:
                subprocess.Popen(['start', '', file_path], shell=True)
            
            await query.edit_message_text(
                f"✅ Файл `{filename}` запущен!\n\n"
                f"📁 `{file_path}`",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка запуска файла: {e}")
            await query.edit_message_text(
                f"❌ Ошибка запуска: {str(e)}",
                parse_mode='Markdown'
            )

    async def view_file(self, query, file_path_or_id):
        """Просмотреть содержимое файла"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        # Получаем полный путь
        file_path = self.get_file_path_from_id(file_path_or_id)
            
        try:
            import os
            
            if not os.path.exists(file_path):
                await query.edit_message_text(
                    f"❌ Файл не найден: `{file_path}`",
                    parse_mode='Markdown'
                )
                return
            
            filename = os.path.basename(file_path)
            file_ext = os.path.splitext(filename)[1].lower()
            
            # Проверяем размер файла
            file_size = os.path.getsize(file_path)
            if file_size > 1024 * 1024:  # 1MB
                await query.edit_message_text(
                    f"❌ Файл `{filename}` слишком большой для просмотра ({self.format_file_size(file_size)})\n\n"
                    "ℹ️ Максимальный размер: 1MB",
                    parse_mode='Markdown'
                )
                return
            
            # Читаем файл
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                try:
                    with open(file_path, 'r', encoding='cp1251') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    await query.edit_message_text(
                        f"❌ Не удалось прочитать файл `{filename}` (бинарный файл?)",
                        parse_mode='Markdown'
                    )
                    return
            
            # Ограничиваем длину содержимого
            if len(content) > 3000:
                content = content[:3000] + "\n\n... (содержимое обрезано)"
            
            keyboard = [
                [InlineKeyboardButton("⬅️ Назад", callback_data=self.make_safe_callback("file_actions", file_path))]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"📄 *Содержимое файла:* `{filename}`\n\n```\n{content}\n```",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Ошибка просмотра файла: {e}")
            await query.edit_message_text(
                f"❌ Ошибка просмотра: {str(e)}",
                parse_mode='Markdown'
            )

    async def extract_file(self, query, file_path_or_id):
        """Распаковать архив"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        # Получаем полный путь
        file_path = self.get_file_path_from_id(file_path_or_id)
            
        try:
            import os
            import zipfile
            
            if not os.path.exists(file_path):
                await query.edit_message_text(
                    f"❌ Файл не найден: `{file_path}`",
                    parse_mode='Markdown'
                )
                return
            
            filename = os.path.basename(file_path)
            file_ext = os.path.splitext(filename)[1].lower()
            
            await query.edit_message_text(
                f"⏳ Распаковываю архив `{filename}`...",
                parse_mode='Markdown'
            )
            
            # Папка для распаковки
            extract_folder = os.path.join(os.path.dirname(file_path), f"{os.path.splitext(filename)[0]}_extracted")
            os.makedirs(extract_folder, exist_ok=True)
            
            extracted_files = 0
            
            if file_ext == '.zip':
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_folder)
                    extracted_files = len(zip_ref.namelist())
            elif file_ext == '.rar':
                try:
                    import rarfile
                    with rarfile.RarFile(file_path, 'r') as rar_ref:
                        rar_ref.extractall(extract_folder)
                        extracted_files = len(rar_ref.namelist())
                except ImportError:
                    await query.edit_message_text(
                        f"❌ Для работы с RAR архивами нужна библиотека rarfile\n\n"
                        "📝 Установите: `pip install rarfile`",
                        parse_mode='Markdown'
                    )
                    return
            elif file_ext == '.7z':
                try:
                    import py7zr
                    with py7zr.SevenZipFile(file_path, 'r') as sz_ref:
                        sz_ref.extractall(extract_folder)
                        extracted_files = len(sz_ref.getnames())
                except ImportError:
                    await query.edit_message_text(
                        f"❌ Для работы с 7Z архивами нужна библиотека py7zr\n\n"
                        "📝 Установите: `pip install py7zr`",
                        parse_mode='Markdown'
                    )
                    return
            else:
                # Попытка распаковать через системные утилиты
                import subprocess
                try:
                    if self._stealth_mode:
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        startupinfo.wShowWindow = subprocess.SW_HIDE
                        
                        result = subprocess.run(
                            ['powershell', '-Command', f'Expand-Archive -Path "{file_path}" -DestinationPath "{extract_folder}" -Force'],
                            startupinfo=startupinfo,
                            capture_output=True,
                            text=True
                        )
                    else:
                        result = subprocess.run(
                            ['powershell', '-Command', f'Expand-Archive -Path "{file_path}" -DestinationPath "{extract_folder}" -Force'],
                            capture_output=True,
                            text=True
                        )
                    
                    if result.returncode == 0:
                        extracted_files = len(os.listdir(extract_folder))
                    else:
                        await query.edit_message_text(
                            f"❌ Ошибка распаковки: {result.stderr}",
                            parse_mode='Markdown'
                        )
                        return
                except Exception as e:
                    await query.edit_message_text(
                        f"❌ Формат `{file_ext}` не поддерживается.\n\n"
                        "ℹ️ Поддерживается: ZIP, RAR, 7Z",
                        parse_mode='Markdown'
                    )
                    return
            
            # Кнопки для всех успешно распакованных архивов
            keyboard = [
                [InlineKeyboardButton("📁 Открыть папку", callback_data=self.make_safe_callback("open_folder", extract_folder))],
                [InlineKeyboardButton("📊 Просмотр содержимого", callback_data=self.make_safe_callback("browse_folder", extract_folder))],
                [InlineKeyboardButton("⬅️ Назад", callback_data=self.make_safe_callback("file_actions", file_path))]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"✅ *Архив распакован!*\n\n"
                    f"📦 *Архив:* `{filename}`\n"
                    f"📁 *Папка:* `{extract_folder}`\n"
                    f"📎 *Файлов:* {extracted_files}",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
                
        except Exception as e:
            logger.error(f"Ошибка распаковки: {e}")
            await query.edit_message_text(
                f"❌ Ошибка распаковки: {str(e)}",
                parse_mode='Markdown'
            )

    async def edit_file(self, query, file_path_or_id):
        """Открыть файл в редакторе"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        # Получаем полный путь
        file_path = self.get_file_path_from_id(file_path_or_id)
            
        try:
            import subprocess
            import os
            
            if not os.path.exists(file_path):
                await query.edit_message_text(
                    f"❌ Файл не найден: `{file_path}`",
                    parse_mode='Markdown'
                )
                return
            
            filename = os.path.basename(file_path)
            
            if self._stealth_mode:
                # В скрытом режиме показываем содержимое для редактирования
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    try:
                        with open(file_path, 'r', encoding='cp1251') as f:
                            content = f.read()
                    except UnicodeDecodeError:
                        await query.edit_message_text(
                            f"❌ Не удалось прочитать файл `{filename}` (бинарный?)",
                            parse_mode='Markdown'
                        )
                        return
                
                # Ограничиваем длину
                if len(content) > 2000:
                    content = content[:2000] + "\n\n... (содержимое обрезано)"
                
                # Сохраняем путь для редактирования
                self._editing_file = file_path
                
                keyboard = [
                    [InlineKeyboardButton("💾 Сохранить изменения", callback_data="save_file_changes")],
                    [InlineKeyboardButton("⬅️ Назад", callback_data=self.make_safe_callback("file_actions", file_path))]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"✏️ *Редактирование:* `{filename}`\n\n```\n{content}\n```\n\n📝 Отправьте новое содержимое сообщением",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            else:
                # Обычный режим - открываем блокнот
                subprocess.Popen(['notepad', file_path])
                
                await query.edit_message_text(
                    f"✏️ Файл `{filename}` открыт в редакторе!\n\n"
                    f"📁 `{file_path}`",
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            logger.error(f"Ошибка открытия редактора: {e}")
            await query.edit_message_text(
                f"❌ Ошибка открытия редактора: {str(e)}",
                parse_mode='Markdown'
            )

    async def view_image(self, query, file_path_or_id):
        """Открыть изображение в просмотрщике"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        # Получаем полный путь
        file_path = self.get_file_path_from_id(file_path_or_id)
            
        try:
            import subprocess
            import os
            
            if not os.path.exists(file_path):
                await query.edit_message_text(
                    f"❌ Файл не найден: `{file_path}`",
                    parse_mode='Markdown'
                )
                return
            
            filename = os.path.basename(file_path)
            
            if self._stealth_mode:
                # В скрытом режиме отправляем изображение в Telegram
                try:
                    with open(file_path, 'rb') as f:
                        await query.message.reply_photo(
                            photo=f,
                            caption=f"🖼️ *Изображение:* `{filename}`\n📁 `{file_path}`",
                            parse_mode='Markdown'
                        )
                    
                    await query.edit_message_text(
                        f"✅ Изображение `{filename}` отправлено!",
                        parse_mode='Markdown'
                    )
                except Exception as img_error:
                    await query.edit_message_text(
                        f"❌ Ошибка отправки изображения: {str(img_error)}",
                        parse_mode='Markdown'
                    )
            else:
                # Обычный режим - открываем просмотрщик
                subprocess.Popen(['start', '', file_path], shell=True)
                
                await query.edit_message_text(
                    f"🖼️ Изображение `{filename}` открыто в просмотрщике!\n\n"
                    f"📁 `{file_path}`",
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            logger.error(f"Ошибка открытия изображения: {e}")
            await query.edit_message_text(
                f"❌ Ошибка открытия изображения: {str(e)}",
                parse_mode='Markdown'
            )

    async def delete_file(self, query, file_path_or_id):
        """Удалить файл"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        # Получаем полный путь
        file_path = self.get_file_path_from_id(file_path_or_id)
            
        try:
            import os
            
            if not os.path.exists(file_path):
                await query.edit_message_text(
                    f"❌ Файл не найден: `{file_path}`",
                    parse_mode='Markdown'
                )
                return
            
            filename = os.path.basename(file_path)
            
            # Удаляем файл
            os.remove(file_path)
            
            await query.edit_message_text(
                f"✅ Файл `{filename}` удален!\n\n"
                f"📁 `{file_path}`",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка удаления файла: {e}")
            await query.edit_message_text(
                f"❌ Ошибка удаления: {str(e)}",
                parse_mode='Markdown'
            )

    async def save_file_changes_prompt(self, query):
        """Подтверждение сохранения изменений"""
        if not self._editing_file:
            await query.edit_message_text("❌ Нет файла для редактирования!")
            return
            
        filename = os.path.basename(self._editing_file)
        await query.edit_message_text(
            f"💾 *Готов к сохранению:* `{filename}`\n\n"
            f"📝 Отправьте новое содержимое файла следующим сообщением",
            parse_mode='Markdown'
        )

    async def save_file_content(self, update, new_content):
        """Сохранить новое содержимое файла"""
        if not self._editing_file:
            await update.message.reply_text("❌ Нет файла для редактирования!")
            return
            
        try:
            # Сохраняем файл
            with open(self._editing_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            filename = os.path.basename(self._editing_file)
            file_size = len(new_content.encode('utf-8'))
            
            keyboard = [
                [InlineKeyboardButton("🔧 Действия с файлом", callback_data=self.make_safe_callback("file_actions", self._editing_file))],
                [InlineKeyboardButton("⬅️ Назад", callback_data="github_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ *Файл сохранён!*\n\n"
                f"💾 *Файл:* `{filename}`\n"
                f"📊 *Размер:* {self.format_file_size(file_size)}\n"
                f"📁 *Путь:* `{self._editing_file}`",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
            # Очищаем редактируемый файл
            self._editing_file = None
            
        except Exception as e:
            logger.error(f"Ошибка сохранения файла: {e}")
            await update.message.reply_text(
                f"❌ Ошибка сохранения: {str(e)}",
                parse_mode='Markdown'
            )

    async def toggle_stealth_mode(self, query):
        """Переключить скрытый режим"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        # Переключаем режим
        self._stealth_mode = not self._stealth_mode
        
        mode_name = "🕵️ Скрытый" if self._stealth_mode else "👁️ Обычный"
        mode_desc = "всё выполняется скрыто в фоне" if self._stealth_mode else "обычное поведение с окнами"
        
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад в меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"⚙️ *Режим изменён!*\n\n"
            f"🔄 *Текущий режим:* {mode_name}\n\n"
            f"📝 *Описание:*\n{mode_desc}\n\n"
            f"💡 *Что это значит:*\n"
            f"{'• Команды выполняются без окон' if self._stealth_mode else '• Команды могут показывать окна'}\n"
            f"{'• Папки открываются в Telegram' if self._stealth_mode else '• Папки открываются в проводнике'}\n"
            f"{'• Редактирование через Telegram' if self._stealth_mode else '• Редактирование в блокноте'}\n"
            f"{'• Изображения отправляются в чат' if self._stealth_mode else '• Изображения открываются в просмотрщике'}",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    async def browse_folder_contents(self, query, folder_path, current_path=""):
        """Интерактивный просмотр содержимого папки"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        import os
        
        # Полный путь к текущей папке
        full_path = os.path.join(folder_path, current_path) if current_path else folder_path
        
        if not os.path.exists(full_path):
            await query.edit_message_text(
                f"❌ Папка не найдена:\n`{full_path}`",
                parse_mode='Markdown'
            )
            return
        
        try:
            # Получаем содержимое
            items = os.listdir(full_path)
            
            # Сортируем: сначала папки, потом файлы
            folders = []
            files = []
            
            for item in items:
                item_path = os.path.join(full_path, item)
                if os.path.isdir(item_path):
                    folders.append(item)
                else:
                    files.append(item)
            
            folders.sort(key=str.lower)
            files.sort(key=str.lower)
            
            keyboard = []
            
            # Кнопка "Назад" для подпапок
            if current_path:
                parent_path = os.path.dirname(current_path) if os.path.dirname(current_path) != current_path else ""
                keyboard.append([InlineKeyboardButton("⬆️ ..", callback_data=self.make_safe_callback("browse_subfolder", f"{folder_path}|{parent_path}"))])
            
            # Папки (ограничиваем 8)
            for folder in folders[:8]:
                subfolder_path = os.path.join(current_path, folder) if current_path else folder
                keyboard.append([InlineKeyboardButton(
                    f"📁 {folder[:30]}", 
                    callback_data=self.make_safe_callback("browse_subfolder", f"{folder_path}|{subfolder_path}")
                )])
            
            # Файлы (ограничиваем 10)
            for file in files[:10]:
                file_full_path = os.path.join(full_path, file)
                file_size = self.format_file_size(os.path.getsize(file_full_path))
                
                keyboard.append([
                    InlineKeyboardButton(
                        f"💾 {file[:20]} ({file_size})", 
                        callback_data=self.make_safe_callback("file_actions", file_full_path)
                    )
                ])
            
            # Кнопки управления
            keyboard.append([InlineKeyboardButton("📁 Открыть в проводнике", callback_data=self.make_safe_callback("open_folder", full_path))])
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="github_menu")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Формируем текст
            display_path = f"/{current_path}" if current_path else "/"
            total_items = len(folders) + len(files)
            
            text = f"""
📁 *Просмотр папки*

📂 *Корневая папка:* `{os.path.basename(folder_path)}`
📍 *Текущий путь:* `{display_path}`

📊 *Статистика:*
📁 Папок: {len(folders)}
💾 Файлов: {len(files)}
📎 Всего: {total_items}

📝 *Навигация:*
• 📁 Нажмите на папку чтобы открыть
• 💾 Нажмите на файл для действий
            """
            
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Ошибка просмотра папки: {e}")
            await query.edit_message_text(
                f"❌ Ошибка просмотра папки: {str(e)}",
                parse_mode='Markdown'
            )

    async def show_file_explorer(self, query):
        """Показать главное меню File Explorer"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        import os
        
        # Получаем список дисков
        drives = []
        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                drives.append(letter)
        
        keyboard = []
        
        # Диски (по 2 в ряд)
        for i in range(0, len(drives), 2):
            row = []
            for j in range(2):
                if i + j < len(drives):
                    drive = drives[i + j]
                    row.append(InlineKeyboardButton(
                        f"💾 {drive}:\\", 
                        callback_data=f"explore_drive_{drive}"
                    ))
            keyboard.append(row)
        
        # Быстрые папки
        quick_folders = [
            ("🏠 Рабочий стол", os.path.expanduser("~/Desktop")),
            ("📁 Документы", os.path.expanduser("~/Documents")),
            ("💾 Загрузки", os.path.expanduser("~/Downloads")),
            ("🖼️ Картинки", os.path.expanduser("~/Pictures"))
        ]
        
        for name, path in quick_folders:
            if os.path.exists(path):
                keyboard.append([InlineKeyboardButton(
                    name, 
                    callback_data=self.make_safe_callback("explore_folder", path)
                )])
        
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = f"""
📁 *File Explorer*

💾 *Доступные диски:*
{', '.join([f'{d}:\\' for d in drives])}

🚀 *Быстрые папки:*
• Рабочий стол, Документы, Загрузки

📝 *Возможности:*
• Полная навигация по файловой системе
• Запуск, просмотр, редактирование файлов
• Распаковка архивов и работа с ними
        """
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    async def explore_drive(self, query, drive):
        """Открыть диск"""
        drive_path = f"{drive}:\\"
        await self.explore_folder(query, drive_path)

    async def explore_folder(self, query, folder_path, current_path=""):
        """Проводник по папкам"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        import os
        
        # Полный путь
        full_path = os.path.join(folder_path, current_path) if current_path else folder_path
        
        if not os.path.exists(full_path):
            await query.edit_message_text(
                f"❌ Папка не найдена:\n`{full_path}`",
                parse_mode='Markdown'
            )
            return
        
        try:
            # Получаем содержимое
            items = os.listdir(full_path)
            
            # Сортируем
            folders = []
            files = []
            
            for item in items:
                item_path = os.path.join(full_path, item)
                try:
                    if os.path.isdir(item_path):
                        folders.append(item)
                    else:
                        files.append(item)
                except PermissionError:
                    continue  # Пропускаем недоступные файлы
            
            folders.sort(key=str.lower)
            files.sort(key=str.lower)
            
            keyboard = []
            
            # Кнопка "Назад"
            if current_path:
                parent_path = os.path.dirname(current_path) if os.path.dirname(current_path) != current_path else ""
                keyboard.append([InlineKeyboardButton(
                    "⬆️ ..", 
                    callback_data=self.make_safe_callback("explore_folder", f"{folder_path}|{parent_path}")
                )])
            else:
                keyboard.append([InlineKeyboardButton("⬅️ К File Explorer", callback_data="file_explorer")])
            
            # Папки (ограничиваем 10)
            for folder in folders[:10]:
                subfolder_path = os.path.join(current_path, folder) if current_path else folder
                keyboard.append([InlineKeyboardButton(
                    f"📁 {folder[:35]}", 
                    callback_data=self.make_safe_callback("explore_folder", f"{folder_path}|{subfolder_path}")
                )])
            
            # Файлы (ограничиваем 12)
            for file in files[:12]:
                file_full_path = os.path.join(full_path, file)
                try:
                    file_size = self.format_file_size(os.path.getsize(file_full_path))
                    
                    # Определяем иконку по расширению
                    ext = os.path.splitext(file)[1].lower()
                    if ext in ['.zip', '.rar', '.7z']:
                        icon = "📦"
                    elif ext in ['.exe', '.msi']:
                        icon = "⚙️"
                    elif ext in ['.txt', '.py', '.js', '.html', '.css']:
                        icon = "📝"
                    elif ext in ['.jpg', '.png', '.gif', '.bmp']:
                        icon = "🖼️"
                    elif ext in ['.mp4', '.avi', '.mkv']:
                        icon = "🎥"
                    elif ext in ['.mp3', '.wav', '.flac']:
                        icon = "🎵"
                    else:
                        icon = "💾"
                    
                    keyboard.append([InlineKeyboardButton(
                        f"{icon} {file[:25]} ({file_size})", 
                        callback_data=self.make_safe_callback("file_actions", file_full_path)
                    )])
                except (OSError, PermissionError):
                    continue  # Пропускаем недоступные файлы
            
            # Кнопки управления
            if not self._stealth_mode:
                keyboard.append([InlineKeyboardButton(
                    "📁 Открыть в проводнике", 
                    callback_data=self.make_safe_callback("open_folder", full_path)
                )])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Формируем текст
            display_path = full_path if len(full_path) < 50 else "..." + full_path[-47:]
            total_items = len(folders) + len(files)
            
            text = f"""
📁 *File Explorer*

📍 *Путь:* `{display_path}`

📊 *Статистика:*
📁 Папок: {len(folders)}
💾 Файлов: {len(files)}
📎 Всего: {total_items}

📝 *Навигация:*
• 📁 Папка - открыть
• 💾 Файл - действия (запуск, просмотр, редактирование)
• 📦 Архив - распаковка и просмотр
            """
            
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            
        except PermissionError:
            await query.edit_message_text(
                f"❌ Нет доступа к папке:\n`{full_path}`",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Ошибка просмотра папки: {e}")
            await query.edit_message_text(
                f"❌ Ошибка просмотра: {str(e)}",
                parse_mode='Markdown'
            )

    def screen_stream_worker(self, chat_id):
        """Рабочий поток для трансляции экрана"""
        try:
            # Настройки качества (оптимизированные для скорости)
            quality_settings = {
                'turbo': {'size': (240, 180), 'interval': 0.5, 'quality': 40},  # Максимальная скорость!
                'low': {'size': (320, 240), 'interval': 1, 'quality': 50},      # Быстро и экономно
                'medium': {'size': (640, 480), 'interval': 1.5, 'quality': 65}, # Баланс скорости и качества
                'high': {'size': (1280, 720), 'interval': 2, 'quality': 75},   # Высокое качество, но быстро
                'ultra': {'size': (1920, 1080), 'interval': 0.2, 'quality': 85}  # Максимально плавно в Full HD!
            }
            
            settings = quality_settings.get(self._stream_quality, quality_settings['medium'])
            
            logger.info(f"📺 Начала трансляция экрана для chat_id: {chat_id}")
            logger.info(f"🎨 Качество: {self._stream_quality}, Настройки: {settings}")
            
            frame_count = 0
            while self._stream_active:
                try:
                    frame_count += 1
                    logger.debug(f"🎥 Обработка кадра #{frame_count}")
                    
                    # Делаем скриншот (оптимизированный)
                    start_time = time.time()
                    screenshot = ImageGrab.grab()
                    
                    # Используем более быстрый алгоритм масштабирования
                    if settings['size'] != screenshot.size:
                        # Для скорости используем NEAREST для маленьких размеров
                        if settings['size'][0] <= 640:
                            screenshot = screenshot.resize(settings['size'], Image.Resampling.NEAREST)
                        else:
                            screenshot = screenshot.resize(settings['size'], Image.Resampling.BILINEAR)
                    
                    process_time = time.time() - start_time
                    logger.debug(f"📷 Обработка скриншота: {process_time:.3f}с, размер: {screenshot.size}")
                    
                    # Сохраняем в буфер
                    bio = io.BytesIO()
                    screenshot.save(bio, format='JPEG', quality=settings['quality'], optimize=True)
                    bio.seek(0)
                    
                    # Отправляем или редактируем фото
                    if self.app and self._stream_active:
                        try:
                            import requests
                            
                            bot_token = BOT_TOKEN
                            file_size = len(bio.getvalue())
                            caption = f"📺 {datetime.now().strftime('%H:%M:%S')} | {self._stream_quality.title()} | Кадр #{frame_count}"
                            
                            bio.seek(0)
                            
                            if self._last_stream_message_id is None:
                                # Первое сообщение - отправляем новое
                                url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
                                files = {'photo': ('screenshot.jpg', bio, 'image/jpeg')}
                                data = {
                                    'chat_id': chat_id,
                                    'caption': caption
                                }
                                
                                logger.debug(f"📤 Отправка первого фото: {file_size} байт")
                                response = requests.post(url, files=files, data=data, timeout=10)
                                
                                if response.status_code == 200:
                                    result = response.json()
                                    if result.get('ok'):
                                        self._last_stream_message_id = result['result']['message_id']
                                        logger.info(f"✅ Первое фото отправлено: message_id {self._last_stream_message_id}")
                                    else:
                                        logger.error(f"Ошибка в ответе: {result}")
                                else:
                                    logger.error(f"Ошибка отправки: {response.status_code} - {response.text}")
                            else:
                                # Редактируем предыдущее сообщение
                                url = f"https://api.telegram.org/bot{bot_token}/editMessageMedia"
                                
                                media_data = {
                                    "type": "photo",
                                    "media": "attach://photo",
                                    "caption": caption
                                }
                                
                                files = {'photo': ('screenshot.jpg', bio, 'image/jpeg')}
                                data = {
                                    'chat_id': chat_id,
                                    'message_id': self._last_stream_message_id,
                                    'media': json.dumps(media_data)
                                }
                                
                                logger.debug(f"🔄 Редактирование фото: message_id {self._last_stream_message_id}")
                                response = requests.post(url, files=files, data=data, timeout=10)
                                
                                if response.status_code == 200:
                                    logger.info(f"✅ Фото обновлено: кадр #{frame_count}, {file_size/1024:.1f} KB")
                                else:
                                    logger.error(f"Ошибка редактирования: {response.status_code} - {response.text}")
                                    # Если не удалось отредактировать, отправляем новое
                                    self._last_stream_message_id = None
                                
                        except Exception as send_error:
                            logger.error(f"Ошибка отправки фото: {send_error}")
                            # Пробуем перезапустить через 3 ошибки
                            if not hasattr(self, '_error_count'):
                                self._error_count = 0
                            self._error_count += 1
                            if self._error_count >= 3:
                                logger.warning("Останавливаем трансляцию из-за множественных ошибок")
                                self._stream_active = False
                                break
                        else:
                            # Сбрасываем счетчик ошибок при успехе
                            self._error_count = 0
                    
                    time.sleep(settings['interval'])
                    
                except Exception as e:
                    logger.error(f"Ошибка в трансляции: {e}")
                    time.sleep(5)
                    
        except Exception as e:
            logger.error(f"Критическая ошибка трансляции: {e}")
        finally:
            self._stream_active = False
            logger.info("📺 Трансляция экрана остановлена")

    async def start_screen_stream(self, query):
        """Начать трансляцию экрана"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        if self._stream_active:
            await query.edit_message_text("ℹ️ Трансляция уже активна!")
            return
            
        try:
            self._stream_active = True
            self._stream_chat_id = query.message.chat_id
            self._last_stream_message_id = None  # Сбрасываем ID для новой трансляции
            
            # Запускаем поток в отдельном потоке
            self._stream_thread = threading.Thread(
                target=self.screen_stream_worker,
                args=(self._stream_chat_id,),
                daemon=True
            )
            self._stream_thread.start()
            
            keyboard = [
                [InlineKeyboardButton("❌ Остановить трансляцию", callback_data="stop_stream")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="screen_stream")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"✅ *Трансляция запущена!*\n\n"
                f"📺 Начинаю трансляцию экрана в реальном времени...\n"
                f"🎨 *Качество:* {self._stream_quality.title()}\n\n"
                f"🔄 *Новая функция:* Одно сообщение обновляется!\n"
                f"⚠️ *Примечание:* Использует интернет-трафик",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
        except Exception as e:
            self._stream_active = False
            await query.edit_message_text(f"❌ Ошибка запуска трансляции: {str(e)}")

    async def stop_screen_stream(self, query):
        """Остановить трансляцию экрана"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        if not self._stream_active:
            await query.edit_message_text("ℹ️ Трансляция не активна.")
            return
            
        try:
            self._stream_active = False
            self._stream_chat_id = None
            self._last_stream_message_id = None  # Сбрасываем ID сообщения
            
            # Ждем завершения потока
            if self._stream_thread and self._stream_thread.is_alive():
                self._stream_thread.join(timeout=3)
            
            keyboard = [
                [InlineKeyboardButton("✅ Начать трансляцию", callback_data="start_stream")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="screen_stream")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"❌ *Трансляция остановлена!*\n\n"
                f"📺 Трансляция экрана в реальном времени остановлена.",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка остановки трансляции: {str(e)}")

    async def change_stream_quality(self, query, quality):
        """Изменить качество трансляции"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        if quality not in ['turbo', 'low', 'medium', 'high', 'ultra']:
            await query.edit_message_text("❌ Неверное качество!")
            return
            
        old_quality = self._stream_quality
        self._stream_quality = quality
        
        quality_names = {
            'turbo': '🔥 Турбо (240x180, 0.5 сек)',
            'low': '🔴 Низкое (320x240, 1 сек)',
            'medium': '🟡 Среднее (640x480, 1.5 сек)',
            'high': '🟢 Высокое (1280x720, 2 сек)',
            'ultra': '🟣 Ультра (1920x1080, 0.2 сек)'
        }
        
        # Если трансляция активна, перезапускаем ее
        restart_needed = self._stream_active
        if restart_needed:
            self._stream_active = False
            self._last_stream_message_id = None  # Сбрасываем ID для нового сообщения
            if self._stream_thread and self._stream_thread.is_alive():
                self._stream_thread.join(timeout=2)
            
            # Запускаем с новым качеством
            self._stream_active = True
            self._stream_thread = threading.Thread(
                target=self.screen_stream_worker,
                args=(self._stream_chat_id,),
                daemon=True
            )
            self._stream_thread.start()
        
        await query.edit_message_text(
            f"✅ *Качество изменено!*\n\n"
            f"🎨 *Новое качество:* {quality_names[quality]}\n"
            f"{'🔄 Трансляция перезапущена с новым качеством!' if restart_needed else ''}\n\n"
            f"⬅️ Нажмите 'Назад' для возврата в меню.",
            parse_mode='Markdown'
        )
        
        # Автоматически возвращаемся в меню через 2 секунды
        import asyncio
        await asyncio.sleep(2)
        await self.show_screen_stream_menu(query)

    async def show_cmd_menu(self, query):
        """Показать меню CMD команд"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        keyboard = [
            [InlineKeyboardButton("📝 Написать команду", callback_data="write_cmd")],
            [
                InlineKeyboardButton("📁 dir", callback_data="quick_cmd_dir"),
                InlineKeyboardButton("📊 tasklist", callback_data="quick_cmd_tasklist")
            ],
            [
                InlineKeyboardButton("🌐 ipconfig", callback_data="quick_cmd_ipconfig"),
                InlineKeyboardButton("💾 systeminfo", callback_data="quick_cmd_systeminfo")
            ],
            [
                InlineKeyboardButton("🔍 netstat", callback_data="quick_cmd_netstat"),
                InlineKeyboardButton("📈 wmic", callback_data="quick_cmd_wmic")
            ],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = """
📝 *CMD Команды*

🚀 *Быстрые команды:*
• **dir** - список файлов в папке
• **tasklist** - список процессов
• **ipconfig** - сетевая информация
• **systeminfo** - информация о системе
• **netstat** - сетевые соединения
• **wmic** - информация WMI

📝 *Либо напишите свою команду!*
⚠️ *Осторожно с опасными командами!*
        """
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    async def request_cmd_input(self, query):
        """Запросить ввод команды"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад", callback_data="cmd_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = """
📝 *Введите CMD команду*

💬 Напишите команду в следующем сообщении.

📝 *Примеры:*
• `dir C:\\`
• `ping google.com`
• `tasklist | findstr chrome`
• `systeminfo | findstr "Общий объём"`

⚠️ *Осторожно!* Не выполняйте опасные команды.
        """
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

    async def execute_quick_cmd(self, query, cmd):
        """Выполнить быструю команду"""
        user_id = query.from_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await query.edit_message_text("❌ У вас нет прав!")
            return
            
        # Маппинг быстрых команд
        quick_commands = {
            'dir': 'dir',
            'tasklist': 'tasklist',
            'ipconfig': 'ipconfig /all',
            'systeminfo': 'systeminfo',
            'netstat': 'netstat -an',
            'wmic': 'wmic computersystem get model,name,manufacturer,systemtype'
        }
        
        command = quick_commands.get(cmd, cmd)
        
        await query.edit_message_text(
            f"⏳ Выполняю команду: `{command}`",
            parse_mode='Markdown'
        )
        
        try:
            import subprocess
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                encoding='cp866'  # Для Windows кодировки
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\n\n❌ Ошибки:\n{result.stderr}"
                
            if not output.strip():
                output = "ℹ️ Команда выполнена, но не вернула результат."
            
            # Ограничиваем длину вывода
            if len(output) > 4000:
                output = output[:4000] + "\n\n... (вывод обрезан)"
                
            keyboard = [
                [InlineKeyboardButton("⬅️ Назад", callback_data="cmd_menu")],
                [InlineKeyboardButton("🆕 Повторить", callback_data=f"quick_cmd_{cmd}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"📝 *Результат команды:* `{command}`\n\n```\n{output}\n```",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
        except subprocess.TimeoutExpired:
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="cmd_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"⏰ Команда `{command}` превысила лимит времени (30 сек).",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as e:
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="cmd_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"❌ Ошибка выполнения команды: {str(e)}",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

    def run(self):
        """Запуск бота (оптимизированный)"""
        if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
            print("❌ Укажите токен бота в переменной BOT_TOKEN!")
            return
        
        try:
            # Оптимизированное создание приложения
            self.app = (Application.builder()
                       .token(BOT_TOKEN)
                       .concurrent_updates(True)  # Параллельная обработка
                       .build())
            
            # Регистрация обработчиков
            self.app.add_handler(CommandHandler("start", self.start))
            self.app.add_handler(CommandHandler("sysinfo", lambda u, c: self.system_info(u)))
            self.app.add_handler(CommandHandler("processes", lambda u, c: self.show_processes(u)))
            self.app.add_handler(CommandHandler("files", lambda u, c: self.show_files(u)))
            self.app.add_handler(CommandHandler("screenshot", lambda u, c: self.take_screenshot(u)))
            self.app.add_handler(CommandHandler("webcam", lambda u, c: self.take_webcam_photo(u)))
            self.app.add_handler(CommandHandler("cmd", self.execute_command))
            self.app.add_handler(CommandHandler("shutdown", self.shutdown_pc))
            self.app.add_handler(CommandHandler("restart", self.restart_pc))
            self.app.add_handler(CommandHandler("sleep", self.sleep_pc))
            self.app.add_handler(CommandHandler("lock", self.lock_pc))
            self.app.add_handler(CommandHandler("adduser", self.add_user_command))
            self.app.add_handler(CommandHandler("request_access", self.request_access_command))
            self.app.add_handler(CallbackQueryHandler(self.button_handler))
            
            # Обработчик текстовых сообщений (для CMD команд)
            self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
            
            print("🤖 Бот запущен! (Оптимизированная версия)")
            logger.info("🚀 Бот готов к работе с оптимизациями производительности")
            
            # Оптимизированный запуск с обработкой ошибок
            self.app.run_polling(
                drop_pending_updates=True,  # Очищаем очередь при запуске
                close_loop=False  # Не закрываем event loop
            )
            
        except KeyboardInterrupt:
            logger.info("🛑 Получен сигнал остановки")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка бота: {e}")
            print(f"❌ Ошибка запуска бота: {e}")
        finally:
            # Очистка ресурсов
            if hasattr(self, '_cache'):
                self._cache.clear()
            gc.collect()  # Принудительная очистка памяти

if __name__ == "__main__":
    bot = PCControlBot()
    bot.run()
