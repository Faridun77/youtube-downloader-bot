import os
import logging
import tempfile
import re
import traceback
import yt_dlp
import telebot
from telebot import types
import threading
from datetime import datetime
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup
import json # Для работы с JSON файлом
from collections import deque # Для ограничения размера user_states

# Обновляем настройки логирования, чтобы логи писались в файл
LOG_FILE = 'bot_activity.log'
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler() # Также выводим в консоль
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# ВСТАВЬТЕ ВАШ ТОКЕН TELEGRAM БОТА ЗДЕСЬ
# ============================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8441105537:AAEGIxT6lUiPhxrhUbRWIiZ0l0DyeF1KcJ8")  # Берем из переменных окружения
# ============================================================

# ============================================================
# НАСТРОЙКИ АДМИН-ПАНЕЛИ
# Вставьте сюда Telegram ID пользователей, которые будут администраторами.
# Вы можете узнать свой ID, отправив сообщение @userinfobot в Telegram.
# Пример: ADMIN_IDS = [123456789, 987654321]
# ============================================================
ADMIN_IDS = [6977973828] # <-- ЗАМЕНИТЕ НА ВАШ TELEGRAM ID!
USERS_FILE = 'users.json' # Файл для хранения ID пользователей
# ============================================================

# Максимальный размер файла для Telegram (50MB)
MAX_TELEGRAM_FILE_SIZE = 50 * 1024 * 1024

# Регулярное выражение для проверки YouTube URL
YOUTUBE_REGEX = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})'

# Желаемые разрешения видео (теперь это высоты в пикселях)
DESIRED_HEIGHTS = [144, 240, 360, 480, 720, 1080]

# Создание экземпляра бота
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Хранение состояний пользователей (используем dict с ограничением размера)
MAX_USERS_IN_MEMORY_STATES = 10000
user_states = {}

# Стилизация бота
BOT_NAME = "YouTube Pro Скачивание"
BOT_LOGO = "📺"
PRIMARY_COLOR = "🔵"
SUCCESS_COLOR = "✅"
ERROR_COLOR = "❌"
WARNING_COLOR = "⚠️"
INFO_COLOR = "ℹ️"

def format_message(title, content, footer=None):
    """Форматирование сообщения в едином стиле."""
    message = f"{BOT_LOGO} *{BOT_NAME}* | *{title}*\n\n{content}"
    if footer:
        message += f"\n\n{footer}"
    return message

def is_youtube_url(url):
    """Проверка, является ли URL действительным YouTube URL."""
    match = re.search(YOUTUBE_REGEX, url)
    return bool(match)

def extract_video_id(url):
    """Извлечение ID видео из YouTube URL."""
    match = re.search(YOUTUBE_REGEX, url)
    if match:
        return match.group(1)
    return None

def get_clean_youtube_url(url):
    """Получение чистого YouTube URL без дополнительных параметров."""
    video_id = extract_video_id(url)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return url

def format_duration(seconds):
    """Форматирование продолжительности в секундах в читаемый формат."""
    if seconds is None:
        return "Неизвестно"

    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"

def format_filesize(bytes):
    """Форматирование размера файла в байтах в читаемый формат."""
    if not bytes:
        return "Неизвестно"

    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024
    return f"{bytes:.1f} TB"

def parse_resolution_height(resolution_str):
    """Извлекает высоту разрешения (например, 1080 из '1920x1080' или '1080p')."""
    if not resolution_str:
        return 0
    match_p = re.search(r'(\d+)p', resolution_str)
    if match_p:
        return int(match_p.group(1))
    match_x = re.search(r'x(\d+)', resolution_str)
    if match_x:
        return int(match_x.group(1))
    return 0

