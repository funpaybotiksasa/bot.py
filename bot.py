import asyncio
import re
import time
import random
import json
import os
import aiohttp
import sys
import threading
import hashlib
from playwright.async_api import async_playwright
from datetime import datetime, timedelta
from flask import Flask, request, Response
import sqlite3
from contextlib import contextmanager

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
def get_env_var(name, required=True):
    value = os.environ.get(name)
    if required and value is None:
        raise ValueError(f"❌ Переменная {name} не установлена!")
    return value

try:
    CONFIG = {
        "FUNPAY_GOLDEN_KEY": get_env_var("FUNPAY_GOLDEN_KEY"),
        "TELEGRAM_TOKEN": get_env_var("TELEGRAM_TOKEN"),
        "TELEGRAM_CHAT_IDS": ["1973759066"],
        "FIRST_MESSAGE": """Здравствуйте, {buyer_name}!

⏰ Время работы продавца с 5:00 до 22:00 по МСК.
📌 Обычно я отвечаю быстро, но бывает что время ответа может быть больше. Приношу извинения!
🤝 Аккаунты в Blox Fruit выдаются автоматически, продавца нужно ждать только для получения кода!
🎁 Фрукты в Blox Fruit выдаются в порядке живой очереди, ты можешь пока что оплатить, но скорее всего придется немного подождать.

📌 КОМАНДЫ:
• Если вы купили ФРУКТ - напишите: !фрукт
• Если нужен КОД с почты - напишите: !код

После команды я уведомлю продавца!""",
        "PAYMENT_CONFIRMED_MESSAGE": """✅ Спасибо за покупку!

Благодарим за доверие! 🙏

Пожалуйста, оставьте отзыв о нашей работе ❤️
Это поможет нам стать лучше!

Хорошего дня! 😊""",
        "PAYMENT_PATTERNS": [
            r"подтвердил успешное выполнение заказа",
            r"подтвердил.*выполнение заказа",
            r"отправил деньги продавцу",
            r"заказ #[A-Z0-9]+",
            r"Покупатель.*подтвердил"
        ],
        "FRUIT_COMMAND": "!фрукт",
        "CODE_COMMAND": "!код",
        "CHECK_INTERVAL": 15,
        "DEBUG": False
    }
except ValueError as e:
    print(f"❌ {e}")
    sys.exit(1)

# ==========================================
# 2. TELEGRAM
# ==========================================
async def send_telegram_async(message):
    if not CONFIG["TELEGRAM_TOKEN"] or not CONFIG["TELEGRAM_CHAT_IDS"]:
        return False
    sent_count = 0
    async with aiohttp.ClientSession() as session:
        for chat_id in CONFIG["TELEGRAM_CHAT_IDS"]:
            chat_id = str(chat_id).strip()
            if not chat_id:
                continue
            try:
                url = f"https://api.telegram.org/bot{CONFIG['TELEGRAM_TOKEN']}/sendMessage"
                data = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
                async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        sent_count += 1
                        print(f"✅ Telegram: {chat_id}")
                    else:
                        text = await response.text()
                        print(f"❌ Ошибка {chat_id}: {text}")
            except Exception as e:
                print(f"❌ Ошибка {chat_id}: {e}")
    return sent_count > 0

def send_telegram(message):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(send_telegram_async(message))
            return True
        else:
            return loop.run_until_complete(send_telegram_async(message))
    except RuntimeError:
        return asyncio.run(send_telegram_async(message))

