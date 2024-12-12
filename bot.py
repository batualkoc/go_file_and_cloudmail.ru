import os
import shutil
import sys
from os import chdir, getcwd, getenv, listdir, mkdir, path, rmdir
from sys import exit, stdout, stderr
from typing import Any, NoReturn, TextIO
from requests import get, post, Session
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from platform import system
from hashlib import sha256
from shutil import move
from time import perf_counter

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

# Telegram Bot Token ve Hedef Chat ID'yi buraya girin
TELEGRAM_BOT_TOKEN = 'YOUR_API_KEY'
TARGET_CHAT_ID = 'YOUR_CHAT_ID'

NEW_LINE: str = "\n" if system() != "Windows" else "\r\n"

def _print(msg: str, error: bool = False) -> None:
    """Konsola mesaj yazdırma fonksiyonu"""
    output: TextIO = stderr if error else stdout
    output.write(msg)
    output.flush()

def die(msg: str) -> NoReturn:
    """Hata mesajı yazdırıp çıkış yapma fonksiyonu"""
    _print(f"{msg}{NEW_LINE}", True)
    exit(-1)

def detect_service(url: str) -> str:
    """URL'nin hangi servise ait olduğunu tespit eden fonksiyon"""
    if "gofile.io" in url.lower():
        return "gofile"
    elif "cloud.mail.ru" in url.lower():
        return "cloudmail"
    else:
        return "unknown"