def search_youtube(query, max_results=5):
    """Поиск видео на YouTube."""
    try:
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://www.youtube.com/results?search_query={encoded_query}"
        response = requests.get(search_url)

        if response.status_code != 200:
            logger.error(f"Ошибка при поиске: статус {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        results = []
        video_ids = re.findall(r"watch\?v=(\S{11})", response.text)
        unique_ids = []

        for video_id in video_ids:
            if video_id not in unique_ids:
                unique_ids.append(video_id)
                if len(unique_ids) >= max_results:
                    break

        for video_id in unique_ids:
            try:
                with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                    info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                    if info:
                        results.append({
                            'id': video_id,
                            'title': info.get('title', 'Неизвестное название'),
                            'url': f"https://www.youtube.com/watch?v={video_id}",
                            'duration': info.get('duration', 0),
                            'uploader': info.get('uploader', 'Неизвестный автор'),
                            'view_count': info.get('view_count', 0),
                            'thumbnail': info.get('thumbnail', '')
                        })
            except Exception as e:
                logger.error(f"Ошибка при получении информации о видео {video_id}: {str(e)}")
                continue
        return results
    except Exception as e:
        logger.error(f"Ошибка при поиске видео: {str(e)}")
        logger.error(traceback.format_exc())
        return []

def get_video_info(url):
    """Получение информации о YouTube видео с помощью yt-dlp."""
    clean_url = get_clean_youtube_url(url)
    logger.info(f"Обработка URL: {clean_url}")

    ydl_opts = {
        'quiet': True,
        'no_warnings': False,
        'format': 'bestvideo+bestaudio/best', # Предпочитать объединение видео и аудио
        'noplaylist': True,
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        'ignoreerrors': True,
        'no_color': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.debug("Извлечение информации о видео...")
            info = ydl.extract_info(clean_url, download=False)

            if not info:
                logger.error("yt-dlp не вернул информацию")
                return None
            
            # Проверка, является ли видео прямой трансляцией
            if info.get('is_live'):
                logger.warning("Видео является прямой трансляцией, пропуск.")
                return None

            logger.debug(f"Название видео: {info.get('title')}")

            video_info = {
                'title': info.get('title', 'Неизвестное название'),
                'uploader': info.get('uploader', 'Неизвестный автор'),
                'duration': info.get('duration', 0),
                'view_count': info.get('view_count', 0),
                'upload_date': info.get('upload_date', ''),
                'thumbnail': info.get('thumbnail', ''),
                'formats': {'video': [], 'audio': None} # Добавлено для аудио
            }

            if video_info['upload_date']:
                try:
                    date_obj = datetime.strptime(video_info['upload_date'], '%Y%m%d')
                    video_info['upload_date'] = date_obj.strftime('%d.%m.%Y')
                except:
                    pass

            available_formats_by_height = {} # {height: {format_id: ..., filesize: ...}}
            best_audio_format = None

            for f in info.get('formats', []):
                filesize = f.get('filesize') or f.get('filesize_approx')
                
                # Собираем лучший аудиоформат
                if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                    if not best_audio_format or (filesize or 0) > (best_audio_format.get('filesize') or best_audio_format.get('filesize_approx') or 0):
                        best_audio_format = f
                
                # Собираем видеоформаты (включая комбинированные и видео-только)
                if f.get('vcodec') != 'none':
                    height = parse_resolution_height(f.get('resolution', ''))
                    if height == 0: # Если разрешение не удалось спарсить, пропускаем
                        continue

                    # Если формат уже содержит аудио, это предпочтительнее
                    is_combined = f.get('acodec') != 'none'
                    
                    current_best = available_formats_by_height.get(height)
                    
                    # Если для этой высоты еще нет формата, или найденный лучше
                    if not current_best or \
                       (is_combined and not current_best.get('is_combined')) or \
                       (is_combined == current_best.get('is_combined') and (filesize or 0) > (current_best.get('filesize') or 0)):
                        
                        available_formats_by_height[height] = {
                            'format_id': f['format_id'],
                            'resolution': f"{height}p",
                            'ext': f.get('ext', 'mp4'),
                            'filesize': filesize,
                            'format_note': f.get('format_note', ''),
                            'is_combined': is_combined # Флаг для комбинированных форматов
                        }
            
            final_formats_list = []
            for height in DESIRED_HEIGHTS:
                if height in available_formats_by_height:
                    fmt = available_formats_by_height[height]
                    # Если это видео-только формат и есть аудио, пытаемся объединить
                    if not fmt['is_combined'] and best_audio_format:
                        combined_filesize = (fmt['filesize'] or 0) + (best_audio_format.get('filesize') or best_audio_format.get('filesize_approx') or 0)
                        if combined_filesize < MAX_TELEGRAM_FILE_SIZE:
                            final_formats_list.append({
                                'format_id': f"{fmt['format_id']}+{best_audio_format['format_id']}",
                                'resolution': fmt['resolution'],
                                'ext': 'mp4', # Предполагаем mp4 после объединения
                                'filesize': combined_filesize,
                                'format_note': 'Video+Audio (merged)'
                            })
                    elif fmt['is_combined'] and (fmt['filesize'] or 0) < MAX_TELEGRAM_FILE_SIZE:
                        final_formats_list.append(fmt)
            
            # Добавляем любые другие комбинированные форматы, которые не попали в DESIRED_HEIGHTS, но подходят по размеру
            for height, fmt in available_formats_by_height.items():
                if fmt['is_combined'] and (fmt['filesize'] or 0) < MAX_TELEGRAM_FILE_SIZE:
                    # Проверяем, не добавили ли мы уже этот формат (по разрешению)
                    if not any(f['resolution'] == fmt['resolution'] for f in final_formats_list):
                        final_formats_list.append(fmt)

            # Сортировка по разрешению (по возрастанию)
            final_formats_list.sort(key=lambda x: parse_resolution_height(x['resolution']))

            video_info['formats']['video'] = final_formats_list

            # Добавляем лучший аудио-формат, если он есть и подходит по размеру
            if best_audio_format and (best_audio_format.get('filesize') or best_audio_format.get('filesize_approx') or 0) < MAX_TELEGRAM_FILE_SIZE:
                video_info['formats']['audio'] = {
                    'format_id': 'bestaudio', # Используем специальный format_id для аудио
                    'filesize': best_audio_format.get('filesize') or best_audio_format.get('filesize_approx'),
                    'ext': best_audio_format.get('ext', 'm4a') # По умолчанию m4a
                }

            # Если форматы не найдены, добавляем резервный вариант с лучшим качеством
            if not video_info['formats']['video'] and not video_info['formats']['audio']:
                logger.warning("Подходящие форматы не найдены, добавляем лучший формат как резервный")
                video_info['formats']['video'] = [{
                    'format_id': 'best',
                    'resolution': 'Лучшее качество',
                    'ext': 'mp4',
                    'filesize': 0, # Заполнитель, фактический размер будет определен при загрузке
                    'format_note': 'Автоматически выбранное лучшее качество'
                }]

            return video_info

    except Exception as e:
        logger.error(f"Ошибка при получении информации о видео: {str(e)}")
        logger.error(traceback.format_exc())
        return None

def upload_to_transfersh(file_path):
    """Загружает файл на transfer.sh и возвращает прямую ссылку."""
    try:
        file_name = os.path.basename(file_path)
        with open(file_path, 'rb') as f:
            response = requests.put(f'https://transfer.sh/{file_name}', data=f)
            response.raise_for_status() # Вызовет исключение для HTTP ошибок
            return response.text.strip()
    except Exception as e:
        logger.error(f"Ошибка при загрузке файла {file_path} на transfer.sh: {e}")
        return None

def download_video(chat_id, url, format_id, message_id):
    """Скачивание видео и отправка его пользователю."""
    try:
        bot.edit_message_text(
            format_message(
                "Загрузка",
                f"{PRIMARY_COLOR} Загрузка началась. Пожалуйста, подождите...\n"
                f"⏳ Подготовка к з��грузке..."
            ),
            chat_id=chat_id,
            message_id=message_id,
            parse_mode='Markdown'
        )

        clean_url = get_clean_youtube_url(url)

        # Используем TemporaryDirectory для автоматического удаления файлов
        with tempfile.TemporaryDirectory() as temp_dir:
            ydl_opts = {
                'format': format_id,
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'noplaylist': True,
                'geo_bypass': True,
                'geo_bypass_country': 'US',
                'progress_hooks': [],
                'ignoreerrors': False,
                'no_color': True,
                'verbose': True,
            }

            # Специальная обработка для аудио
            if format_id == 'bestaudio':
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['outtmpl'] = os.path.join(temp_dir, '%(title)s.%(ext)s') # yt-dlp сам выберет расширение (m4a, webm)
                # УДАЛЕНА ЧАСТЬ КОДА ДЛЯ КОНВЕРТАЦИИ В MP3
                # ydl_opts['postprocessors'] = [{
                #     'key': 'FFmpegExtractAudio',
                #     'preferredcodec': 'mp3',
                #     'preferredquality': '192', # Качество MP3 (например, 192kbps)
                # }]

            def progress_hook(d):
                if d['status'] == 'downloading':
                    if 'total_bytes' in d and d['total_bytes'] > 0:
                        percent = d['downloaded_bytes'] / d['total_bytes'] * 100
                        downloaded = format_filesize(d['downloaded_bytes'])
                        total = format_filesize(d['total_bytes'])
                        speed = format_filesize(d.get('speed', 0)) + '/s'

                        if int(percent) % 10 == 0:
                            try:
                                bot.edit_message_text(
                                    format_message(
                                        "Загрузка",
                                        f"{PRIMARY_COLOR} Загрузка в процессе...\n\n"
                                        f"📊 Прогресс: {int(percent)}%\n"
                                        f"📦 Размер: {downloaded} / {total}\n"
                                        f"🚀 Скорость: {speed}"
                                    ),
                                    chat_id=chat_id,
                                    message_id=message_id,
                                    parse_mode='Markdown'
                                )
                            except:
                                pass
                elif d['status'] == 'error':
                    logger.error(f"Ошибка загрузки: {d.get('error')}")

            ydl_opts['progress_hooks'].append(progress_hook)

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(clean_url, download=True)
                    if not info:
                        raise Exception("Не удалось загрузить видео. Видео может быть недоступно.")

                    downloaded_file = ydl.prepare_filename(info)

                    if not os.path.exists(downloaded_file):
                        files = os.listdir(temp_dir)
                        if files:
                            for file in files:
                                # Ищем mp4, webm, m4a, mp3
                                # Обновлено: теперь ищем также .webm для аудио
                                if file.endswith(('.mp4', '.webm', '.m4a', '.mp3')):
                                    downloaded_file = os.path.join(temp_dir, file)
                                    break
                        else:
                            raise Exception("Загрузка не удалась. Файл не был создан.")

                bot.edit_message_text(
                    format_message(
                        "Отправка",
                        f"{PRIMARY_COLOR} Загрузка завершена! Отправка в Telegram...\n\n"
                        f"⬆️ Пожалуйста, подождите, пока мы отправляем ваш файл..."
                    ),
                    chat_id=chat_id,
                    message_id=message_id,
                    parse_mode='Markdown'
                )

                file_size = os.path.getsize(downloaded_file)

                if file_size > MAX_TELEGRAM_FILE_SIZE:
                    bot.edit_message_text(
                        format_message(
                            "Видео слишком большое",
                            f"{ERROR_COLOR} Видеофайл ({format_filesize(file_size)}) превышает лимит Telegram в 50МБ и не может быть загружен.\n\n"
                            f"Пожалуйста, выберите другое качество или другое видео."
                        ),
                        chat_id=chat_id,
                        message_id=message_id,
                        parse_mode='Markdown'
                    )
                else:
                    # Существующий код для отправки файлов <= 50МБ
                    with open(downloaded_file, 'rb') as media_file:
                        # Обновлено: теперь проверяем и .webm для отправки как аудио
                        if format_id == 'bestaudio' or downloaded_file.endswith(('.m4a', '.mp3', '.webm')):
                            bot.send_audio(
                                chat_id=chat_id,
                                audio=media_file,
                                caption=format_message(
                                    "Аудио загружено",
                                    f"🎵 *{info['title']}*\n\n"
                                    f"👤 Канал: {info.get('uploader', 'Неизвестно')}\n"
                                    f"⏱️ Длительность: {format_duration(info.get('duration', 0))}"
                                ),
                                parse_mode='Markdown'
                            )
                        else:
                            bot.send_video(
                                chat_id=chat_id,
                                video=media_file,
                                caption=format_message(
                                    "Видео загружено",
                                    f"📹 *{info['title']}*\n\n"
                                    f"👤 Канал: {info.get('uploader', 'Неизвестно')}\n"
                                    f"⏱️ Длительность: {format_duration(info.get('duration', 0))}"
                                ),
                                parse_mode='Markdown',
                                supports_streaming=True
                            )

                    bot.edit_message_text(
                        format_message(
                            "Успех",
                            f"{SUCCESS_COLOR} Загрузка завершена!\n\n"
                            f"📝 Название: *{info['title']}*\n"
                            f"👤 Канал: {info.get('uploader', 'Неизвестно')}\n"
                            f"⏱️ Длительность: {format_duration(info.get('duration', 0))}\n\n"
                            f"Отправьте еще одну ссылку на YouTube, чтобы загрузить больше видео."
                        ),
                        chat_id=chat_id,
                        message_id=message_id,
                        parse_mode='Markdown'
                    )

            except yt_dlp.utils.DownloadError as e:
                logger.error(f"Ошибка загрузки yt-dlp: {str(e)}")
                if format_id != 'best':
                    bot.edit_message_text(
                        format_message(
                            "Повторная попытка",
                            f"{WARNING_COLOR} Не удалось загрузить в выбранном качестве. Пробуем с лучшим качеством...\n\n"
                            f"Пожалуйста, подождите, пока мы пробуем альтернативный метод."
                        ),
                        chat_id=chat_id,
                        message_id=message_id,
                        parse_mode='Markdown'
                    )
                    thread = threading.Thread(
                        target=download_video, 
                        args=(chat_id, url, 'best', message_id)
                    )
                    thread.daemon = True
                    thread.start()
                    return
                else:
                    bot.edit_message_text(
                        format_message(
                            "Ошибка",
                            f"{ERROR_COLOR} Загрузка не удалась!\n\n"
                            f"Ошибка: {str(e)}\n\n"
                            f"Пожалуйста, попробуйте другое видео или другое качество."
                        ),
                        chat_id=chat_id,
                        message_id=message_id,
                        parse_mode='Markdown'
                    )

    except Exception as e:
        logger.error(f"Ошибка при загрузке видео: {str(e)}")
        logger.error(traceback.format_exc())
        if format_id != 'best':
            bot.edit_message_text(
                format_message(
                    "Повторная попытка",
                    f"{WARNING_COLOR} Произошла ошибка. Пробуем с лучшим качеством...\n\n"
                    f"Пожалуйста, подождите, пока мы пробуем альтернативный метод."
                ),
                chat_id=chat_id,
                message_id=message_id,
                parse_mode='Markdown'
            )
            try:
                thread = threading.Thread(
                    target=download_video, 
                    args=(chat_id, url, 'best', message_id)
                )
                thread.daemon = True
                thread.start()
                return
            except:
                pass
        bot.edit_message_text(
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} Загрузка не удалась!\n\n"
                f"Ошибка: {str(e)}\n\n"
                f"Пожалуйста, попробуйте другое видео или другое качество."
            ),
            chat_id=chat_id,
            message_id=message_id,
            parse_mode='Markdown'
        )

