# Сервер управления дронами

Этот проект представляет собой сервер на Flask и WebSocket для мониторинга и управления устройствами (дронами, станциями).

## Структура проекта

```
drone_server/
├── drone_control_server.py   # Основной код сервера
├── data.json                 # Конфигурация пользователей и устройств
├── requirements.txt          # Зависимости Python
├── README.md                 # Этот файл
├── templates/                # HTML шаблоны
│   ├── login.html
│   └── index.html
└── static/                   # Статические файлы (CSS)
    └── style.css
```

## Установка

1.  **Клонируйте репозиторий**
    ```bash
    git clone <your-repo-url>
    cd drone_server
    ```

2.  **Создайте и активируйте виртуальное окружение**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Для Linux/macOS
    # venv\Scripts\activate   # Для Windows
    ```

3.  **Установите зависимости**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Настройте `data.json`**
    Отредактируйте `data.json`, чтобы добавить своих пользователей и устройства. Пароли пользователей должны быть хэшированы с помощью bcrypt. Пароли устройств хранятся в открытом виде (для простоты).

## Запуск для разработки

Для локального тестирования и разработки можно запустить сервер напрямую:

```bash
python drone_control_server.py
```

Сервер будет доступен по адресу `http://127.0.0.1:5000`.

## Развертывание в продакшен (Production)

В продакшене нельзя использовать встроенный сервер Flask. Рекомендуется использовать WSGI-сервер **Gunicorn** за реверс-прокси **Nginx**.

### Шаг 1: Запуск с помощью Gunicorn

Gunicorn будет управлять процессами вашего Flask-приложения. Мы используем `eventlet` для поддержки WebSocket.

```bash
gunicorn --bind 0.0.0.0:5000 --worker-class eventlet -w 1 drone_control_server:app
```

*   `--bind 0.0.0.0:5000`: Gunicorn будет слушать порт 5000.
*   `--worker-class eventlet`: **Критически важно!** Используем воркер `eventlet` для асинхронной работы.
*   `-w 1`: **Критически важно!** Используем только **один** рабочий процесс. Так как состояние (подключенные клиенты) хранится в памяти одного процесса, масштабирование на несколько воркеров потребует внешнего брокера сообщений (например, Redis). Для десятков устройств одного воркера более чем достаточно.
*   `drone_control_server:app`: Gunicorn ищет объект `app` в файле `drone_control_server.py`.

### Шаг 2: Настройка Nginx в качестве реверс-прокси

Nginx будет принимать внешние запросы и перенаправлять их на нужные порты: HTTP-запросы на Gunicorn, а WebSocket-запросы — на наш WebSocket-сервер.

Создайте файл конфигурации для вашего сайта в Nginx (например, `/etc/nginx/sites-available/drone_server`):

```nginx
server {
    listen 80;
    server_name your_domain.com; # Замените на ваш домен или IP

    # Перенаправляем HTTP запросы на Gunicorn
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # Перенаправляем WebSocket запросы (которые приходят от устройств)
    # Предполагается, что устройства будут подключаться к ws://your_domain.com/ws/
    location /ws/ {
        proxy_pass http://127.0.0.1:8765; # Порт нашего WebSocket-сервера
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
    }
}
```

**Важно:**
1.  Активируйте эту конфигурацию: `sudo ln -s /etc/nginx/sites-available/drone_server /etc/nginx/sites-enabled/`
2.  Проверьте конфигурацию Nginx: `sudo nginx -t`
3.  Перезапустите Nginx: `sudo systemctl restart nginx`
4.  Ваши устройства должны будут подключаться по адресу `ws://your_domain.com/ws/`.

Теперь ваш проект полностью готов к стабильной и производительной работе.