class GoFileDownloader:
    def __init__(self, url: str, password: str | None = None, max_workers: int = 5, bot=None, chat_id=None) -> None:
        root_dir: str | None = getenv("GF_DOWNLOADDIR")

        if root_dir and path.exists(root_dir):
            chdir(root_dir)

        self._lock: Lock = Lock()
        self._max_workers: int = max_workers
        token: str | None = getenv("GF_TOKEN")
        self._message: str = " "
        self._content_dir: str | None = None

        # Telegram bot ve chat id
        self.bot = bot
        self.chat_id = chat_id

        self._recursive_files_index: int = 0
        self._files_info: dict[str, dict[str, str]] = {}

        self._root_dir: str = root_dir if root_dir else getcwd()
        self._token: str = token if token else self._get_token()

        self._parse_url_or_file(url, password)
        
        # İndirme tamamlandıktan sonra dosyaları Telegram'a gönder
        self._send_files_to_telegram()

    def _send_files_to_telegram(self):
        """İndirilen dosyaları Telegram'a gönderme fonksiyonu"""
        if not self._content_dir or not self.bot or not self.chat_id:
            return

        for root, dirs, files in os.walk(self._content_dir):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'rb') as f:
                        # Dosyayı Telegram'a gönder
                        self.bot.send_document(self.chat_id, f)
                    
                    # Dosyayı gönderdikten sonra sil
                    os.remove(file_path)
                except Exception as e:
                    self.bot.send_message(self.chat_id, f"Dosya gönderme hatası: {e}")

        # İçerik dizinini sil
        if os.path.exists(self._content_dir):
            shutil.rmtree(self._content_dir)

    def _get_token(self) -> str:
        """GoFile token alma fonksiyonu"""
        user_agent: str | None = getenv("GF_USERAGENT")
        headers: dict[str, str] = {
            "User-Agent": user_agent if user_agent else "Mozilla/5.0",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "*/*",
            "Connection": "keep-alive",
        }

        create_account_response: dict[Any, Any] = post("https://api.gofile.io/accounts", headers=headers).json()

        if create_account_response["status"] != "ok":
            die("Account creation failed!")

        return create_account_response["data"]["token"]

    def _create_dir(self, dirname: str) -> None:
        """Dizin oluşturma fonksiyonu"""
        current_dir: str = getcwd()
        filepath: str = path.join(current_dir, dirname)

        try:
            mkdir(path.join(filepath))
        except FileExistsError:
            pass

    def _download_content(self, file_info: dict[str, str], chunk_size: int = 16384) -> None:
        """Dosya indirme fonksiyonu"""
        filepath: str = path.join(file_info["path"], file_info["filename"])
        if path.exists(filepath):
            if path.getsize(filepath) > 0:
                _print(f"{filepath} zaten var, atlanıyor.{NEW_LINE}")
                return

        tmp_file: str =  f"{filepath}.part"
        url: str = file_info["link"]
        user_agent: str | None = getenv("GF_USERAGENT")

        headers: dict[str, str] = {
            "Cookie": f"accountToken={self._token}",
            "Accept-Encoding": "gzip, deflate, br",
            "User-Agent": user_agent if user_agent else "Mozilla/5.0",
            "Accept": "*/*",
            "Referer": f"{url}{('/' if not url.endswith('/') else '')}",
            "Origin": url,
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache"
        }

        part_size: int = 0
        if path.isfile(tmp_file):
            part_size = int(path.getsize(tmp_file))
            headers["Range"] = f"bytes={part_size}-"

        has_size: str | None = None
        status_code: int | None = None

        try:
            with get(url, headers=headers, stream=True, timeout=(9, 27)) as response_handler:
                status_code = response_handler.status_code

                if ((response_handler.status_code in (403, 404, 405, 500)) or
                    (part_size == 0 and response_handler.status_code != 200) or
                    (part_size > 0 and response_handler.status_code != 206)):
                    _print(
                        f"{url} adresinden dosya indirilemedi."
                        f"{NEW_LINE}"
                        f"Durum kodu: {status_code}"
                        f"{NEW_LINE}"
                    )
                    return

                content_lenth: str | None = response_handler.headers.get("Content-Length")
                has_size = content_lenth if part_size == 0 \
                    else content_lenth.split("/")[-1] if content_lenth else None

                if not has_size:
                    _print(
                        f"{url} adresinden dosya boyutu alınamadı."
                        f"{NEW_LINE}"
                        f"Durum kodu: {status_code}"
                        f"{NEW_LINE}"
                    )
                    return

                with open(tmp_file, "ab") as handler:
                    total_size: float = float(has_size)

                    start_time: float = perf_counter()
                    for i, chunk in enumerate(response_handler.iter_content(chunk_size=chunk_size)):
                        progress: float = (part_size + (i * len(chunk))) / total_size * 100

                        handler.write(chunk)

                        rate: float = (i * len(chunk)) / (perf_counter()-start_time)
                        unit: str = "B/s"
                        if rate < (1024):
                            unit = "B/s"
                        elif rate < (1024*1024):
                            rate /= 1024
                            unit = "KB/s"
                        elif rate < (1024*1024*1024):
                            rate /= (1024 * 1024)
                            unit = "MB/s"
                        elif rate < (1024*1024*1024*1024):
                            rate /= (1024 * 1024 * 1024)
                            unit = "GB/s"

                        with self._lock:
                            _print(f"\r{' ' * len(self._message)}")

                            self._message = f"\r{file_info['filename']} indiriliyor: {part_size + i * len(chunk)}" \
                            f" / {has_size} {round(progress, 1)}% {round(rate, 1)}{unit}"

                            _print(self._message)
        finally:
            with self._lock:
                if has_size and path.getsize(tmp_file) == int(has_size):
                    _print(f"\r{' ' * len(self._message)}")
                    _print(f"\r{file_info['filename']} indirildi: "
                        f"{path.getsize(tmp_file)} / {has_size} Tamamlandı!"
                        f"{NEW_LINE}"
                    )
                    move(tmp_file, filepath)

    def _threaded_downloads(self) -> None:
        """Paralel indirme fonksiyonu"""
        if not self._content_dir:
            _print(f"İçerik dizini oluşturulamadı, hiçbir şey yapılmadı.{NEW_LINE}")
            return

        chdir(self._content_dir)

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            for item in self._files_info.values():
                executor.submit(self._download_content, item)

        chdir(self._root_dir)

    def _parse_links_recursively(
        self,
        content_id: str,
        password: str | None = None
    ) -> None:
        """Linkleri recursive olarak ayrıştırma fonksiyonu"""
        url: str = f"https://api.gofile.io/contents/{content_id}?wt=4fd6sg89d7s6&cache=true"

        if password:
            url = f"{url}&password={password}"

        user_agent: str | None = getenv("GF_USERAGENT")

        headers: dict[str, str] = {
            "User-Agent": user_agent if user_agent else "Mozilla/5.0",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "*/*",
            "Connection": "keep-alive",
            "Authorization": f"Bearer {self._token}",
        }

        response: dict[Any, Any] = get(url, headers=headers).json()

        if response["status"] != "ok":
            _print(f"{url} adresinden yanıt alınamadı.{NEW_LINE}")
            return

        data: dict[Any, Any] = response["data"]

        if "password" in data and "passwordStatus" in data and data["passwordStatus"] != "passwordOk":
            _print(f"Parola korumalı link. Lütfen parolayı girin.{NEW_LINE}")
            return

        if data["type"] == "folder":
            if not self._content_dir and data["name"] != content_id:
                self._content_dir = path.join(self._root_dir, content_id)
                self._create_dir(self._content_dir)
                chdir(self._content_dir)
            elif not self._content_dir and data["name"] == content_id:
                self._content_dir = path.join(self._root_dir, content_id)
                self._create_dir(self._content_dir)

            self._create_dir(data["name"])
            chdir(data["name"])

            for child_id in data["children"]:
                child: dict[Any, Any] = data["children"][child_id]

                if child["type"] == "folder":
                    self._parse_links_recursively(child["id"], password)
                else:
                    self._recursive_files_index += 1

                    self._files_info[str(self._recursive_files_index)] = {
                        "path": getcwd(),
                        "filename": child["name"],
                        "link": child["link"]
                    }

            chdir(path.pardir)
        else:
            self._recursive_files_index += 1

            self._files_info[str(self._recursive_files_index)] = {
                "path": getcwd(),
                "filename": data["name"],
                "link": data["link"]
            }

    def _parse_url_or_file(self, url_or_file: str, _password: str | None = None) -> None:
        """URL veya dosyayı ayrıştırma fonksiyonu"""
        if not (path.exists(url_or_file) and path.isfile(url_or_file)):
            self._download(url_or_file, _password)
            return

        with open(url_or_file, "r") as f:
            lines: list[str] = f.readlines()

        for line in lines:
            line_splitted: list[str] = line.split(" ")
            url: str = line_splitted[0].strip()
            password: str | None = _password if _password else line_splitted[1].strip() \
                if len(line_splitted) > 1 else _password

            self._download(url, password)

    def _download(self, url: str, password: str | None = None) -> None:
        """İndirme fonksiyonu"""
        try:
            if not url.split("/")[-2] == "d":
                _print(f"URL muhtemelen geçerli bir ID içermiyor: {url}.{NEW_LINE}")
                return

            content_id: str = url.split("/")[-1]
        except IndexError:
            _print(f"{url} geçerli bir URL gibi görünmüyor.{NEW_LINE}")
            return

        _password: str | None = sha256(password.encode()).hexdigest() if password else password

        self._parse_links_recursively(content_id, _password)

        if not self._content_dir:
            _print(f"{url} için içerik dizini oluşturulamadı, hiçbir şey yapılmadı.{NEW_LINE}")
            return

        if not listdir(self._content_dir) and not self._files_info:
            _print(f"{url} için boş dizin, hiçbir şey yapılmadı.{NEW_LINE}")
            rmdir(self._content_dir)
            return

        self._threaded_downloads()

        os.system("clear")