# --- Функции для работы с пользователями и админ-панелью ---

def load_users():
    """Загружает список chat_id пользователей из файла."""
    if not os.path.exists(USERS_FILE):
        return []
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.error(f"Ошибка чтения файла {USERS_FILE}. Файл поврежден или пуст.")
        return []

def save_users(user_list):
    """Сохраняет список chat_id пользователей в файл."""
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(user_list, f)
    except Exception as e:
        logger.error(f"Ошибка записи в файл {USERS_FILE}: {e}")

def add_user_to_list(chat_id):
    """Добавляет chat_id пользователя в список, если его там нет."""
    users = load_users()
    if chat_id not in users:
        users.append(chat_id)
        save_users(users)
        logger.info(f"Добавлен новый пользователь: {chat_id}. Всего пользователей: {len(users)}")

def is_admin(user_id):
    """Проверяет, является ли пользователь администратором."""
    return user_id in ADMIN_IDS

# --- Обработчики сообщений и колбэков ---

@bot.message_handler(commands=['start'])
def handle_start(message):
    """Обработка команды /start."""
    add_user_to_list(message.chat.id) # Сохраняем ID пользователя
    bot.reply_to(
        message,
        format_message(
            "Добро пожаловать",
            f"👋 Добро пожаловать в {BOT_NAME}!\n\n"
            f"Этот бот позволяет скачивать видео с YouTube в различных качествах.\n\n"
            f"🔹 *Доступные команды:*\n"
            f"/mp4 [ссылка] - Скачать видео в формате MP4\n"
            f"/search [запрос] - Поиск видео на YouTube\n"
            f"/help - Показать справку\n\n"
            f"Также вы можете просто отправить ссылку на YouTube для начала загрузки!"
        ),
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['help'])
def handle_help(message):
    """Обработка команды /help."""
    add_user_to_list(message.chat.id) # Сохраняем ID пользователя
    bot.reply_to(
        message,
        format_message(
            "Помощь",
            f"📚 *Как использовать {BOT_NAME}:*\n\n"
            f"1️⃣ *Отправьте ссылку на YouTube*\n"
            f"   - Бот проанализирует видео\n\n"
            f"2️⃣ *Выберите качество видео*\n"
            f"   - Разные разрешения (144p - 1080p)\n\n"
            f"3️⃣ *Дождитесь загрузки*\n"
            f"   - Бот загрузит и отправит ваше видео\n\n"
            f"🔹 *Быстрые команды:*\n"
            f"/mp4 [ссылка] - Скачать видео в формате MP4\n"
            f"/search [запрос] - Поиск видео на YouTube\n\n"
            f"⚠️ Примечание: Из-за ограничений Telegram, файлы ограничены размером 50МБ."
        ),
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['admin'])
def handle_admin_command(message):
    """Обработка команды /admin."""
    if not is_admin(message.from_user.id):
        bot.reply_to(
            message,
            format_message(
                "Доступ запрещен",
                f"{ERROR_COLOR} У вас нет прав администратора для доступа к этой панели."
            ),
            parse_mode='Markdown'
        )
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("Отправить рассылку", callback_data="admin_broadcast_start"))
    markup.add(types.InlineKeyboardButton("Отправить фото с кнопками", callback_data="admin_photo_broadcast_start")) # Новая кнопка
    markup.add(types.InlineKeyboardButton("Количество пользователей", callback_data="admin_user_count"))
    markup.add(types.InlineKeyboardButton("Отправить сообщение пользователю", callback_data="admin_send_message_start"))
    markup.add(types.InlineKeyboardButton("Получить логи бота", callback_data="admin_get_logs"))
    
    bot.reply_to(
        message,
        format_message(
            "Админ-панель",
            f"{INFO_COLOR} Добро пожаловать в админ-панель!"
        ),
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data == 'admin_broadcast_start')
def admin_broadcast_start(call):
    """Начало процесса рассылки."""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Доступ запрещен", show_alert=True)
        return
    
    bot.answer_callback_query(call.id)
    msg = bot.edit_message_text(
        format_message(
            "Рассылка",
            f"{PRIMARY_COLOR} Отправьте сообщение, которое вы хотите разослать всем пользователям."
        ),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, send_broadcast_message)

