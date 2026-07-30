async def _get_message_id(self, message_element, debug=False):
    """
    Получает уникальный идентификатор сообщения.
    Приоритет: data-id -> id -> msg-* в классах -> хеш из HTML
    """
    try:
        # 1. Пробуем data-id
        msg_id = await message_element.get_attribute('data-id')
        if msg_id:
            if debug:
                print(f"✅ Найден data-id: {msg_id}")
            return f"dataid_{msg_id}"
        
        # 2. Пробуем id
        msg_id = await message_element.get_attribute('id')
        if msg_id:
            if debug:
                print(f"✅ Найден id: {msg_id}")
            return f"id_{msg_id}"
        
        # 3. Пробуем найти в классах (msg-12345)
        classes = await message_element.get_attribute('class') or ""
        match = re.search(r'msg-(\d+)', classes)
        if match:
            if debug:
                print(f"✅ Найден msg-* в классах: {match.group(1)}")
            return f"class_{match.group(1)}"
        
        # 4. Запасной вариант: хеш из HTML + автор
        if debug:
            print("⚠️ ID не найден, создаю хеш...")
        
        # Определяем автора
        author = "client"
        if "out" in classes:
            author = "me"
        elif "in" in classes:
            author = "client"
        
        # Получаем полный HTML сообщения
        html = await message_element.evaluate("el => el.outerHTML")
        
        # Получаем время (если есть)
        time_elem = await message_element.locator('.time, .message-time, [class*="time"]').first
        time_text = ""
        if await time_elem.count() > 0:
            time_text = await time_elem.text_content() or ""
        
        # Создаем хеш
        import hashlib
        content = f"{author}|{html}|{time_text}"
        hash_id = hashlib.md5(content.encode('utf-8')).hexdigest()[:16]
        
        if debug:
            print(f"🔑 Создан хеш ID: {hash_id} (автор: {author})")
        
        return f"hash_{hash_id}"
        
    except Exception as e:
        print(f"⚠️ Ошибка получения ID: {e}")
        return None
