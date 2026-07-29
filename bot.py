import asyncio
import re
import time
import random
import json
import os
from playwright.async_api import async_playwright
from datetime import datetime

# ==========================================
# 1. НАСТРОЙКИ (ИЗМЕНИ ПОД СЕБЯ)
# ==========================================
CONFIG = {
    # --- FunPay ---
    "FUNPAY_LOGIN": "leopardplay135",          # Твой логин
    "FUNPAY_PASSWORD": "Rodionrodion@10",       # Пароль
    
    # --- Сообщения бота ---
    "FIRST_MESSAGE": """Здравствуйте, {buyer_name}!

⏰ Время работы продавца с 5:00 до 22:00 по МСК.
📌 Обычно я отвечаю быстро, но бывает что время ответа может быть больше. Приношу извинения!
🤝 Аккаунты в Blox Fruit выдаются автоматически, продавца нужно ждать только для получения кода!
🎁 Фрукты в Blox Fruit выдаются в порядке живой очереди, ты можешь пока что оплатить, но скорее всего придется немного подождать.""",
    
    "PAYMENT_CONFIRMED_MESSAGE": """✅ Спасибо за покупку!

Благодарим за доверие! 🙏

Пожалуйста, оставьте отзыв о нашей работе ❤️
Это поможет нам стать лучше!

Хорошего дня! 😊""",
    
    # --- Ключевые слова для определения системного сообщения FunPay ---
    "PAYMENT_PATTERNS": [
        r"подтвердил успешное выполнение заказа",
        r"подтвердил.*выполнение заказа",
        r"отправил деньги продавцу",
        r"заказ #[A-Z0-9]+",
        r"Покупатель.*подтвердил"
    ],
    
    # --- Как бот определяет первое сообщение ---
    "ORDER_WORDS": ["здравствуйте", "привет", "хочу купить", "заказ", "куплю", "есть", "продаете", "добрый день", "здрасьте"],
    
    # --- Технические настройки ---
    "CHECK_INTERVAL": 15,
    "DEBUG": True
}

# ==========================================
# 2. БАЗА ДАННЫХ
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
            print(f"💳 Оплата подтверждена для {client_name}")
            return True
        return False
    
    def mark_thank_you_sent(self, client_name):
        if client_name in self.data:
            self.data[client_name]["thank_you_sent"] = True
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