def send_broadcast_message(message):
    """Отправляет сообщение всем пользователям."""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, format_message("Доступ запрещен", f"{ERROR_COLOR} У вас нет прав администратора."), parse_mode='Markdown')
        return

    broadcast_text = message.text
    all_users = load_users()
    sent_count = 0
    blocked_count = 0

    bot.send_message(
        message.chat.id,
        format_message(
            "Рассылка",
            f"{PRIMARY_COLOR} Начинаю рассылку сообщения {len(all_users)} пользователям..."
        ),
        parse_mode='Markdown'
    )

    for user_id in all_users:
        try:
            bot.send_message(user_id, broadcast_text, parse_mode='Markdown')
            sent_count += 1
            time.sleep(0.1) # Небольшая задержка, чтобы избежать флуда
        except telebot.apihelper.ApiTelegramException as e:
            if e.error_code == 403: # Пользователь заблокировал бота
                blocked_count += 1
                logger.warning(f"Пользователь {user_id} заблокировал бота. Ошибка: {e}")
            else:
                logger.error(f"Ошибка при отправке сообщения пользователю {user_id}: {e}")
        except Exception as e:
            logger.error(f"Неизвестная ошибка при отправке сообщения пользователю {user_id}: {e}")

    bot.send_message(
        message.chat.id,
        format_message(
            "Рассылка завершена",
            f"{SUCCESS_COLOR} Рассылка завершена!\n\n"
            f"✅ Отправлено: {sent_count}\n"
            f"🚫 Заблокировано/Ошибка: {blocked_count}"
        ),
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data == 'admin_photo_broadcast_start')
def admin_photo_broadcast_start(call):
    """Начало процесса рассылки фото с кнопками."""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Доступ запрещен", show_alert=True)
        return
    
    bot.answer_callback_query(call.id)
    msg = bot.edit_message_text(
        format_message(
            "Рассылка фото",
            f"{PRIMARY_COLOR} Отправьте фото, которое вы хотите разослать. После отправки фото, я попрошу вас ввести текст и кнопки."
        ),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, receive_broadcast_photo)

def receive_broadcast_photo(message):
    """Получает фото для рассылки и запрашивает текст/кнопки."""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, format_message("Доступ запрещен", f"{ERROR_COLOR} У вас нет прав администратора."), parse_mode='Markdown')
        return

    if not message.photo:
        msg = bot.reply_to(
            message,
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} Пожалуйста, отправьте фото. Если вы хотите отправить только текст, используйте обычную рассылку."
            ),
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(msg, receive_broadcast_photo) # Повторяем запрос фото
        return

    # Сохраняем file_id самого большого размера фото
    photo_file_id = message.photo[-1].file_id
    user_states[message.chat.id] = {'photo_file_id': photo_file_id}

    msg = bot.reply_to(
        message,
        format_message(
            "Текст и кнопки",
            f"{PRIMARY_COLOR} Теперь отправьте текст для подписи к фото и, если нужно, инлайн-кнопки.\n\n"
            f"Формат для кнопок: `[Текст кнопки](URL)`\n"
            f"Каждая кнопка с новой строки.\n\n"
            f"Пример:\n"
            f"Привет всем!\n"
            f"[Наш сайт](https://example.com)\n"
            f"[Наш канал](https://t.me/your_channel)"
        ),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, receive_broadcast_photo_details)

def parse_inline_buttons(text):
    """Парсит текст на предмет инлайн-кнопок."""
    buttons = []
    # Регулярное выражение для поиска [Текст кнопки](URL)
    # Оно должно быть в начале строки или после новой строки
    button_regex = re.compile(r'^\[([^\]]+)\]$$(https?:\/\/[^)]+)$$$', re.MULTILINE)
    
    lines = text.split('\n')
    caption_lines = []

    for line in lines:
        match = button_regex.match(line.strip())
        if match:
            button_text = match.group(1)
            button_url = match.group(2)
            buttons.append(types.InlineKeyboardButton(text=button_text, url=button_url))
        else:
            caption_lines.append(line)
    
    caption = "\n".join(caption_lines).strip()
    return caption, buttons