class CloudMailDownloader:
    def __init__(self, url: str, max_workers: int = 5, bot=None, chat_id=None) -> None:
        self._lock = Lock()
        self._max_workers = max_workers
        self._message = " "
        self._content_dir = None
        self.bot = bot
        self.chat_id = chat_id
        self.session = Session()
        self._root_dir = getenv("CM_DOWNLOADDIR") or getcwd()

        # API endpoints
        self.base_api_url = "https://cloud.mail.ru/api/v2"
        self.page_id = None
        self.base_url = None

        self._parse_url(url)
        self._send_files_to_telegram()

    def _get_page_id(self, url: str) -> str:
        """Sayfadan page_id'yi al"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; Firefox/3.6; Linux)',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
            }

            response = self.session.get(url, headers=headers)
            if response.status_code != 200:
                raise Exception("Sayfa yüklenemedi")

            # page_id'yi bul
            import re
            match = re.search(r'pageId[\'"]?\s*:\s*[\'"]([^\'"]+)[\'"]', response.text)
            if not match:
                raise Exception("page_id bulunamadı")

            return match.group(1)

        except Exception as e:
            _print(f"Page ID alma hatası: {str(e)}{NEW_LINE}")
            return None

    def _get_base_url(self, page_id: str) -> str:
        """Dispatcher API'den base URL al"""
        try:
            url = f"{self.base_api_url}/dispatcher?x-page-id={page_id}"
            response = self.session.get(url)
            if response.status_code != 200:
                raise Exception("Dispatcher API yanıt vermedi")

            data = response.json()
            if "body" in data and "weblink_get" in data["body"] and len(data["body"]["weblink_get"]) > 0:
                return data["body"]["weblink_get"][0]["url"]

            raise Exception("Base URL bulunamadı")

        except Exception as e:
            _print(f"Base URL alma hatası: {str(e)}{NEW_LINE}")
            return None

    def _get_file_info(self, url: str) -> list:
        """Cloud Mail.ru'dan dosya bilgilerini al"""
        try:
            # URL'den weblink ID'sini çıkar
            import re
            match = re.search(r'/public/([^/]+/[^/]+)', url)
            if not match:
                raise Exception("Geçersiz Cloud Mail.ru linki")

            weblink = match.group(1)

            # Önce page_id al
            self.page_id = self._get_page_id(url)
            if not self.page_id:
                raise Exception("Page ID alınamadı")

            # Base URL al
            self.base_url = self._get_base_url(self.page_id)
            if not self.base_url:
                raise Exception("Base URL alınamadı")

            # Dosya bilgilerini al
            folder_url = f"{self.base_api_url}/folder?weblink={weblink}&x-page-id={self.page_id}"
            response = self.session.get(folder_url)

            if response.status_code != 200:
                raise Exception("Dosya bilgileri alınamadı")

            data = response.json()
            if "body" not in data or "list" not in data["body"]:
                raise Exception("Dosya listesi bulunamadı")

            files = []
            for item in data["body"]["list"]:
                if item["type"] == "file":
                    download_url = f"{self.base_url}/{weblink}"
                    if "name" in item:
                        download_url = f"{self.base_url}/{weblink}/{item['name']}"

                    files.append({
                        'name': item['name'],
                        'size': item['size'],
                        'link': download_url
                    })

            return files

        except Exception as e:
            _print(f"Dosya bilgileri alma hatası: {str(e)}{NEW_LINE}")
            return None

    def _download_file(self, file_info: dict) -> None:
        """Dosya indirme fonksiyonu"""
        if not file_info:
            return

        filename = file_info['name']
        download_url = file_info['link']
        file_size = file_info['size']

        # İndirme dizinini oluştur
        if not self._content_dir:
            self._content_dir = path.join(self._root_dir, filename)
            if not path.exists(self._content_dir):
                mkdir(self._content_dir)

        filepath = path.join(self._content_dir, filename)
        tmp_file = f"{filepath}.part"

        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; Firefox/3.6; Linux)',
            'Accept': '*/*',
            'Referer': 'https://cloud.mail.ru/',
        }

        try:
            with self.session.get(download_url, headers=headers, stream=True) as response:
                if response.status_code != 200:
                    raise Exception(f"İndirme başlatılamadı: HTTP {response.status_code}")

                total_size = int(response.headers.get('content-length', file_size))
                with open(tmp_file, 'wb') as f:
                    downloaded = 0
                    start_time = perf_counter()

                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            progress = (downloaded / total_size) * 100 if total_size else 0
                            speed = downloaded / (perf_counter() - start_time)

                            with self._lock:
                                _print(f"\r{' ' * len(self._message)}")
                                self._message = f"\r{filename} indiriliyor: {downloaded}/{total_size} " \
                                                f"{round(progress, 1)}% {self._format_speed(speed)}"
                                _print(self._message)

            # İndirme tamamlandığında dosyayı yeniden adlandır
            os.rename(tmp_file, filepath)
            _print(f"\n{filename} başarıyla indirildi!{NEW_LINE}")

        except Exception as e:
            _print(f"Dosya indirme hatası: {str(e)}{NEW_LINE}")
            if path.exists(tmp_file):
                os.remove(tmp_file)

    def _format_speed(self, bytes_per_second: float) -> str:
        """İndirme hızını formatla"""
        for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
            if bytes_per_second < 1024:
                return f"{bytes_per_second:.1f} {unit}"
            bytes_per_second /= 1024
        return f"{bytes_per_second:.1f} TB/s"

    def _send_files_to_telegram(self):
        """İndirilen dosyaları Telegram'a gönderme fonksiyonu"""
        if not self._content_dir or not self.bot or not self.chat_id:
            return

        try:
            for root, dirs, files in os.walk(self._content_dir):
                for file in files:
                    file_path = path.join(root, file)
                    try:
                        with open(file_path, 'rb') as f:
                            self.bot.send_document(self.chat_id, f)
                        os.remove(file_path)
                    except Exception as e:
                        _print(f"Dosya gönderme hatası: {str(e)}{NEW_LINE}")

            if path.exists(self._content_dir):
                shutil.rmtree(self._content_dir)

        except Exception as e:
            _print(f"Telegram'a gönderme hatası: {str(e)}{NEW_LINE}")

    def _parse_url(self, url: str) -> None:
        """URL'yi ayrıştır ve indirme işlemini başlat"""
        try:
            files = self._get_file_info(url)
            if files:
                for file in files:
                    self._download_file(file)
            else:
                _print(f"Dosya bilgileri alınamadı: {url}{NEW_LINE}")
        except Exception as e:
            _print(f"URL ayrıştırma hatası: {str(e)}{NEW_LINE}")

        os.system("clear")