# ==========================================
# 3. ОСНОВНОЙ БОТ
# ==========================================
class FunPayBot:
    def __init__(self, config):
        self.config = config
        self.browser = None
        self.page = None
        self.db = ClientDatabase()
    
    async def start(self):
        """Запуск браузера и вход на FunPay"""
        p = await async_playwright().start()
        
        self.browser = await p.chromium.launch(
            headless=not self.config["DEBUG"],
            slow_mo=200,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        self.page = await self.browser.new_page()
        
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        print("🔄 Открываю FunPay...")
        await self.page.goto("https://funpay.com/", timeout=60000)
        
        # Ждем загрузки страницы
        await self.page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        # Пробуем войти
        await self.login()
        
        # Запускаем главный цикл
        await self.main_loop()
    
    async def login(self):
        """Вход на FunPay с обработкой ошибок"""
        try:
            print("🔑 Ищу кнопку входа...")
            
            # Пробуем разные варианты кнопки входа
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
                # Если кнопка не найдена, возможно уже авторизованы
                print("⚠️ Кнопка входа не найдена. Возможно, уже авторизованы.")
                # Проверяем, есть ли кнопка профиля
                profile = await self.page.locator('[class*="profile"], [class*="user"]').count()
                if profile > 0:
                    print("✅ Похоже, уже авторизованы!")
                    return
                else:
                    print("❌ Не удалось найти кнопку входа. Проверьте интернет или сайт.")
                    return
            
            await asyncio.sleep(2)
            
            # Вводим логин и пароль
            print("🔑 Ввожу логин...")
            await self.page.fill('input[name="user[login]"]', self.config["FUNPAY_LOGIN"])
            await asyncio.sleep(1)
            
            print("🔑 Ввожу пароль...")
            await self.page.fill('input[name="user[password]"]', self.config["FUNPAY_PASSWORD"])
            await asyncio.sleep(1)
            
            # Нажимаем кнопку входа
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
            
            # Ждем загрузки после входа
            await asyncio.sleep(5)
            await self.page.wait_for_load_state("networkidle", timeout=30000)
            
            # Проверяем, успешно ли вошли
            try:
                await self.page.locator('[class*="profile"], [class*="user"]').first.wait_for(timeout=10000)
                print("✅ Успешный вход в FunPay!")
            except:
                print("⚠️ Не удалось подтвердить вход. Проверьте логин/пароль.")
                print("📌 Возможно, нужно ввести капчу или подтверждение.")
                
                # Ждем ручного ввода (если нужна капча)
                input("После ручного входа нажмите Enter для продолжения...")
                
        except Exception as e:
            print(f"❌ Ошибка при входе: {e}")
            # Если ошибка, даем возможность войти вручную
            print("📌 Попробуйте войти вручную в открывшемся браузере")
            input("После ручного входа нажмите Enter для продолжения...")
    
    async def get_client_name_from_chat(self):
        """Получает имя клиента из открытого чата"""
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
        """Проверяет, является ли сообщение подтверждением оплаты от FunPay"""
        text = text.lower()
        
        for pattern in self.config["PAYMENT_PATTERNS"]:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    async def check_new_dialogs(self):
        """Проверяет новые диалоги с сообщениями"""
        try:
            await self.page.goto("https://funpay.com/chat/")
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            
            # Ищем диалоги с новыми сообщениями
            dialogs = await self.page.locator('.chat-item:has(.badge)').all()
            
            if not dialogs:
                return
            
            print(f"📩 Найдено {len(dialogs)} диалогов с новыми сообщениями")
            
            for dialog in dialogs:
                try:
                    # Получаем имя клиента
                    client_name = await self._get_client_name_from_dialog(dialog)
                    
                    if not client_name:
                        client_name = "покупатель"
                    
                    # Открываем диалог
                    await dialog.click()
                    await asyncio.sleep(2)
                    
                    # Получаем имя покупателя из чата
                    buyer_name = await self.get_client_name_from_chat()
                    
                    # Читаем все сообщения
                    messages = await self.page.locator('.message-text').all()
                    if not messages:
                        await self.page.goto("https://funpay.com/chat/")
                        continue
                    
                    # Проверяем все сообщения
                    for msg_element in messages:
                        try:
                            msg_text = await msg_element.inner_text()
                            
                            # Проверяем, системное ли это сообщение (от FunPay)
                            is_system = await self._is_system_message(msg_element)
                            
                            # Проверяем, подтверждение ли это оплаты
                            is_payment = await self.is_payment_confirmation_message(msg_text)
                            
                            # Проверяем, от клиента ли сообщение
                            is_from_client = await self._is_message_from_client(msg_element)
                            
                            # Добавляем клиента в базу, если его нет
                            if client_name not in self.db.data:
                                self.db.add_client(client_name, self.page.url)
                            
                            # 1. Если это сообщение от клиента и первое сообщение еще не отправлено
                            if is_from_client and not self.db.is_first_message_sent(client_name):
                                is_order = any(word in msg_text.lower() for word in self.config["ORDER_WORDS"])
                                
                                if is_order:
                                    first_msg = self.config["FIRST_MESSAGE"].format(buyer_name=buyer_name)
                                    await self.send_message(first_msg)
                                    self.db.mark_first_message_sent(client_name)
                                    print(f"📨 Отправлено первое сообщение клиенту {client_name}")
                                    await asyncio.sleep(1)
                            
                            # 2. Если это системное сообщение о подтверждении оплаты
                            if is_system and is_payment:
                                if not self.db.is_thank_you_sent(client_name):
                                    order_match = re.search(r'#[A-Z0-9]+', msg_text)
                                    order_number = order_match.group(0) if order_match else ""
                                    
                                    print(f"💳 Обнаружено подтверждение оплаты! Заказ {order_number}")
                                    print(f"📝 Клиент: {client_name}")
                                    
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
        """Проверяет, является ли сообщение системным (от FunPay)"""
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
        """Получает имя клиента из диалога"""
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
        """Проверяет, отправлено ли сообщение клиентом"""
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
        """Отправляет сообщение в открытый чат"""
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
        """Главный цикл бота"""
        print("\n" + "="*60)
        print("🚀 БОТ ЗАПУЩЕН")
        print("="*60)
        print("📌 Бот отвечает на первое сообщение клиента")
        print("📌 Бот отслеживает системное сообщение FunPay о подтверждении оплаты")
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
                await asyncio.sleep(60)
    
    async def close(self):
        if self.browser:
            await self.browser.close()

# ==========================================
# 4. ЗАПУСК
# ==========================================
async def main():
    bot = FunPayBot(CONFIG)
    try:
        await bot.start()
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
        await bot.close()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