def receive_broadcast_photo_details(message):
    """Получает детали рассылки (текст и кнопки) и отправляет фото."""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, format_message("Доступ запрещен", f"{ERROR_COLOR} У вас нет прав администратора."), parse_mode='Markdown')
        return

    chat_id = message.chat.id
    if chat_id not in user_states or 'photo_file_id' not in user_states[chat_id]:
        bot.reply_to(
            message,
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} Сессия истекла. Пожалуйста, начните рассылку фото заново."
            ),
            parse_mode='Markdown'
        )
        return

    photo_file_id = user_states[chat_id].pop('photo_file_id') # Извлекаем и удаляем file_id
    
    caption_and_buttons_text = message.text
    caption, buttons = parse_inline_buttons(caption_and_buttons_text)

    markup = None
    if buttons:
        markup = types.InlineKeyboardMarkup()
        for button in buttons:
            markup.add(button) # Добавляем каждую кнопку в отдельный ряд

    all_users = load_users()
    sent_count = 0
    blocked_count = 0

    bot.send_message(
        chat_id,
        format_message(
            "Рассылка фото",
            f"{PRIMARY_COLOR} Начинаю рассылку фото {len(all_users)} пользователям..."
        ),
        parse_mode='Markdown'
    )

    for user_id in all_users:
        try:
            bot.send_photo(
                chat_id=user_id,
                photo=photo_file_id,
                caption=caption,
                reply_markup=markup,
                parse_mode='Markdown' # Если хотите, чтобы подпись поддерживала Markdown
            )
            sent_count += 1
            time.sleep(0.1) # Небольшая задержка
        except telebot.apihelper.ApiTelegramException as e:
            if e.error_code == 403: # Пользователь заблокировал бота
                blocked_count += 1
                logger.warning(f"Пользователь {user_id} заблокировал бота. Ошибка: {e}")
            else:
                logger.error(f"Ошибка при отправке фото пользователю {user_id}: {e}")
        except Exception as e:
            logger.error(f"Неизвестная ошибка при отправке фото пользователю {user_id}: {e}")

    bot.send_message(
        chat_id,
        format_message(
            "Рассылка фото завершена",
            f"{SUCCESS_COLOR} Рассылка фото завершена!\n\n"
            f"✅ Отправлено: {sent_count}\n"
            f"🚫 Заблокировано/Ошибка: {blocked_count}"
        ),
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data == 'admin_user_count')
def admin_user_count(call):
    """Показывает количество пользователей."""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Доступ запрещен", show_alert=True)
        return
    
    bot.answer_callback_query(call.id)
    users = load_users()
    bot.edit_message_text(
        format_message(
            "Количество пользователей",
            f"{INFO_COLOR} Всего уникальных пользователей: *{len(users)}*"
        ),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['mp4'])