class MultiServiceBot:
    def __init__(self, token, target_chat_id):
        self.updater = Updater(token=token, use_context=True)
        self.dispatcher = self.updater.dispatcher
        self.target_chat_id = target_chat_id

        # Komutları ekle
        self.dispatcher.add_handler(CommandHandler('start', self.start_command))
        self.dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, self.process_url))

    def start_command(self, update, context):
        welcome_message = (
            "Çoklu İndirici Bot'a hoş geldiniz! 🤖\n\n"
            "Bu bot aşağıdaki servislerden dosya indirmenize yardımcı olur:\n"
            "- GoFile.io\n"
            "- Cloud Mail.ru\n\n"
            "Kullanım:\n"
            "1. Desteklenen servislerden bir link gönderin\n"
            "2. GoFile şifreli linkler için: <link> <şifre>\n"
            "Bot dosyayı otomatik olarak indirecek ve size gönderecektir."
        )
        update.message.reply_text(welcome_message)

    def process_url(self, update, context):
        message_parts = update.message.text.strip().split()
        url = message_parts[0]
        password = message_parts[1] if len(message_parts) > 1 else None

        try:
            status_message = update.message.reply_text("Link analiz ediliyor... 🔍")
            
            service = detect_service(url)
            
            if service == "gofile":
                downloader = GoFileDownloader(
                    url=url,
                    password=password,
                    bot=update.message.bot,
                    chat_id=self.target_chat_id
                )
                status_message.edit_text("GoFile dosyası indiriliyor... 📥")
                
            elif service == "cloudmail":
                downloader = CloudMailDownloader(
                    url=url,
                    bot=update.message.bot,
                    chat_id=self.target_chat_id
                )
                status_message.edit_text("Cloud Mail.ru dosyası indiriliyor... 📥")
                
            else:
                status_message.edit_text("❌ Desteklenmeyen servis! Sadece GoFile ve Cloud Mail.ru linkleri desteklenmektedir.")
                return

            status_message.edit_text("✅ İndirme tamamlandı!")
            
        except Exception as e:
            error_message = f"Hata oluştu: {str(e)}"
            update.message.reply_text(error_message)

    def start_bot(self):
        print("Bot başlatıldı... Durdurmak için Ctrl+C")
        self.updater.start_polling()
        self.updater.idle()

def main():
    try:
        bot = MultiServiceBot(TELEGRAM_BOT_TOKEN, TARGET_CHAT_ID)
        bot.start_bot()
    except Exception as e:
        print(f"Bot başlatılamadı: {e}")

if __name__ == "__main__":
    main()
