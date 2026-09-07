# Управление Cookies (Cookies Management)

## 1. Зачем нужны cookies
Платформы Instagram, Facebook и TikTok агрессивно блокируют автоматические запросы к медиа без авторизованной сессии (`Instagram sent an empty media response`, HTTP 429, Login Wall).
В пайплайне `SeedIntake` все загрузчики (`yt-dlp`, `gallery-dl`, `instaloader`) настроены на чтение cookies с первого запроса.

## 2. Размещение файлов
Cookies хранятся в корневой папке `.cookies/`:
- `.cookies/instagram.txt` — cookies Instagram (формат Netscape HTTP Cookie File)
- `.cookies/facebook.txt` — cookies Facebook
- `.cookies/tiktok.txt` — cookies TikTok

> ⚠️ Папка `.cookies/` включена в `.gitignore` и никогда не должна коммититься в git!

## 3. Экспорт и обновление cookies
1. Установите расширение для браузера (например, *Get cookies.txt LOCALLY* для Chrome/Firefox).
2. Авторизуйтесь в соответствующей соцсети в браузере.
3. Экспортируйте cookies в формате Netscape в соответствующий файл в `.cookies/`.
4. Убедитесь, что файл содержит актуальные параметры сессии (например, `sessionid` для Instagram).

## 4. Поведение при ошибках cookies
Если контент упёрся в экран логина или cookies протухли:
- **КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО** маскировать это под «видео без содержания» или ставить статус `processed`!
- Не ходить по кругу и не тратить токены на повторные попытки.
- Прямо сообщить пользователю:
  > *"Cookies для [платформы] устарели или отсутствуют. Пожалуйста, обнови/сохрани cookies в `.cookies/<платформа>.txt`."*
- Остановиться и ждать, пока пользователь предоставит обновлённые cookies.