def handle_mp4_command(message):
    """Обработка команды /mp4 для прямой загрузки видео."""
    add_user_to_list(message.chat.id) # Сохраняем ID пользователя
    chat_id = message.chat.id
    text = message.text.strip()

    parts = text.split(' ', 1)
    if len(parts) < 2:
        bot.reply_to(
            message,
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} Пожалуйста, укажите ссылку на YouTube после команды.\n\n"
                f"Пример: /mp4 https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            ),
            parse_mode='Markdown'
        )
        return

    url = parts[1].strip()

    if not is_youtube_url(url):
        bot.reply_to(
            message,
            format_message(
                "Неверный ввод",
                f"{ERROR_COLOR} Пожалуйста, укажите действительную ссылку на YouTube.\n\n"
                f"Пример: /mp4 https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            ),
            parse_mode='Markdown'
        )
        return

    processing_message = bot.send_message(
        chat_id=chat_id,
        text=format_message(
            "Обработка MP4",
            f"{PRIMARY_COLOR} Подготовка к загрузке видео...\n\n"
            f"⏳ Пожалуйста, подождите, пока мы анализируем видео..."
        ),
        parse_mode='Markdown'
    )

    user_states[chat_id] = {
        'youtube_url': url,
        'message_id': processing_message.message_id
    }

    thread = threading.Thread(
        target=download_video, 
        args=(chat_id, url, 'best', processing_message.message_id)
    )
    thread.daemon = True
    thread.start()

@bot.message_handler(commands=['search'])
def handle_search_command(message):
    """Обработка команды /search для поиска видео на YouTube."""
    add_user_to_list(message.chat.id) # Сохраняем ID пользователя
    chat_id = message.chat.id
    text = message.text.strip()

    parts = text.split(' ', 1)
    if len(parts) < 2:
        bot.reply_to(
            message,
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} Пожалуйста, укажите запрос для поиска после команды.\n\n"
                f"Пример: /search лучшие песни 2023"
            ),
            parse_mode='Markdown'
        )
        return

    query = parts[1].strip()

    search_message = bot.send_message(
        chat_id=chat_id,
        text=format_message(
            "Поиск",
            f"{PRIMARY_COLOR} Поиск видео на YouTube...\n\n"
            f"🔍 Запрос: *{query}*\n"
            f"⏳ Пожалуйста, подождите..."
        ),
        parse_mode='Markdown'
    )

    results = search_youtube(query)

    if not results:
        bot.edit_message_text(
            format_message(
                "Результаты поиска",
                f"{WARNING_COLOR} По вашему запросу ничего не найдено.\n\n"
                f"Попробуйте изменить запрос и повторить поиск."
            ),
            chat_id=chat_id,
            message_id=search_message.message_id,
            parse_mode='Markdown'
        )
        return

    result_text = f"{SUCCESS_COLOR} Найдено {len(results)} видео по запросу: *{query}*\n\n"

    for i, video in enumerate(results, 1):
        views_formatted = f"{video['view_count']:,}" if video['view_count'] else "Неизвестно"
        result_text += f"*{i}. {video['title']}*\n"
        result_text += f"👤 {video['uploader']}\n"
        result_text += f"⏱️ {format_duration(video['duration'])}\n"
        result_text += f"👁️ {views_formatted} просмотров\n\n"

    markup = types.InlineKeyboardMarkup()

    for i, video in enumerate(results, 1):
        markup.add(types.InlineKeyboardButton(
            text=f"{i}. {video['title'][:30]}...",
            callback_data=f"search_result_{i-1}"
        ))

    user_states[chat_id] = {
        'search_results': results,
        'message_id': search_message.message_id
    }

    bot.edit_message_text(
        format_message(
            "Результаты поиска",
            result_text
        ),
        chat_id=chat_id,
        message_id=search_message.message_id,
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('search_result_'))
def handle_search_result_selection(call):
    """Обработка выбора результата поиска."""
    add_user_to_list(call.message.chat.id) # Сохраняем ID пользователя
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    bot.answer_callback_query(call.id)

    result_index = int(call.data.split('_')[2])

    if chat_id not in user_states or 'search_results' not in user_states[chat_id]:
        bot.edit_message_text(
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} Сессия истекла. Пожалуйста, выполните поиск снова."
            ),
            chat_id=chat_id,
            message_id=message_id,
            parse_mode='Markdown'
        )
        return

    results = user_states[chat_id]['search_results']

    if result_index < 0 or result_index >= len( results):
        bot.edit_message_text(
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} Неверный выбор. Пожалуйста, выполните поиск снова."
            ),
            chat_id=chat_id,
            message_id=message_id,
            parse_mode='Markdown'
        )
        return

    # Получаем выбранное видео
    video = results[result_index]
    youtube_url = video['url']

    # Отправка сообщения "обработка"
    bot.edit_message_text(
        format_message(
            "Обработка",
            f"{PRIMARY_COLOR} Анализ выбранного видео...\n\n"
            f"⏳ Пожалуйста, подождите, пока мы получаем информацию о видео..."
        ),
        chat_id=chat_id,
        message_id=message_id,
        parse_mode='Markdown'
    )

    try:
        video_info = get_video_info(youtube_url)

        if not video_info:
            bot.edit_message_text(
                format_message(
                    "Ошибка",
                    f"{ERROR_COLOR} Не удалось получить информацию о видео или это прямая трансляция.\n\n"
                    f"Пожалуйста, убедитесь, что ссылка действительна и видео не является прямой трансляцией."
                ),
                chat_id=chat_id,
                message_id=message_id,
                parse_mode='Markdown'
            )
            return

        # Сохранение URL и информации о видео в состояниях пользователя
        user_states[chat_id] = {
            'youtube_url': youtube_url,
            'video_info': video_info,
            'message_id': message_id # Обновляем message_id для текущего сообщения
        }

        views_formatted = f"{video_info['view_count']:,}" if video_info['view_count'] else "Неизвестно"
        upload_date = video_info['upload_date'] if video_info['upload_date'] else "Неизвестно"

        has_video_formats = len(video_info['formats']['video']) > 0
        has_audio_format = video_info['formats']['audio'] is not None

        if not has_video_formats and not has_audio_format:
            bot.edit_message_text(
                format_message(
                    "Прямая загрузка",
                    f"{WARNING_COLOR} Не найдены подходящие форматы видео или аудио (возможно, из-за размера > 50МБ).\n\n"
                    f"Пожалуйста, попробуйте другое видео."
                ),
                chat_id=chat_id,
                message_id=message_id,
                parse_mode='Markdown'
            )
            return

        message_text = format_message(
            "Видео найдено",
            f"📹 *{video_info['title']}*\n\n"
            f"👤 Канал: {video_info['uploader']}\n"
            f"⏱️ Длительность: {format_duration(video_info['duration'])}\n"
            f"👁️ Просмотры: {views_formatted}\n"
            f"📅 Загружено: {upload_date}\n\n"
            f"Пожалуйста, выберите качество для загрузки (файлы > 50МБ не отображаются):"
        )

        markup = types.InlineKeyboardMarkup(row_width=2)

        # Добавление вариантов качества видео
        for fmt in video_info['formats']['video']:
            size_mb = fmt['filesize'] / (1024 * 1024) if fmt['filesize'] else 0
            button_text = f"📹 {fmt['resolution']} ({size_mb:.1f} MB)"
            markup.add(types.InlineKeyboardButton(
                text=button_text,
                callback_data=f"quality_{fmt['format_id']}"
            ))
        
        # Добавление кнопки для аудио
        if has_audio_format:
            audio_size_mb = video_info['formats']['audio']['filesize'] / (1024 * 1024)
            markup.add(types.InlineKeyboardButton(
                text=f"🎵 Аудио ({audio_size_mb:.1f} MB)",
                callback_data=f"quality_bestaudio"
            ))

        # Добавление кнопки быстрой загрузки (лучшее качество)
        markup.add(types.InlineKeyboardButton(
            text="⚡ Быстрая загрузка (Лучшее качество)",
            callback_data="quality_best"
        ))

        # Добавление кнопки назад к результатам поиска
        markup.add(types.InlineKeyboardButton(
            text="⬅️ Вернуться к результатам поиска",
            callback_data="back_to_search"
        ))

        bot.edit_message_text(
            message_text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=markup,
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Ошибка обработки выбранного видео из поиска: {str(e)}")
        logger.error(traceback.format_exc())
        bot.edit_message_text(
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} Произошла ошибка при обработке выбранного видео.\n\n"
                f"Пожалуйста, попробуйте еще раз или выберите другое видео."
            ),
            chat_id=chat_id,
            message_id=message_id,
            parse_mode='Markdown'
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('search_quality_'))
def handle_search_quality_selection(call):
    """Обработка выбора качества для результата поиска."""
    add_user_to_list(call.message.chat.id) # Сохраняем ID пользователя
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    bot.answer_callback_query(call.id)

    parts = call.data.split('_')
    quality = parts[2]
    result_index = int(parts[3]) # Этот индекс больше не используется для получения URL, но сохраним его для совместимости

    if chat_id not in user_states or 'search_results' not in user_states[chat_id]:
        bot.edit_message_text(
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} Сессия истекла. Пожалуйста, выполните поиск снова."
            ),
            chat_id=chat_id,
            message_id=message_id,
            parse_mode='Markdown'
        )
        return

    # Получаем URL из текущего состояния, которое было установлено в handle_search_result_selection
    url = user_states[chat_id].get('youtube_url')
    if not url:
        bot.edit_message_text(
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} Не удалось найти URL видео для загрузки. Пожалуйста, попробуйте снова."
            ),
            chat_id=chat_id,
            message_id=message_id,
            parse_mode='Markdown'
        )
        return

    # Обновление сообщения
    bot.edit_message_text(
        format_message(
            "Загрузка видео",
            f"{PRIMARY_COLOR} Подготовка к загрузке...\n\n"
            f"⏳ Пожалуйста, подождите..."
        ),
        chat_id=chat_id,
        message_id=message_id,
        parse_mode='Markdown'
    )

    thread = threading.Thread(
        target=download_video, 
        args=(chat_id, url, quality, message_id)
    )
    thread.daemon = True
    thread.start()

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_search')
def handle_back_to_search(call):
    """Обработка кнопки назад к результатам поиска."""
    add_user_to_list(call.message.chat.id) # Сохраняем ID пользователя
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    bot.answer_callback_query(call.id)

    if chat_id not in user_states or 'search_results' not in user_states[chat_id]:
        bot.edit_message_text(
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} Сессия истекла. Пожалуйста, выполните поиск снова."
            ),
            chat_id=chat_id,
            message_id=message_id,
            parse_mode='Markdown'
        )
        return

    results = user_states[chat_id]['search_results']

    result_text = f"{SUCCESS_COLOR} Найдено {len(results)} видео\n\n"

    for i, video in enumerate(results, 1):
        views_formatted = f"{video['view_count']:,}" if video['view_count'] else "Неизвестно"
        result_text += f"*{i}. {video['title']}*\n"
        result_text += f"👤 {video['uploader']}\n"
        result_text += f"⏱️ {format_duration(video['duration'])}\n"
        result_text += f"👁️ {views_formatted} просмотров\n\n"

    markup = types.InlineKeyboardMarkup()

    for i, video in enumerate(results, 1):
        markup.add(types.InlineKeyboardButton(
            text=f"{i}. {video['title'][:30]}...",
            callback_data=f"search_result_{i-1}"
        ))

    bot.edit_message_text(
        format_message(
            "Результаты поиска",
            result_text
        ),
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """Обработка всех сообщений и проверка, содержат ли они URL YouTube."""
    add_user_to_list(message.chat.id) # Сохраняем ID пользователя
    text = message.text.strip()
    chat_id = message.chat.id

    youtube_url = None

    if is_youtube_url(text):
        youtube_url = text
    else:
        words = text.split()
        for word in words:
            if is_youtube_url(word):
                youtube_url = word
                break

    if youtube_url:
        # cleanup_user_states() # Эта функция больше не нужна, так как user_states используется для временных данных

        processing_message = bot.send_message(
            chat_id=chat_id,
            text=format_message(
                "Обработка",
                f"{PRIMARY_COLOR} Анализ вашей ссылки на YouTube...\n\n"
                f"⏳ Пожалуйста, подождите, пока мы получаем информацию о видео..."
            ),
            parse_mode='Markdown'
        )

        try:
            video_info = get_video_info(youtube_url)

            if not video_info:
                bot.edit_message_text(
                    format_message(
                        "Ошибка",
                        f"{ERROR_COLOR} Не удалось получить информацию о видео или это прямая трансляция.\n\n"
                        f"Пожалуйста, убедитесь, что ссылка действительна и видео не является прямой трансляцией."
                    ),
                    chat_id=chat_id,
                    message_id=processing_message.message_id,
                    parse_mode='Markdown'
                )
                return

            user_states[chat_id] = {
                'youtube_url': youtube_url,
                'video_info': video_info,
                'message_id': processing_message.message_id
            }

            views_formatted = f"{video_info['view_count']:,}" if video_info['view_count'] else "Неизвестно"
            upload_date = video_info['upload_date'] if video_info['upload_date'] else "Неизвестно"

            has_video_formats = len(video_info['formats']['video']) > 0
            has_audio_format = video_info['formats']['audio'] is not None

            if not has_video_formats and not has_audio_format:
                bot.edit_message_text(
                    format_message(
                        "Прямая загрузка",
                        f"{WARNING_COLOR} Не найдены подходящие форматы видео или аудио (возможно, из-за размера > 50МБ).\n\n"
                        f"Пожалуйста, попробуйте другое видео."
                    ),
                    chat_id=chat_id,
                    message_id=processing_message.message_id,
                    parse_mode='Markdown'
                )
                return

            message_text = format_message(
                "Видео найдено",
                f"📹 *{video_info['title']}*\n\n"
                f"👤 Канал: {video_info['uploader']}\n"
                f"⏱️ Длительность: {format_duration(video_info['duration'])}\n"
                f"👁️ Просмотры: {views_formatted}\n"
                f"📅 Загружено: {upload_date}\n\n"
                f"Пожалуйста, выберите качество для загрузки (файлы > 50МБ не отображаются):"
            )

            markup = types.InlineKeyboardMarkup(row_width=2)

            for fmt in video_info['formats']['video']:
                size_mb = fmt['filesize'] / (1024 * 1024) if fmt['filesize'] else 0
                button_text = f"📹 {fmt['resolution']} ({size_mb:.1f} MB)"

                markup.add(types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"quality_{fmt['format_id']}"
                ))
            
            # Добавление кнопки для аудио
            if has_audio_format:
                audio_size_mb = video_info['formats']['audio']['filesize'] / (1024 * 1024)
                markup.add(types.InlineKeyboardButton(
                    text=f"🎵 Аудио ({audio_size_mb:.1f} MB)",
                    callback_data=f"quality_bestaudio"
                ))

            markup.add(types.InlineKeyboardButton(
                text="⚡ Быстрая загрузка (Лучшее качество)",
                callback_data="quality_best"
            ))

            bot.edit_message_text(
                message_text,
                chat_id=chat_id,
                message_id=processing_message.message_id,
                reply_markup=markup,
                parse_mode='Markdown'
            )

        except Exception as e:
            logger.error(f"Ошибка обработки URL YouTube: {str(e)}")
            logger.error(traceback.format_exc())

            bot.edit_message_text(
                format_message(
                    "Ошибка",
                    f"{ERROR_COLOR} Произошла ошибка при обработке видео.\n\n"
                    f"Пожалуйста, попробуйте еще раз или отправьте другую ссылку."
                ),
                chat_id=chat_id,
                message_id=processing_message.message_id,
                parse_mode='Markdown'
            )
    else:
        if len(text) > 3:
            if chat_id not in user_states:
                user_states[chat_id] = {}
            if 'pending_search_queries' not in user_states[chat_id]:
                user_states[chat_id]['pending_search_queries'] = {}
            
            query_key = str(int(time.time()))
            user_states[chat_id]['pending_search_queries'][query_key] = text

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                text=f"🔍 Искать: {text[:50]}...",
                callback_data=f"do_search_key_{query_key}"
            ))

            bot.reply_to(
                message,
                format_message(
                    "Поиск",
                    f"{INFO_COLOR} Это не похоже на ссылку YouTube. Хотите выполнить поиск?\n\n"
                    f"Запрос: *{text}*"
                ),
                reply_markup=markup,
                parse_mode='Markdown'
            )

