# YouTube Downloader Telegram Bot

A powerful Telegram bot for downloading YouTube videos in various formats and resolutions.

## 🎥 Features

- **Download Videos** - MP4, MP3, and other formats
- **Multiple Resolutions** - Choose from 144p to 1080p
- **Search YouTube** - Find videos directly in Telegram
- **Admin Panel** - Manage users and send messages
- **Logging** - Track all bot activity
- **Fast & Reliable** - Uses yt-dlp for best quality

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- Telegram Bot Token (from @BotFather)

### Installation

1. Clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/youtube-downloader-bot.git
cd youtube-downloader-bot
```

2. Install dependencies
```bash
pip install -r requirements.txt
```

3. Set up environment variables
```bash
export TELEGRAM_BOT_TOKEN="your_bot_token_here"
```

4. Run the bot
```bash
python main.py
```

## 📋 Available Commands

- `/start` - Start the bot
- `/mp4` - Download video as MP4
- `/search` - Search for videos on YouTube
- `/help` - Show help message
- `/admin` - Access admin panel (admins only)

## 🎛️ Admin Panel

Admins can:
- View user statistics
- Send messages to users
- View bot logs
- Manage settings

## ⚙️ Configuration

Edit these settings in `main.py`:
```python
TELEGRAM_BOT_TOKEN = "your_token"  # Your Telegram bot token
ADMIN_IDS = [123456789]            # Telegram IDs of admins
MAX_TELEGRAM_FILE_SIZE = 50 * 1024 * 1024  # Max file size
DESIRED_HEIGHTS = [144, 240, 360, 480, 720, 1080]  # Available resolutions
```

## 📁 Project Structure
```
├── main.py              # Main bot file
├── requirements.txt     # Dependencies
├── README.md           # This file
└── bot_activity.log    # Activity logs (auto-generated)
```

## 🔐 Security

⚠️ **Important Security Note:**
- Never share your bot token
- Never commit `.env` files with secrets
- Use environment variables for sensitive data

## 🐛 Troubleshooting

### "Token not found"
- Set `TELEGRAM_BOT_TOKEN` environment variable

### "yt-dlp error"
- Update: `pip install --upgrade yt-dlp`

### "File too large"
- Telegram has 50MB file size limit
- Try downloading in lower resolution

## 👤 Author

Created with ❤️ for YouTube lovers

## 🤝 Contributing

Contributions are welcome! Feel free to submit issues and pull requests.

---

**Made with Python and ❤️**
```

---

#### **Файл 4: .gitignore**

**Имя:** `.gitignore`

**Содержание:**
```
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg
.env
.venv
venv/
ENV/
env/
.idea/
.vscode/
*.swp
*.swo
bot_activity.log
users.json
*.mp4
*.mp3
tmp/
temp/
downloads/
```

---

#### **Файл 5: .env.example**

**Имя:** `.env.example`

**Содержание:**
```
# Telegram Bot Settings
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Admin Settings
ADMIN_IDS=123456789,987654321

# Logging
LOG_FILE=bot_activity.log
LOG_LEVEL=INFO
