import asyncio
import re
import time
import random
import json
import os
import aiohttp
import sys
import threading
from playwright.async_api import async_playwright
from datetime import datetime
from flask import Flask

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
        "FUNPAY_LOGIN": get_env_var("FUNPAY_LOGIN"),
        "FUNPAY_PASSWORD": get_env_var("FUNPAY_PASSWORD"),
        "TELEGRAM_TOKEN": get_env_var("TELEGRAM_TOKEN"),
        "TELEGRAM_CHAT_IDS": ["1973759066"],   # ← ТВОЙ CHAT ID
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
        "ORDER_WORDS": ["здравствуйте", "привет", "хочу купить", "заказ", "куплю", "есть", "продаете", "добрый день", "здрасьте"],
        "FRUIT_COMMAND": "!фрукт",
        "CODE_COMMAND": "!код",
        "CHECK_INTERVAL": 15,
        "DEBUG": False
    }
except ValueError as e:
    print(f"❌ {e}")
    sys.exit(1)

# ==========================================
# 2. TELEGRAM (АСИНХРОННЫЙ)
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

# ==========================================
# 3. БАЗА ДАННЫХ (SQLite)
# ==========================================
import sqlite3
from contextlib import contextmanager

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
                    first_message_sent INTEGER DEFAULT 0,
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
        return self._set_value(client_name, "first_message_sent", True)
    def mark_payment_confirmed(self, client_name):
        return self._set_value(client_name, "payment_confirmed", True)
    def mark_thank_you_sent(self, client_name):
        return self._set_value(client_name, "thank_you_sent", True)
    def mark_fruit_notified(self, client_name):
        return self._set_value(client_name, "fruit_notified", True)
    def mark_code_notified(self, client_name):
        return self._set_value(client_name, "code_notified", True)
    def is_first_message_sent(self, client_name):
        return self._get_value(client_name, "first_message_sent")
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
        
        print("🔄 Открываю FunPay...")
        await self.page.goto("https://funpay.com/", timeout=60000)
        await self.page.wait_for_load_state("networkidle")
        print(f"📍 URL: {self.page.url}")
        
        print("🔄 Вход...")
        await self.login()
        
        print("🔄 Отправка уведомления...")
        await send_telegram_async("✅ <b>Бот запущен!</b>\n🕐 " + datetime.now().strftime("%H:%M:%S"))
        
        print("🔄 Запуск главного цикла...")
        await self.main_loop()
    
    async def _save_debug(self, tag):
        """Сохраняет скриншот и HTML страницы для диагностики проблем с селекторами."""
        try:
            await self.page.screenshot(path=f"/app/debug_{tag}.png", full_page=True)
            html = await self.page.content()
            with open(f"/app/debug_{tag}.html", "w", encoding="utf-8") as f:
                f.write(html)
            print(f"🔍 Debug сохранён: debug_{tag}.png / debug_{tag}.html")
        except Exception as e:
            print(f"⚠️ Не удалось сохранить debug: {e}")
    
    async def login(self):
        try:
            print("🔑 Ищу кнопку входа...")
            if "/user/" in self.page.url:
                print("✅ Уже авторизован")
                return
            
            login_selectors = [
                'a:has-text("Войти")', 'a:has-text("Вход")',
                'button:has-text("Войти")', 'button:has-text("Вход")',
                'text="Войти"', 'text="Вход"',
                '.login-btn', '[class*="login"]'
            ]
            
            login_found = False
            for selector in login_selectors:
                try:
                    locator = self.page.locator(selector).first
                    if await locator.count() > 0:
                        await locator.click(timeout=5000)
                        print(f"✅ Нажал: {selector}")
                        login_found = True
                        break
                except Exception:
                    continue
            
            if not login_found:
                await self._save_debug("no_login_button")
                raise RuntimeError("❌ Кнопка входа не найдена")
            
            # Ждём, пока реально появится форма входа (модалка), а не просто спим по таймеру
            try:
                await self.page.wait_for_selector(
                    'input[name="login"], input[name="user[login]"], '
                    'input[type="email"], input[type="text"]:visible',
                    timeout=10000
                )
            except Exception:
                pass  # если не дождались — попробуем найти всё равно, диагностика ниже покажет причину
            
            await asyncio.sleep(1)
            
            print("🔑 Логин...")
            login_input = self.page.locator(
                'input[name="login"], input[name="user[login]"], '
                'input[type="email"], input[type="text"]'
            ).first
            if await login_input.count() == 0:
                await self._save_debug("no_login_field")
                raise RuntimeError("❌ Поле логина не найдено")
            await login_input.fill(self.config["FUNPAY_LOGIN"])
            await asyncio.sleep(1)
            
            print("🔑 Пароль...")
            pass_input = self.page.locator(
                'input[name="password"], input[name="user[password]"], input[type="password"]'
            ).first
            if await pass_input.count() == 0:
                await self._save_debug("no_password_field")
                raise RuntimeError("❌ Поле пароля не найдено")
            await pass_input.fill(self.config["FUNPAY_PASSWORD"])
            await asyncio.sleep(1)
            
            print("🔑 Войти...")
            submit_selectors = [
                'button[type="submit"]', 'button:has-text("Войти")',
                'button:has-text("Вход")', 'input[type="submit"]'
            ]
            
            submit_found = False
            for selector in submit_selectors:
                try:
                    locator = self.page.locator(selector).first
                    if await locator.count() > 0:
                        await locator.click(timeout=5000)
                        print(f"✅ Нажал: {selector}")
                        submit_found = True
                        break
                except Exception:
                    continue
            
            if not submit_found:
                await self._save_debug("no_submit_button")
                raise RuntimeError("❌ Кнопка отправки не найдена")
            
            await asyncio.sleep(5)
            await self.page.wait_for_load_state("networkidle", timeout=30000)
            print(f"📍 URL после входа: {self.page.url}")
            
            if "/user/" in self.page.url:
                print("✅ Успешный вход!")
                await send_telegram_async("✅ <b>Успешный вход в FunPay!</b>")
            else:
                await self._save_debug("login_not_confirmed")
                raise RuntimeError("❌ Не удалось подтвердить вход")
                
        except Exception as e:
            print(f"❌ Ошибка входа: {e}")
            await send_telegram_async(f"⚠️ <b>Ошибка входа!</b>\n{str(e)}")
            raise
    
    async def _get_element_text(self, locator):
        try:
            if await locator.count() > 0:
                return await locator.first.text_content()
        except Exception:
            pass
        return None
    
    async def check_new_dialogs(self):
        try:
            if "/chat" not in self.page.url:
                await self.page.goto("https://funpay.com/chat/")
                await self.page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
            
            dialogs = self.page.locator('.chat-item:has(.badge), .chat-item.unread')
            dialog_count = await dialogs.count()
            if dialog_count == 0:
                return
            
            print(f"📩 Найдено {dialog_count} диалогов")
            
            for i in range(dialog_count):
                try:
                    dialog = dialogs.nth(i)
                    client_name = await self._get_client_name_from_dialog(dialog)
                    if not client_name:
                        client_name = "покупатель"
                    
                    await dialog.click()
                    await asyncio.sleep(2)
                    
                    buyer_name = await self._get_element_text(
                        self.page.locator('.chat-header .user-name, .dialog-header .name')
                    ) or "покупатель"
                    
                    messages = self.page.locator('.message-text')
                    msg_count = await messages.count()
                    if msg_count == 0:
                        continue
                    
                    for j in range(msg_count):
                        try:
                            msg_element = messages.nth(j)
                            msg_text = await msg_element.text_content() or ""
                            is_from_client = await self._is_message_from_client(msg_element)
                            is_payment = await self._is_payment_confirmation(msg_text)
                            
                            self.db.add_client(client_name, self.page.url)
                            
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
                                elif not self.db.is_first_message_sent(client_name):
                                    is_order = any(word in msg_lower for word in self.config["ORDER_WORDS"])
                                    if is_order:
                                        first_msg = self.config["FIRST_MESSAGE"].format(buyer_name=buyer_name)
                                        await self.send_message(first_msg)
                                        self.db.mark_first_message_sent(client_name)
                                        print(f"📨 Первое сообщение для {client_name}")
                                        await asyncio.sleep(1)
                            
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
                        except Exception as e:
                            print(f"⚠️ Ошибка сообщения: {e}")
                            continue
                    
                    await self.page.goto("https://funpay.com/chat/")
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"⚠️ Ошибка диалога: {e}")
                    continue
        except Exception as e:
            print(f"⚠️ Ошибка проверки: {e}")
    
    async def _is_payment_confirmation(self, text):
        text = text.lower()
        for pattern in self.config["PAYMENT_PATTERNS"]:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    async def _get_client_name_from_dialog(self, dialog):
        try:
            name_selectors = ['.chat-item-name', '.user-name', '.name']
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
    
    async def send_message(self, text):
        try:
            textarea = self.page.locator('textarea[name="message"], .chat-input textarea')
            if await textarea.count() == 0:
                print("⚠️ Поле ввода не найдено")
                return
            await textarea.first.fill(text)
            await asyncio.sleep(0.5)
            send_btn = self.page.locator('button:has-text("Отправить"), button[type="submit"]')
            if await send_btn.count() > 0:
                await send_btn.first.click()
            else:
                await textarea.first.press("Enter")
        except Exception as e:
            print(f"❌ Ошибка отправки: {e}")
    
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
# 5. HEALTH CHECKS (Flask)
# ==========================================
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!", 200

@app.route('/health')
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}, 200

def run_web():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ==========================================
# 6. ЗАПУСК
# ==========================================
def run_bot():
    print("🔵 run_bot()")
    try:
        asyncio.run(main_bot())
    except Exception as e:
        print(f"❌ RUN_BOT_ERROR: {repr(e)}")
        import traceback
        traceback.print_exc()
        raise

async def main_bot():
    print("🔵 main_bot()")
    bot = FunPayBot(CONFIG)
    await bot.start()

def main():
    print("🔵 main()")
    print("🔄 Запуск...")
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    print(f"✅ Health check: порт {os.environ.get('PORT', 10000)}")
    run_bot()

if __name__ == "__main__":
    print("🔵 __main__")
    main()
