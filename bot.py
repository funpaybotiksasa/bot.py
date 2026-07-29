import asyncio
import re
import time
import random
import json
import os
import requests
import subprocess
import sys
import threading
from playwright.async_api import async_playwright
from datetime import datetime
from flask import Flask

# ==========================================
# 1. НАСТРОЙКИ (ИЗМЕНИ ПОД СЕБЯ)
# ==========================================
CONFIG = {
    # --- FunPay (из переменных окружения) ---
    "FUNPAY_LOGIN": os.getenv("FUNPAY_LOGIN", "leopardplay135"),
    "FUNPAY_PASSWORD": os.getenv("FUNPAY_PASSWORD", "Rodionrodion@10"),
    
    # --- Telegram (ВШИТЫЕ CHAT ID) ---
    "TELEGRAM_TOKEN": os.getenv("TELEGRAM_TOKEN", "ТВОЙ_ТОКЕН_ОТ_BOTFATHER"),
    "TELEGRAM_CHAT_IDS": [
        "8138491685",  # ← ВСТАВЬ СВОЙ CHAT ID (только цифры!)
        "1973759066",  # ← Второй Chat ID (если нужен)
    ],
    
    # --- Сообщения бота ---
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
    "DEBUG": False  # На сервере всегда False
}

# ==========================================
# 2. УСТАНОВКА БРАУЗЕРА
# ==========================================
def install_browser():
    """Устанавливает браузер для Playwright если его нет"""
    try:
        print("🔄 Проверка браузера...")
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "firefox"],
            capture_output=True,
            text=True,
            timeout=180
        )
        if result.returncode == 0:
            print("✅ Браузер установлен")
            return True
        else:
            print(f"❌ Ошибка установки: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

# ==========================================
# 3. ОТПРАВКА УВЕДОМЛЕНИЙ В TELEGRAM
# ==========================================
def send_telegram(message):
    """Отправляет сообщение ВСЕМ пользователям из списка TELEGRAM_CHAT_IDS"""
    if not CONFIG["TELEGRAM_TOKEN"]:
        print("⚠️ TELEGRAM_TOKEN не настроен!")
        return False
    
    sent_count = 0
    
    for chat_id in CONFIG["TELEGRAM_CHAT_IDS"]:
        chat_id = str(chat_id).strip()
        if not chat_id:
            continue
            
        try:
            url = f"https://api.telegram.org/bot{CONFIG['TELEGRAM_TOKEN']}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                sent_count += 1
                print(f"✅ Уведомление отправлено в Telegram (chat_id: {chat_id})")
            else:
                print(f"❌ Ошибка для {chat_id}: {response.text}")
                
        except Exception as e:
            print(f"❌ Ошибка для {chat_id}: {e}")
    
    if sent_count > 0:
        print(f"✅ Уведомление отправлено {sent_count} пользователям")
        return True
    return False

# ==========================================
# 4. БАЗА ДАННЫХ
# ==========================================
class ClientDatabase:
    def __init__(self):
        self.db_file = "clients_data.json"
        self.data = self.load()
    
    def load(self):
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save(self):
        with open(self.db_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
    
    def add_client(self, client_name, chat_url):
        if client_name not in self.data:
            self.data[client_name] = {
                "chat_url": chat_url,
                "first_message_sent": False,
                "payment_confirmed": False,
                "thank_you_sent": False,
                "fruit_notified": False,
                "code_notified": False,
                "date": datetime.now().isoformat()
            }
            self.save()
            print(f"📝 Клиент {client_name} добавлен в базу")
            return True
        return False
    
    def mark_first_message_sent(self, client_name):
        if client_name in self.data:
            self.data[client_name]["first_message_sent"] = True
            self.save()
            return True
        return False
    
    def mark_payment_confirmed(self, client_name):
        if client_name in self.data:
            self.data[client_name]["payment_confirmed"] = True
            self.save()
            return True
        return False
    
    def mark_thank_you_sent(self, client_name):
        if client_name in self.data:
            self.data[client_name]["thank_you_sent"] = True
            self.save()
            return True
        return False
    
    def mark_fruit_notified(self, client_name):
        if client_name in self.data:
            self.data[client_name]["fruit_notified"] = True
            self.save()
            return True
        return False
    
    def mark_code_notified(self, client_name):
        if client_name in self.data:
            self.data[client_name]["code_notified"] = True
            self.save()
            return True
        return False
    
    def is_first_message_sent(self, client_name):
        if client_name in self.data:
            return self.data[client_name].get("first_message_sent", False)
        return False
    
    def is_thank_you_sent(self, client_name):
        if client_name in self.data:
            return self.data[client_name].get("thank_you_sent", False)
        return False
    
    def is_fruit_notified(self, client_name):
        if client_name in self.data:
            return self.data[client_name].get("fruit_notified", False)
        return False
    
    def is_code_notified(self, client_name):
        if client_name in self.data:
            return self.data[client_name].get("code_notified", False)
        return False

# ==========================================
# 5. ОСНОВНОЙ БОТ
# ==========================================
class FunPayBot:
    def __init__(self, config):
        self.config = config
        self.browser = None
        self.page = None
        self.db = ClientDatabase()
    
    async def start(self):
        """Запуск браузера и вход на FunPay"""
        
        # Устанавливаем браузер если его нет
        install_browser()
        
        # Отправляем уведомление о запуске
        send_telegram("✅ <b>Бот запущен!</b>\n🕐 " + datetime.now().strftime("%H:%M:%S"))
        
        p = await async_playwright().start()
        
        # Используем Firefox
        self.browser = await p.firefox.launch(
            headless=not self.config["DEBUG"],
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        
        self.page = await self.browser.new_page()
        
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        print("🔄 Открываю FunPay...")
        await self.page.goto("https://funpay.com/", timeout=60000)
        
        await self.page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        await self.login()
        await self.main_loop()
    
    async def login(self):
        """Вход на FunPay"""
        try:
            print("🔑 Ищу кнопку входа...")
            
            login_selectors = [
                'text="Вход"',
                'text="Войти"',
                'button:has-text("Вход")',
                'button:has-text("Войти")',
                'a:has-text("Вход")',
                '.login-btn',
                '[class*="login"]',
                '[class*="auth"]'
            ]
            
            login_found = False
            for selector in login_selectors:
                try:
                    if await self.page.locator(selector).count() > 0:
                        await self.page.click(selector, timeout=5000)
                        print(f"✅ Нажал кнопку: {selector}")
                        login_found = True
                        break
                except:
                    continue
            
            if not login_found:
                print("⚠️ Кнопка входа не найдена. Возможно, уже авторизованы.")
                profile = await self.page.locator('[class*="profile"], [class*="user"]').count()
                if profile > 0:
                    print("✅ Похоже, уже авторизованы!")
                    return
                else:
                    print("❌ Не удалось найти кнопку входа.")
                    return
            
            await asyncio.sleep(2)
            
            print("🔑 Ввожу логин...")
            await self.page.fill('input[name="user[login]"]', self.config["FUNPAY_LOGIN"])
            await asyncio.sleep(1)
            
            print("🔑 Ввожу пароль...")
            await self.page.fill('input[name="user[password]"]', self.config["FUNPAY_PASSWORD"])
            await asyncio.sleep(1)
            
            print("🔑 Нажимаю Войти...")
            submit_selectors = [
                'button[type="submit"]',
                'button:has-text("Войти")',
                'button:has-text("Вход")',
                'input[type="submit"]'
            ]
            
            for selector in submit_selectors:
                try:
                    if await self.page.locator(selector).count() > 0:
                        await self.page.click(selector, timeout=5000)
                        print(f"✅ Нажал кнопку: {selector}")
                        break
                except:
                    continue
            
            await asyncio.sleep(5)
            await self.page.wait_for_load_state("networkidle", timeout=30000)
            
            try:
                await self.page.locator('[class*="profile"], [class*="user"]').first.wait_for(timeout=10000)
                print("✅ Успешный вход в FunPay!")
                send_telegram("✅ <b>Успешный вход в FunPay!</b>")
            except:
                print("⚠️ Не удалось подтвердить вход. Проверьте логин/пароль.")
                send_telegram("⚠️ <b>Не удалось войти в FunPay!</b> Проверьте логин/пароль.")
                
        except Exception as e:
            print(f"❌ Ошибка при входе: {e}")
            send_telegram(f"⚠️ <b>Ошибка входа в FunPay!</b>\n{str(e)}")
    
    async def get_client_name_from_chat(self):
        try:
            selectors = [
                '.chat-header .user-name',
                '.dialog-header .name',
                '.chat-header .name',
                '.user-name',
                '[class*="user-name"]'
            ]
            
            for selector in selectors:
                try:
                    name_element = await self.page.locator(selector).first
                    if name_element:
                        name = await name_element.inner_text()
                        return name.strip()
                except:
                    continue
            
            return "покупатель"
        except:
            return "покупатель"
    
    async def is_payment_confirmation_message(self, text):
        text = text.lower()
        for pattern in self.config["PAYMENT_PATTERNS"]:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    async def check_new_dialogs(self):
        try:
            await self.page.goto("https://funpay.com/chat/")
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            
            dialogs = await self.page.locator('.chat-item:has(.badge)').all()
            
            if not dialogs:
                return
            
            print(f"📩 Найдено {len(dialogs)} диалогов с новыми сообщениями")
            
            for dialog in dialogs:
                try:
                    client_name = await self._get_client_name_from_dialog(dialog)
                    
                    if not client_name:
                        client_name = "покупатель"
                    
                    await dialog.click()
                    await asyncio.sleep(2)
                    
                    buyer_name = await self.get_client_name_from_chat()
                    
                    messages = await self.page.locator('.message-text').all()
                    if not messages:
                        await self.page.goto("https://funpay.com/chat/")
                        continue
                    
                    for msg_element in messages:
                        try:
                            msg_text = await msg_element.inner_text()
                            
                            is_system = await self._is_system_message(msg_element)
                            is_payment = await self.is_payment_confirmation_message(msg_text)
                            is_from_client = await self._is_message_from_client(msg_element)
                            
                            if client_name not in self.db.data:
                                self.db.add_client(client_name, self.page.url)
                            
                            if is_from_client:
                                msg_lower = msg_text.lower()
                                
                                # Проверяем команду !фрукт
                                if self.config["FRUIT_COMMAND"] in msg_lower:
                                    if not self.db.is_fruit_notified(client_name):
                                        notify_msg = (
                                            f"🍎 <b>КЛИЕНТ КУПИЛ ФРУКТ!</b>\n\n"
                                            f"👤 Клиент: {client_name}\n"
                                            f"💬 Сообщение: {msg_text[:200]}\n"
                                            f"🔗 Ссылка: {self.page.url}\n\n"
                                            f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}"
                                        )
                                        send_telegram(notify_msg)
                                        self.db.mark_fruit_notified(client_name)
                                        print(f"🍎 Уведомление о фрукте отправлено для {client_name}")
                                        await self.send_message("🍎 Продавец уведомлен о покупке фрукта! Ожидайте выдачи.")
                                
                                # Проверяем команду !код
                                elif self.config["CODE_COMMAND"] in msg_lower:
                                    if not self.db.is_code_notified(client_name):
                                        notify_msg = (
                                            f"🔑 <b>КЛИЕНТ ЗАПРОСИЛ КОД С ПОЧТЫ!</b>\n\n"
                                            f"👤 Клиент: {client_name}\n"
                                            f"💬 Сообщение: {msg_text[:200]}\n"
                                            f"🔗 Ссылка: {self.page.url}\n\n"
                                            f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}"
                                        )
                                        send_telegram(notify_msg)
                                        self.db.mark_code_notified(client_name)
                                        print(f"🔑 Уведомление о коде отправлено для {client_name}")
                                        await self.send_message("🔑 Продавец уведомлен о запросе кода! Ожидайте.")
                                
                                # Первое сообщение
                                elif not self.db.is_first_message_sent(client_name):
                                    is_order = any(word in msg_lower for word in self.config["ORDER_WORDS"])
                                    
                                    if is_order:
                                        first_msg = self.config["FIRST_MESSAGE"].format(buyer_name=buyer_name)
                                        await self.send_message(first_msg)
                                        self.db.mark_first_message_sent(client_name)
                                        print(f"📨 Отправлено первое сообщение клиенту {client_name}")
                                        await asyncio.sleep(1)
                            
                            # Системное сообщение о подтверждении оплаты
                            if is_system and is_payment:
                                if not self.db.is_thank_you_sent(client_name):
                                    order_match = re.search(r'#[A-Z0-9]+', msg_text)
                                    order_number = order_match.group(0) if order_match else ""
                                    
                                    print(f"💳 Обнаружено подтверждение оплаты! Заказ {order_number}")
                                    print(f"📝 Клиент: {client_name}")
                                    
                                    payment_notify = (
                                        f"💳 <b>ОПЛАТА ПОДТВЕРЖДЕНА!</b>\n\n"
                                        f"👤 Клиент: {client_name}\n"
                                        f"📦 Заказ: {order_number}\n"
                                        f"🔗 Ссылка: {self.page.url}\n\n"
                                        f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}"
                                    )
                                    send_telegram(payment_notify)
                                    
                                    await self.send_message(self.config["PAYMENT_CONFIRMED_MESSAGE"])
                                    self.db.mark_payment_confirmed(client_name)
                                    self.db.mark_thank_you_sent(client_name)
                                    print(f"🙏 Отправлена благодарность клиенту {client_name}")
                                    await asyncio.sleep(1)
                            
                        except Exception as e:
                            print(f"⚠️ Ошибка при проверке сообщения: {e}")
                            continue
                    
                    await self.page.goto("https://funpay.com/chat/")
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    print(f"⚠️ Ошибка обработки диалога: {e}")
                    await self.page.goto("https://funpay.com/chat/")
                    continue
                    
        except Exception as e:
            print(f"⚠️ Ошибка проверки диалогов: {e}")
    
    async def _is_system_message(self, message_element):
        try:
            classes = await message_element.get_attribute('class')
            if classes:
                if 'system' in classes or 'notification' in classes or 'info' in classes:
                    return True
            
            text = await message_element.inner_text()
            if 'подтвердил' in text and 'заказа' in text:
                return True
            if 'отправил деньги' in text:
                return True
            
            return False
        except:
            return False
    
    async def _get_client_name_from_dialog(self, dialog_element):
        try:
            selectors = [
                '.chat-item-name',
                '.user-name',
                '.name',
                '[class*="chat-item"] [class*="name"]'
            ]
            
            for selector in selectors:
                try:
                    name_element = await dialog_element.locator(selector).first
                    if name_element:
                        name = await name_element.inner_text()
                        return name.strip()
                except:
                    continue
            
            profile_link = await dialog_element.locator('a[href*="/user/"]').first
            if profile_link:
                href = await profile_link.get_attribute('href')
                match = re.search(r'/user/([^/]+)', href)
                if match:
                    return match.group(1)
        except:
            pass
        return None
    
    async def _is_message_from_client(self, message_element):
        try:
            classes = await message_element.get_attribute('class')
            if classes:
                if 'out' in classes or 'message-out' in classes:
                    return True
                if 'in' in classes or 'message-in' in classes:
                    return False
            
            text = await message_element.inner_text()
            text_lower = text.lower()
            
            if await self._is_system_message(message_element):
                return False
            
            bot_messages = [
                self.config["FIRST_MESSAGE"].lower()[:30],
                self.config["PAYMENT_CONFIRMED_MESSAGE"].lower()[:30]
            ]
            
            for bot_msg in bot_messages:
                if bot_msg in text_lower:
                    return False
            
            return True
        except:
            return True
    
    async def send_message(self, text):
        try:
            textarea = await self.page.locator('textarea[name="message"], .chat-input textarea').first
            if not textarea:
                print("⚠️ Поле ввода не найдено")
                return
            
            await textarea.fill(text)
            await asyncio.sleep(0.5)
            
            send_btn = await self.page.locator('button:has-text("Отправить"), button[type="submit"]').first
            if send_btn:
                await send_btn.click()
                await asyncio.sleep(1)
            else:
                await textarea.press("Enter")
                await asyncio.sleep(1)
                
        except Exception as e:
            print(f"❌ Ошибка отправки сообщения: {e}")
    
    async def main_loop(self):
        print("\n" + "="*60)
        print("🚀 БОТ ЗАПУЩЕН")
        print("="*60)
        print("📌 Бот отвечает на первое сообщение клиента")
        print("📌 Команда !фрукт → уведомление в Telegram")
        print("📌 Команда !код → уведомление в Telegram")
        print("📌 Бот отслеживает оплату и отправляет благодарность")
        print(f"📨 Уведомления отправляются {len(self.config['TELEGRAM_CHAT_IDS'])} пользователям")
        print(f"⏱ Проверка каждые {self.config['CHECK_INTERVAL']} секунд")
        print("="*60 + "\n")
        
        while True:
            try:
                await self.check_new_dialogs()
                
                wait_time = random.randint(
                    self.config["CHECK_INTERVAL"] - 5,
                    self.config["CHECK_INTERVAL"] + 5
                )
                print(f"⏳ Следующая проверка через {wait_time} секунд")
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                print(f"❌ Критическая ошибка в цикле: {e}")
                send_telegram(f"⚠️ <b>Критическая ошибка в боте!</b>\n{str(e)}")
                await asyncio.sleep(60)
    
    async def close(self):
        if self.browser:
            await self.browser.close()
        send_telegram("🛑 <b>Бот остановлен</b>")

# ==========================================
# 6. HEALTH CHECKS (Flask сервер)
# ==========================================
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!", 200

@app.route('/health')
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}, 200

def run_web():
    """Запускает веб-сервер для health checks"""
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# 7. ЗАПУСК
# ==========================================
async def main():
    # Запускаем веб-сервер в отдельном потоке
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    print(f"✅ Health check сервер запущен на порту {os.environ.get('PORT', 10000)}")
    
    # Запускаем бота
    bot = FunPayBot(CONFIG)
    try:
        await bot.start()
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
        await bot.close()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        send_telegram(f"❌ <b>Ошибка запуска бота!</b>\n{str(e)}")
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
