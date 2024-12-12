# Gofile and Cloud Mail.ru Downloader

A Telegram bot that automatically downloads files from Gofile.io and Cloud Mail.ru, then forwards them to a specified Telegram chat.

## ⭐ Features

- Supports multiple file hosting services:
  - ✅ Gofile.io
    - Handles password-protected files
    - Multi-threaded downloading
    - Supports batch downloads
  - ✅ Cloud Mail.ru
    - Single and multiple file downloads
    - Automatic file detection
- 🤖 Telegram Integration
  - Automatic forwarding to specified chat
  - Progress updates
  - Simple command interface
- 🚀 Performance
  - Concurrent downloads
  - Resume interrupted downloads
  - Progress tracking

## 📋 Requirements

- Python 3.7+
- python-telegram-bot
- requests
- Other dependencies listed in requirements.txt

## ⚙️ Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/gofile-and-cloudmailru-downloader.git
cd gofile-and-cloudmailru-downloader
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Configure the bot:
```python
# Edit these values in bot.py
TELEGRAM_BOT_TOKEN = 'your_bot_token_here'
TARGET_CHAT_ID = 'your_chat_id_here'
```

## 🎯 Usage

1. Start the bot:
```bash
python bot.py
```

2. Send links to the bot:
```
# Gofile link
https://gofile.io/d/example

# Password-protected Gofile link
https://gofile.io/d/example password123

# Cloud Mail.ru link
https://cloud.mail.ru/public/example
```

## 🔧 Environment Variables

Optional configuration through environment variables:
```bash
# Gofile settings
GF_DOWNLOADDIR="/custom/download/path"
GF_TOKEN="custom_gofile_token"
GF_USERAGENT="custom_user_agent"

# Cloud Mail.ru settings
CM_DOWNLOADDIR="/custom/download/path"
```

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

- This tool is for educational purposes only
- Be sure to comply with the terms of service of both Gofile.io and Cloud Mail.ru
- The developers are not responsible for any misuse of this tool

## 🔍 Common Issues

### Gofile Issues
- Rate limiting: Use custom tokens
- Download failures: Check file availability
- Password issues: Verify password format

### Cloud Mail.ru Issues
- Access denied: Check link validity
- Slow downloads: Server load dependent
- Failed uploads: Check Telegram file size limits

## 📮 Contact

Your Name - [@yourusername](https://github.com/yourusername)

Project Link: [https://github.com/yourusername/gofile-and-cloudmailru-downloader](https://github.com/yourusername/gofile-and-cloudmailru-downloader)