@bot.callback_query_handler(func=lambda call: call.data.startswith('do_search_key_'))
def handle_do_search(call):
    """Обработка запроса на поиск."""
    add_user_to_list(call.message.chat.id) # Сохраняем ID пользователя
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    bot.answer_callback_query(call.id)

    query_key = call.data.split('_')[3]

    if chat_id not in user_states or 'pending_search_queries' not in user_states[chat_id] or query_key not in user_states[chat_id]['pending_search_queries']:
        bot.edit_message_text(
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} Сессия истекла или запрос не найден. Пожалуйста, попробуйте снова."
            ),
            chat_id=chat_id,
            message_id=message_id,
            parse_mode='Markdown'
        )
        return
    
    query = user_states[chat_id]['pending_search_queries'].pop(query_key)

    search_message = bot.send_message(
        chat_id=chat_id,
        text=format_message(
            "Поиск",
            f"{PRIMARY_COLOR} Поиск видео на YouTube...\n\n"
            f"🔍 Запрос: *{query}*\n"
            f"⏳ Пожалуйста, подождите..."
        ),
        parse_mode='Markdown'
    )

    results = search_youtube(query)

    if not results:
        bot.edit_message_text(
            format_message(
                "Результаты поиска",
                f"{WARNING_COLOR} По вашему запросу ничего не найдено.\n\n"
                f"Попробуйте изменить запрос и повторить поиск."
            ),
            chat_id=chat_id,
            message_id=search_message.message_id,
            parse_mode='Markdown'
        )
        return

    result_text = f"{SUCCESS_COLOR} Найдено {len(results)} видео по запросу: *{query}*\n\n"

    for i, video in enumerate(results, 1):
        views_formatted = f"{video['view_count']:,}" if video['view_count'] else "Неизвестно"
        result_text += f"*{i}. {video['title']}*\n"
        result_text += f"👤 {video['uploader']}\n"
        result_text += f"⏱️ {format_duration(video['duration'])}\n"
        result_text += f"👁️ {views_formatted} просмотров\n\n"

    markup = types.InlineKeyboardMarkup()

    for i, video in enumerate(results, 1):
        markup.add(types.InlineKeyboardButton(
            text=f"{i}. {video['title'][:30]}...",
            callback_data=f"search_result_{i-1}"
        ))

    user_states[chat_id] = {
        'search_results': results,
        'message_id': search_message.message_id
    }

    bot.edit_message_text(
        format_message(
            "Результаты поиска",
            result_text
        ),
        chat_id=chat_id,
        message_id=search_message.message_id,
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('quality_'))
def handle_quality_selection(call):
    """Обработка выбора качества."""
    add_user_to_list(call.message.chat.id) # Сохраняем ID пользователя
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    bot.answer_callback_query(call.id)

    format_id = call.data.split('_')[1]

    if chat_id not in user_states:
        bot.edit_message_text(
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} Сессия истекла. Пожалуйста, отправьте ссылку на YouTube снова."
            ),
            chat_id=chat_id,
            message_id=message_id,
            parse_mode='Markdown'
        )
        return

    url = user_states[chat_id]['youtube_url']

    # Обновление сообщения
    bot.edit_message_text(
        format_message(
            "Загрузка видео",
            f"{PRIMARY_COLOR} Подготовка к загрузке...\n\n"
            f"⏳ Пожалуйста, подождите..."
        ),
        chat_id=chat_id,
        message_id=message_id,
        parse_mode='Markdown'
    )

    thread = threading.Thread(target=download_video, args=(chat_id, url, format_id, message_id))
    thread.daemon = True
    thread.start()