async def send_telegram_document_async(file_path, caption=""):
    if not CONFIG["TELEGRAM_TOKEN"] or not CONFIG["TELEGRAM_CHAT_IDS"]:
        return False
    if not os.path.exists(file_path):
        print(f"⚠️ Файл не найден: {file_path}")
        return False
    sent_count = 0
    async with aiohttp.ClientSession() as session:
        for chat_id in CONFIG["TELEGRAM_CHAT_IDS"]:
            chat_id = str(chat_id).strip()
            if not chat_id:
                continue
            try:
                url = f"https://api.telegram.org/bot{CONFIG['TELEGRAM_TOKEN']}/sendDocument"
                with open(file_path, "rb") as doc_file:
                    form = aiohttp.FormData()
                    form.add_field("chat_id", chat_id)
                    form.add_field("caption", caption[:1024])
                    form.add_field("document", doc_file, filename=os.path.basename(file_path))
                    async with session.post(url, data=form, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status == 200:
                            sent_count += 1
                            print(f"✅ Документ отправлен: {chat_id}")
                        else:
                            text = await response.text()
                            print(f"❌ Ошибка документа {chat_id}: {text}")
            except Exception as e:
                print(f"❌ Ошибка документа {chat_id}: {e}")
    return sent_count > 0

async def send_telegram_photo_async(photo_path, caption=""):
    if not CONFIG["TELEGRAM_TOKEN"] or not CONFIG["TELEGRAM_CHAT_IDS"]:
        return False
    if not os.path.exists(photo_path):
        print(f"⚠️ Файл не найден: {photo_path}")
        return False
    sent_count = 0
    async with aiohttp.ClientSession() as session:
        for chat_id in CONFIG["TELEGRAM_CHAT_IDS"]:
            chat_id = str(chat_id).strip()
            if not chat_id:
                continue
            try:
                url = f"https://api.telegram.org/bot{CONFIG['TELEGRAM_TOKEN']}/sendPhoto"
                with open(photo_path, "rb") as photo_file:
                    form = aiohttp.FormData()
                    form.add_field("chat_id", chat_id)
                    form.add_field("caption", caption[:1024])
                    form.add_field("photo", photo_file, filename="debug.png", content_type="image/png")
                    async with session.post(url, data=form, timeout=aiohttp.ClientTimeout(total=20)) as response:
                        if response.status == 200:
                            sent_count += 1
                            print(f"✅ Скриншот отправлен: {chat_id}")
                        else:
                            text = await response.text()
                            print(f"❌ Ошибка фото {chat_id}: {text}")
            except Exception as e:
                print(f"❌ Ошибка фото {chat_id}: {e}")
    return sent_count > 0

# ==========================================
# 3. БАЗА ДАННЫХ
# ==========================================
class ClientDatabase:
    def __init__(self):
        self.db_file = "clients.db"
        self._init_db()
    
    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    name TEXT PRIMARY KEY,
                    chat_url TEXT,
                    last_message_id TEXT,
                    first_message_sent INTEGER DEFAULT 0,
                    first_message_time TEXT,
                    payment_confirmed INTEGER DEFAULT 0,
                    thank_you_sent INTEGER DEFAULT 0,
                    fruit_notified INTEGER DEFAULT 0,
                    code_notified INTEGER DEFAULT 0,
                    date TEXT
                )
            """)
            conn.commit()
    
    def add_client(self, client_name, chat_url):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO clients (name, chat_url, date) VALUES (?, ?, ?)",
                          (client_name, chat_url, datetime.now().isoformat()))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_last_message_id(self, client_name):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_message_id FROM clients WHERE name = ?", (client_name,))
            row = cursor.fetchone()
            return row["last_message_id"] if row else None
    
    def set_last_message_id(self, client_name, msg_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE clients SET last_message_id = ? WHERE name = ?", (msg_id, client_name))
            conn.commit()
            return cursor.rowcount > 0
    
    def _get_value(self, client_name, field):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {field} FROM clients WHERE name = ?", (client_name,))
            row = cursor.fetchone()
            return bool(row[0]) if row else False
    
    def _set_value(self, client_name, field, value):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE clients SET {field} = ? WHERE name = ?", (1 if value else 0, client_name))
            conn.commit()
            return cursor.rowcount > 0
    
    def mark_first_message_sent(self, client_name):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE clients
                SET first_message_sent = 1,
                    first_message_time = ?
                WHERE name = ?
            """, (datetime.now().isoformat(), client_name))
            conn.commit()
            return cursor.rowcount > 0
    
    def is_first_message_sent(self, client_name):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT first_message_sent,
                       first_message_time
                FROM clients
                WHERE name = ?
            """, (client_name,))
            row = cursor.fetchone()
            
            if not row:
                return False
            
            sent = bool(row["first_message_sent"])
            msg_time = row["first_message_time"]
            
            if not sent:
                return False
            
            if msg_time:
                try:
                    msg_time = datetime.fromisoformat(msg_time)
                    if datetime.now() - msg_time > timedelta(hours=2):
                        cursor.execute("""
                            UPDATE clients
                            SET first_message_sent = 0,
                                first_message_time = NULL
                            WHERE name = ?
                        """, (client_name,))
                        conn.commit()
                        return False
                except:
                    pass
            
            return True
    
    def mark_payment_confirmed(self, client_name):
        return self._set_value(client_name, "payment_confirmed", True)
    def mark_thank_you_sent(self, client_name):
        return self._set_value(client_name, "thank_you_sent", True)
    def mark_fruit_notified(self, client_name):
        return self._set_value(client_name, "fruit_notified", True)
    def mark_code_notified(self, client_name):
        return self._set_value(client_name, "code_notified", True)
    def is_thank_you_sent(self, client_name):
        return self._get_value(client_name, "thank_you_sent")
    def is_fruit_notified(self, client_name):
        return self._get_value(client_name, "fruit_notified")
    def is_code_notified(self, client_name):
        return self._get_value(client_name, "code_notified")

# ==========================================
# 4. ОСНОВНОЙ БОТ
# ==========================================
class FunPayBot:
    def __init__(self, config):
        print("🔵 FunPayBot.__init__()")
        self.config = config
        self.browser = None
        self.page = None
        self.db = ClientDatabase()
        self.running = True
        self.playwright = None
        self.debug_requested = False
        self.own_username = None
        self.first_run = True
    
    async def start(self):
        print("🔵 START()")
        print("🔄 Запуск Playwright...")
        self.playwright = await async_playwright().start()
        print("✅ Playwright запущен")
        
        print("🔄 Запуск Chromium...")
        try:
            self.browser = await self.playwright.chromium.launch(
                headless=not self.config["DEBUG"],
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-blink-features=AutomationControlled'
                ]
            )
            print("✅ Chromium запущен")
        except Exception as e:
            print(f"❌ Chromium error: {repr(e)}")
            raise
        
        self.page = await self.browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="ru-RU"
        )
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        print("🔑 Подставляю сессию (golden_key)...")
        await self.page.context.add_cookies([
            {
                "name": "golden_key",
                "value": self.config["FUNPAY_GOLDEN_KEY"],
                "domain": "funpay.com",
                "path": "/",
            }
        ])
        
        print("🔄 Открываю FunPay...")
        await self.page.goto("https://funpay.com/", timeout=60000)
        await self.page.wait_for_load_state("networkidle")
        print(f"📍 URL: {self.page.url}")
        
        await self._accept_cookies()
        
        print("🔄 Проверка входа по сессии...")
        await self.login()
        
        print("🔄 Отправка уведомления...")
        await send_telegram_async("✅ <b>Бот запущен!</b>\n🕐 " + datetime.now().strftime("%H:%M:%S"))
        
        print("🔄 Инициализация диалогов...")
        await self._init_dialogs()
        
        print("🔄 Запуск главного цикла...")
        await self.main_loop()
    
    async def _accept_cookies(self):
        try:
            accept_btn = self.page.locator('.cc-accept-all').first
            if await accept_btn.count() > 0 and await accept_btn.is_visible():
                await accept_btn.click(timeout=5000)
                print("✅ Cookie-баннер закрыт")
                await asyncio.sleep(0.5)
        except Exception as e:
            print(f"⚠️ Не удалось закрыть cookie-баннер: {e}")
    
    async def _get_message_id(self, message_element, debug=False):
        try:
            # 1. data-id
            msg_id = await message_element.get_attribute('data-id')
            if msg_id:
                if debug:
                    print(f"✅ Найден data-id: {msg_id}")
                return f"dataid_{msg_id}"
            
            # 2. id
            msg_id = await message_element.get_attribute('id')
            if msg_id:
                if debug:
                    print(f"✅ Найден id: {msg_id}")
                return f"id_{msg_id}"
            
            # 3. msg-* в классах
            classes = await message_element.get_attribute('class') or ""
            match = re.search(r'msg-(\d+)', classes)
            if match:
                if debug:
                    print(f"✅ Найден msg-* в классах: {match.group(1)}")
                return f"class_{match.group(1)}"
            
            # 4. Хеш только из текста сообщения
            if debug:
                print("⚠️ ID не найден, создаю хеш из текста сообщения...")
            
            # Определяем автора
            author = "client"
            if "out" in classes:
                author = "me"
            
            # Берем ТОЛЬКО текст сообщения
            body = message_element.locator(".chat-msg-text, .msg-text, [class*='msg-text']").first
            text = ""
            if await body.count() > 0:
                text = await body.text_content() or ""
            else:
                text = await message_element.text_content() or ""
            
            # Очищаем текст от лишних пробелов
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Добавляем позицию в DOM для стабильности
            index = await message_element.evaluate("""
                el => Array.from(el.parentNode.children).indexOf(el)
            """)
            
            # Создаём хеш
            content = f"{author}|{text}|{index}"
            hash_id = hashlib.md5(content.encode('utf-8')).hexdigest()[:16]
            
            if debug:
                print(f"🔑 Создан хеш ID: {hash_id} (текст: {text[:30]}...)")
            
            return f"hash_{hash_id}"
            
        except Exception as e:
            print(f"⚠️ Ошибка получения ID: {e}")
            return None
    
    async def _debug_message_structure(self, message_element):
        try:
            attrs = await message_element.evaluate("""
                element => {
                    const result = {};
                    for (const attr of element.attributes) {
                        result[attr.name] = attr.value;
                    }
                    return result;
                }
            """)
            print(f"🔍 Атрибуты сообщения:")
            for key, value in attrs.items():
                print(f"    {key}: {value}")
            
            classes = await message_element.get_attribute('class')
            print(f"🔍 Классы: {classes}")
            
            html = await message_element.evaluate("el => el.outerHTML")
            print(f"🔍 OuterHTML (первые 200 символов): {html[:200]}...")
            
            if 'data-id' in html:
                print("✅ Найден data-id в HTML!")
                match = re.search(r'data-id=["\']([^"\']+)["\']', html)
                if match:
                    print(f"   data-id = {match.group(1)}")
            
            if 'id="' in html:
                print("✅ Найден id в HTML!")
                match = re.search(r'id=["\']([^"\']+)["\']', html)
                if match:
                    print(f"   id = {match.group(1)}")
            
            return attrs
        except Exception as e:
            print(f"⚠️ Ошибка диагностики: {e}")
            return {}
    
    async def login(self):
        try:
            account_locator = self.page.locator('.user-link-name').first
            is_logged_in = await account_locator.count() > 0

            if is_logged_in:
                self.own_username = (await account_locator.text_content() or "").strip()
                print(f"✅ Сессия активна (аккаунт: {self.own_username})")
                await send_telegram_async(f"✅ <b>Вход в FunPay выполнен</b> (аккаунт: {self.own_username})")
                return

            await self._save_debug("session_invalid")
            raise RuntimeError("❌ Сессия по golden_key недействительна")
        except Exception as e:
            print(f"❌ Ошибка входа: {e}")
            await send_telegram_async(f"⚠️ <b>Ошибка входа!</b>\n{str(e)}")
            raise
    
    async def _init_dialogs(self):
        try:
            print("🔍 Инициализация диалогов...")
            
            await self.page.goto("https://funpay.com/chat/")
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            await self._accept_cookies()
            
            dialogs = self.page.locator('.contact-item')
            dialog_count = await dialogs.count()
            print(f"🔍 Найдено диалогов: {dialog_count}")
            
            initialized = 0
            failed = 0
            
            for i in range(dialog_count):
                try:
                    dialog = dialogs.nth(i)
                    client_name = await self._get_client_name_from_dialog(dialog)
                    if not client_name:
                        continue
                    
                    await dialog.click()
                    await asyncio.sleep(1)
                    
                    messages = self.page.locator('.chat-msg-item')
                    msg_count = await messages.count()
                    if msg_count > 0:
                        last_msg = messages.nth(msg_count - 1)
                        msg_id = await self._get_message_id(last_msg)
                        
                        self.db.add_client(client_name, self.page.url)
                        
                        if msg_id:
                            self.db.set_last_message_id(client_name, msg_id)
                            print(f"📌 {client_name}: последний ID = {msg_id}")
                            initialized += 1
                        else:
                            print(f"⚠️ {client_name}: не удалось получить ID, пропускаю")
                            failed += 1
                    
                    await self.page.goto("https://funpay.com/chat/")
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"⚠️ Ошибка инициализации диалога {i}: {e}")
                    continue
            
            self.first_run = False
            print(f"✅ Инициализация завершена! Обработано {initialized}, пропущено {failed}")
            
        except Exception as e:
            print(f"⚠️ Ошибка инициализации: {e}")
    
    async def _save_debug(self, tag):
        try:
            screenshot_path = f"/tmp/debug_{tag}.png"
            html_path = f"/tmp/debug_{tag}.html"
            await self.page.screenshot(path=screenshot_path, full_page=True)
            html = await self.page.content()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"🔍 Debug сохранён: {screenshot_path}")

            title = await self.page.title()
            caption = f"🔍 Debug: {tag}\n📍 URL: {self.page.url}\n📄 Title: {title}"
            await send_telegram_photo_async(screenshot_path, caption)
            await send_telegram_document_async(html_path, f"HTML: {tag}")

            page_text = (await self.page.content()).lower()
            suspicious_markers = ["captcha", "капча", "подтвердите, что вы не робот", "cloudflare", "доступ ограничен", "заблокирован"]
            found_markers = [m for m in suspicious_markers if m in page_text]
            if found_markers:
                await send_telegram_async(f"⚠️ Возможна блокировка/капча. Найдены маркеры: {', '.join(found_markers)}")
        except Exception as e:
            print(f"⚠️ Не удалось сохранить/отправить debug: {e}")
    
    async def _get_element_text(self, locator):
        try:
            if await locator.count() > 0:
                return await locator.first.text_content()
        except Exception:
            pass
        return None
    
    async def _get_client_name_from_dialog(self, dialog):
        try:
            name_selectors = ['.media-user-name']
            for selector in name_selectors:
                locator = dialog.locator(selector)
                if await locator.count() > 0:
                    name = await locator.first.text_content()
                    if name:
                        return name.strip()
            profile_link = dialog.locator('a[href*="/user/"]')
            if await profile_link.count() > 0:
                href = await profile_link.first.get_attribute('href')
                if href:
                    match = re.search(r'/user/([^/]+)', href)
                    if match:
                        return match.group(1)
        except Exception:
            pass
        return None
    
    async def _is_message_from_client(self, message_element):
        try:
            classes = await message_element.get_attribute('class') or ""
            if 'out' in classes:
                return False
            if 'in' in classes:
                return True
            text = await message_element.text_content() or ""
            text_lower = text.lower()
            bot_messages = [self.config["FIRST_MESSAGE"].lower()[:30], self.config["PAYMENT_CONFIRMED_MESSAGE"].lower()[:30]]
            for bot_msg in bot_messages:
                if bot_msg in text_lower:
                    return False
            return True
        except Exception:
            return True
    
    async def _is_payment_confirmation(self, text):
        text = text.lower()
        for pattern in self.config["PAYMENT_PATTERNS"]:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    async def send_message(self, text):
        try:
            await self._accept_cookies()
            textarea = self.page.locator('textarea[name="content"]')
            if await textarea.count() == 0:
                print("⚠️ Поле ввода не найдено")
                return
            await textarea.first.fill(text)
            await asyncio.sleep(0.5)
            send_btn = self.page.locator('.chat-form button[type="submit"]')
            if await send_btn.count() > 0:
                await send_btn.first.click()
            else:
                await textarea.first.press("Enter")
        except Exception as e:
            print(f"❌ Ошибка отправки: {e}")
    
    async def check_new_dialogs(self):
        try:
            if "/chat" not in self.page.url:
                await self.page.goto("https://funpay.com/chat/")
                await self.page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                await self._accept_cookies()
            
            if self.debug_requested:
                await self._save_debug("chat_list")
                unread_preview = self.page.locator('.contact-item.unread').first
                if await unread_preview.count() > 0:
                    try:
                        await unread_preview.click()
                        await asyncio.sleep(2)
                        await self._save_debug("dialog_opened")
                    except Exception as e:
                        print(f"⚠️ Не удалось открыть диалог: {e}")
                self.debug_requested = False
            
            dialogs = self.page.locator('.contact-item')
            dialog_count = await dialogs.count()
            
            if dialog_count == 0:
                return
            
            print(f"📩 Обрабатываю {dialog_count} диалогов")
            
            for i in range(dialog_count):
                try:
                    dialog = dialogs.nth(i)
                    client_name = await self._get_client_name_from_dialog(dialog)
                    if not client_name:
                        client_name = "покупатель"
                    
                    self.db.add_client(client_name, self.page.url)
                    
                    last_saved_id = self.db.get_last_message_id(client_name)
                    
                    if last_saved_id is None:
                        print(f"⚠️ {client_name}: нет сохраненного ID, пропускаю")
                        await self.page.goto("https://funpay.com/chat/")
                        await asyncio.sleep(1)
                        continue
                    
                    print(f"🔍 {client_name}: last_saved_id = {last_saved_id}")
                    
                    await dialog.click()
                    await asyncio.sleep(1)
                    
                    messages = self.page.locator('.chat-msg-item')
                    msg_count = await messages.count()
                    if msg_count == 0:
                        await self.page.goto("https://funpay.com/chat/")
                        continue
                    
                    # Диагностика первого сообщения
                    if i == 0 and msg_count > 0:
                        await self._debug_message_structure(messages.nth(0))
                    
                    # Находим новые сообщения (исправленная логика)
                    new_messages = []
                    collect = False
                    
                    # Проходим по сообщениям в порядке от старых к новым
                    for j in range(msg_count):
                        msg_element = messages.nth(j)
                        msg_id = await self._get_message_id(msg_element)
                        
                        # Если еще не начали собирать, ищем last_saved_id
                        if not collect:
                            if msg_id and msg_id == last_saved_id:
                                collect = True
                                print(f"  ✅ Найден последний обработанный ID: {msg_id}")
                            continue
                        
                        # После нахождения last_saved_id - собираем все следующие сообщения
                        if msg_id:
                            new_messages.append((msg_element, msg_id))
                            print(f"  ➕ Новое сообщение: {msg_id}")
                        else:
                            print(f"  ⚠️ Сообщение без ID, пропускаю")
                    
                    # Если last_saved_id не найден - НЕ обновляем базу!
                    if not collect and msg_count > 0:
                        print(f"⚠️ Последний ID не найден у {client_name}, НЕ обновляю базу (только лог)")
                        # Отправляем предупреждение в Telegram
                        await send_telegram_async(f"⚠️ <b>Рассинхрон ID у {client_name}</b>\nСохраненный ID не найден. Новые сообщения не обрабатываются.")
                        # НЕ обновляем базу - просто выходим
                        await self.page.goto("https://funpay.com/chat/")
                        await asyncio.sleep(1)
                        continue
                    
                    if new_messages:
                        print(f"📨 Новых сообщений для {client_name}: {len(new_messages)}")
                        
                        # Обновляем last_message_id на последнее новое
                        last_new_id = new_messages[-1][1]
                        if last_new_id:
                            self.db.set_last_message_id(client_name, last_new_id)
                            print(f"💾 Обновлен last_message_id: {last_new_id}")
                        
                        for msg_element, msg_id in new_messages:
                            msg_text = await msg_element.text_content() or ""
                            is_from_client = await self._is_message_from_client(msg_element)
                            is_payment = await self._is_payment_confirmation(msg_text)
                            
                            if is_from_client and not self.db.is_first_message_sent(client_name):
                                buyer_name = await self._get_element_text(
                                    self.page.locator('.chat-header .media-user-name')
                                ) or "покупатель"
                                first_msg = self.config["FIRST_MESSAGE"].format(buyer_name=buyer_name)
                                await self.send_message(first_msg)
                                self.db.mark_first_message_sent(client_name)
                                print(f"📨 Первое сообщение для {client_name}")
                                await asyncio.sleep(1)
                            
                            if is_from_client:
                                msg_lower = msg_text.lower()
                                if self.config["FRUIT_COMMAND"] in msg_lower:
                                    if not self.db.is_fruit_notified(client_name):
                                        notify = f"🍎 <b>КЛИЕНТ КУПИЛ ФРУКТ!</b>\n\n👤 {client_name}\n💬 {msg_text[:200]}\n🔗 {self.page.url}\n⏰ {datetime.now().strftime('%H:%M:%S')}"
                                        await send_telegram_async(notify)
                                        self.db.mark_fruit_notified(client_name)
                                        print(f"🍎 Уведомление о фрукте для {client_name}")
                                        await self.send_message("🍎 Продавец уведомлен!")
                                elif self.config["CODE_COMMAND"] in msg_lower:
                                    if not self.db.is_code_notified(client_name):
                                        notify = f"🔑 <b>КЛИЕНТ ЗАПРОСИЛ КОД!</b>\n\n👤 {client_name}\n💬 {msg_text[:200]}\n🔗 {self.page.url}\n⏰ {datetime.now().strftime('%H:%M:%S')}"
                                        await send_telegram_async(notify)
                                        self.db.mark_code_notified(client_name)
                                        print(f"🔑 Уведомление о коде для {client_name}")
                                        await self.send_message("🔑 Продавец уведомлен!")
                            
                            if is_payment:
                                if not self.db.is_thank_you_sent(client_name):
                                    order_match = re.search(r'#[A-Z0-9]+', msg_text)
                                    order_number = order_match.group(0) if order_match else ""
                                    print(f"💳 Оплата! Заказ {order_number} | {client_name}")
                                    notify = f"💳 <b>ОПЛАТА ПОДТВЕРЖДЕНА!</b>\n\n👤 {client_name}\n📦 Заказ: {order_number}\n🔗 {self.page.url}\n⏰ {datetime.now().strftime('%H:%M:%S')}"
                                    await send_telegram_async(notify)
                                    await self.send_message(self.config["PAYMENT_CONFIRMED_MESSAGE"])
                                    self.db.mark_payment_confirmed(client_name)
                                    self.db.mark_thank_you_sent(client_name)
                                    print(f"🙏 Благодарность для {client_name}")
                                    await asyncio.sleep(1)
                    else:
                        print(f"⏭️ Нет новых сообщений для {client_name}")
                    
                    await self.page.goto("https://funpay.com/chat/")
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"⚠️ Ошибка диалога {i}: {e}")
                    await self.page.goto("https://funpay.com/chat/")
                    continue
        except Exception as e:
            print(f"⚠️ Ошибка проверки: {e}")
    
    async def main_loop(self):
        print("\n" + "="*60)
        print("🚀 БОТ ЗАПУЩЕН")
        print("="*60)
        print(f"⏱ Проверка каждые {self.config['CHECK_INTERVAL']} сек")
        print("="*60 + "\n")
        
        while self.running:
            try:
                await self.check_new_dialogs()
                wait_time = random.randint(max(1, self.config["CHECK_INTERVAL"] - 5), self.config["CHECK_INTERVAL"] + 5)
                print(f"⏳ Следующая проверка через {wait_time} сек")
                await asyncio.sleep(wait_time)
            except Exception as e:
                print(f"❌ Критическая ошибка: {e}")
                await send_telegram_async(f"⚠️ <b>Ошибка!</b>\n{str(e)}")
                await asyncio.sleep(60)
                try:
                    print("🔄 Перезапуск...")
                    await self.page.close()
                    await self.browser.close()
                    self.browser = await self.playwright.chromium.launch(
                        headless=not self.config["DEBUG"],
                        args=['--no-sandbox', '--disable-setuid-sandbox']
                    )
                    self.page = await self.browser.new_page()
                    await self.page.context.add_cookies([
                        {
                            "name": "golden_key",
                            "value": self.config["FUNPAY_GOLDEN_KEY"],
                            "domain": "funpay.com",
                            "path": "/",
                        }
                    ])
                    await self.page.goto("https://funpay.com/")
                    await self.login()
                    print("✅ Восстановлено!")
                except Exception as restart_error:
                    print(f"❌ Ошибка восстановления: {restart_error}")
    
    async def close(self):
        self.running = False
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        await send_telegram_async("🛑 <b>Бот остановлен</b>")

# ==========================================
# 5. HEALTH CHECKS + SCREENSHOT + DEBUG
# ==========================================
app = Flask(__name__)

MAIN_EVENT_LOOP = None
BOT_INSTANCE = None
SCREENSHOT_TOKEN = os.environ.get("SCREENSHOT_TOKEN", "")

@app.route('/')
def health_check():
    return "Bot is running!", 200

@app.route('/health')
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}, 200

@app.route('/screenshot')
def screenshot():
    if SCREENSHOT_TOKEN:
        token = request.args.get("token", "")
        if token != SCREENSHOT_TOKEN:
            return "Forbidden", 403

    if BOT_INSTANCE is None or BOT_INSTANCE.page is None or MAIN_EVENT_LOOP is None:
        return "Бот ещё не запущен", 503

    async def _take_screenshot():
        return await BOT_INSTANCE.page.screenshot(full_page=True)

    try:
        future = asyncio.run_coroutine_threadsafe(_take_screenshot(), MAIN_EVENT_LOOP)
        image_bytes = future.result(timeout=15)
        return Response(image_bytes, mimetype="image/png")
    except Exception as e:
        return f"Ошибка получения скриншота: {e}", 500

@app.route('/debug-structure')
def debug_structure():
    if SCREENSHOT_TOKEN:
        token = request.args.get("token", "")
        if token != SCREENSHOT_TOKEN:
            return "Forbidden", 403

    if BOT_INSTANCE is None or BOT_INSTANCE.page is None:
        return "Бот не запущен", 503

    async def _get_structure():
        result = {}
        try:
            await BOT_INSTANCE.page.goto("https://funpay.com/chat/", wait_until="domcontentloaded")
            await BOT_INSTANCE.page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

            dialogs = BOT_INSTANCE.page.locator('.contact-item')
            dialog_count = await dialogs.count()
            result["dialog_count"] = dialog_count

            if dialog_count == 0:
                result["error"] = "Нет диалогов"
                return result

            await dialogs.first.click()
            await BOT_INSTANCE.page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

            messages = BOT_INSTANCE.page.locator('.chat-msg-item')
            msg_count = await messages.count()
            result["msg_count"] = msg_count

            if msg_count == 0:
                result["error"] = "Нет сообщений"
                return result

            first_msg = messages.first
            attrs = await first_msg.evaluate("""
                element => {
                    if (!element) return null;
                    const result = {};
                    for (const attr of element.attributes) {
                        result[attr.name] = attr.value;
                    }
                    result.outerHTML = element.outerHTML || '';
                    result.className = element.className || '';
                    result.tagName = element.tagName || '';
                    return result;
                }
            """)

            result["attributes"] = attrs
            result["has_data_id"] = 'data-id' in (attrs or {})
            result["has_id"] = 'id' in (attrs or {})
            result["success"] = True

            return result

        except Exception as e:
            result["error"] = str(e)
            result["error_type"] = type(e).__name__
            import traceback
            result["traceback"] = traceback.format_exc()
            return result

    try:
        future = asyncio.run_coroutine_threadsafe(_get_structure(), MAIN_EVENT_LOOP)
        result = future.result(timeout=30)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Ошибка: {e}", 500

@app.route('/debug-now')
def debug_now():
    if SCREENSHOT_TOKEN:
        token = request.args.get("token", "")
        if token != SCREENSHOT_TOKEN:
            return "Forbidden", 403

    if BOT_INSTANCE is None:
        return "Бот ещё не запущен", 503

    BOT_INSTANCE.debug_requested = True
    return "Запрошено. Скриншот и HTML придут в Telegram в течение 15-20 секунд.", 200

def run_web():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ==========================================
# 6. ЗАПУСК
# ==========================================
def run_bot():
    print("🔵 run_bot()")
    sys.stdout.flush()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main_bot())
    except Exception as e:
        print(f"❌ RUN_BOT_ERROR: {repr(e)}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        loop.close()

async def main_bot():
    global MAIN_EVENT_LOOP, BOT_INSTANCE
    print("🔵 main_bot()")
    sys.stdout.flush()
    MAIN_EVENT_LOOP = asyncio.get_running_loop()
    bot = FunPayBot(CONFIG)
    BOT_INSTANCE = bot
    await bot.start()

def main():
    print("🔵 main()")
    sys.stdout.flush()
    print("🔄 Запуск...")
    sys.stdout.flush()
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    print(f"✅ Health check: порт {os.environ.get('PORT', 10000)}")
    sys.stdout.flush()
    run_bot()

if __name__ == "__main__":
    print("🔵 __main__")
    sys.stdout.flush()
    main()