@bot.callback_query_handler(func=lambda call: call.data == 'admin_send_message_start')
def admin_send_message_start(call):
    """Начало процесса отправки сообщения конкретному пользователю."""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Доступ запрещен", show_alert=True)
        return
    
    bot.answer_callback_query(call.id)
    msg = bot.edit_message_text(
        format_message(
            "Отправить сообщение пользователю",
            f"{PRIMARY_COLOR} Отправьте Telegram ID пользователя, которому вы хотите отправить сообщение."
        ),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, receive_user_id_for_message)

def receive_user_id_for_message(message):
    """Получает ID пользователя и запрашивает текст сообщения."""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, format_message("Доступ запрещен", f"{ERROR_COLOR} У вас нет прав администратора."), parse_mode='Markdown')
        return

    try:
        user_id_to_send = int(message.text.strip())
        user_states[message.chat.id] = {'target_user_id': user_id_to_send}
        msg = bot.reply_to(
            message,
            format_message(
                "Отправить сообщение пользователю",
                f"{PRIMARY_COLOR} Теперь отправьте текст сообщения для пользователя с ID `{user_id_to_send}`."
            ),
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(msg, execute_send_message_to_user)
    except ValueError:
        msg = bot.reply_to(
            message,
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} Неверный формат ID пользователя. Пожалуйста, введите числовой ID."
            ),
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(msg, receive_user_id_for_message)

def execute_send_message_to_user(message):
    """Отправляет сообщение указанному пользователю."""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, format_message("Доступ запрещен", f"{ERROR_COLOR} У вас нет прав администратора."), parse_mode='Markdown')
        return

    chat_id = message.chat.id
    if chat_id not in user_states or 'target_user_id' not in user_states[chat_id]:
        bot.reply_to(
            message,
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} Сессия истекла. Пожалуйста, начните отправку сообщения заново."
            ),
            parse_mode='Markdown'
        )
        return

    target_user_id = user_states[chat_id].pop('target_user_id')
    message_text = message.text

    try:
        bot.send_message(target_user_id, message_text, parse_mode='Markdown')
        bot.reply_to(
            message,
            format_message(
                "Успех",
                f"{SUCCESS_COLOR} Сообщение успешно отправлено пользователю `{target_user_id}`."
            ),
            parse_mode='Markdown'
        )
    except telebot.apihelper.ApiTelegramException as e:
        error_msg = f"Ошибка при отправке сообщения пользователю `{target_user_id}`: {e}"
        logger.error(error_msg)
        bot.reply_to(
            message,
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} {error_msg}\n\n"
                f"Возможно, пользователь заблокировал бота или ID неверен."
            ),
            parse_mode='Markdown'
        )
    except Exception as e:
        error_msg = f"Неизвестная ошибка при отправке сообщения пользователю `{target_user_id}`: {e}"
        logger.error(error_msg)
        bot.reply_to(
            message,
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} {error_msg}"
            ),
            parse_mode='Markdown'
        )

@bot.callback_query_handler(func=lambda call: call.data == 'admin_get_logs')
def admin_get_logs(call):
    """Отправляет последние логи бота администратору."""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Доступ запрещен", show_alert=True)
        return
    
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    try:
        if not os.path.exists(LOG_FILE):
            bot.edit_message_text(
                format_message(
                    "Логи бота",
                    f"{WARNING_COLOR} Файл логов `{LOG_FILE}` не найден."
                ),
                chat_id=chat_id,
                message_id=message_id,
                parse_mode='Markdown'
            )
            return

        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Отправляем последние 100 строк логов
        last_100_lines = "".join(lines[-100:]) 
        
        if not last_100_lines.strip():
            log_content = f"{INFO_COLOR} Файл логов пуст или содержит только пробелы."
        else:
            log_content = f"\`\`\`\n{last_100_lines}\n\`\`\`" # Форматируем как блок кода

        bot.edit_message_text(
            format_message(
                "Логи бота",
                f"{INFO_COLOR} Последние 100 строк логов:\n\n{log_content}"
            ),
            chat_id=chat_id,
            message_id=message_id,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Ошибка при получении логов: {e}")
        bot.edit_message_text(
            format_message(
                "Ошибка",
                f"{ERROR_COLOR} Произошла ошибка при попытке получить логи: {e}"
            ),
            chat_id=chat_id,
            message_id=message_id,
            parse_mode='Markdown'
        )

def main():
    """Запуск бота."""
    print(f"🤖 Запуск {BOT_NAME}...")

    bot.threaded = True
    bot.num_threads = 8

    bot.set_my_commands([
        telebot.types.BotCommand("start", "Запустить бота"),
        telebot.types.BotCommand("mp4", "Скачать видео в MP4"),
        telebot.types.BotCommand("search", "Поиск видео на YouTube"),
        telebot.types.BotCommand("help", "Показать справку"),
        telebot.types.BotCommand("admin", "Админ-панель") # Добавляем команду /admin
    ])

    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logger.error(f"Ошибка в основном цикле бота: {str(e)}")
            logger.error(traceback.format_exc())
            time.sleep(10)

if __name__ == "__main__":
    import time
    main()
