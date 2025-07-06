## Руководство по установке и запуску сервера управления дронами

### Введение

Это руководство поможет вам развернуть и запустить сервер управления дронами на чистом сервере с операционной системой Ubuntu. Мы пройдем все шаги: от создания структуры проекта до настройки веб-сервера Nginx для работы в производственном режиме и финального тестирования.

### Предварительные требования

*   Сервер с установленной **Ubuntu 20.04 / 22.04**.
*   Доступ к серверу по SSH с правами `sudo`.
*   Базовые навыки работы в командной строке Linux.
*   IP-адрес вашего сервера. В инструкциях мы будем использовать заполнитель `<your_server_ip>`.

---

### Раздел 1: Настройка структуры проекта

Сначала мы создадим все необходимые каталоги и файлы.

#### Шаг 1.1: Создание корневого каталога проекта

Подключитесь к вашему серверу по SSH и выполните следующие команды, чтобы создать основной каталог для проекта.

```bash
# Создаем каталог проекта в домашней директории пользователя
cd ~
mkdir drone_server

# Переходим в созданный каталог
cd drone_server
```

#### Шаг 1.2: Создание дерева каталогов и файлов

Теперь, находясь в каталоге `drone_server`, создадим все необходимые подкаталоги и пустые файлы.

```bash
# Создаем подкаталоги
mkdir templates
mkdir static
mkdir tests

# Создаем пустые файлы
touch drone_control_server.py
touch data.json
touch requirements.txt
touch README.md
touch templates/login.html
touch templates/index.html
touch static/style.css
touch tests/mock_device.py
```

После выполнения этих команд структура вашего проекта будет выглядеть так:

```
drone_server/
├── drone_control_server.py
├── data.json
├── requirements.txt
├── README.md
├── templates/
│   ├── login.html
│   └── index.html
├── static/
│   └── style.css
└── tests/
    └── mock_device.py
```

#### Шаг 1.3: Заполнение файлов содержимым

Теперь вам нужно скопировать и вставить код в каждый из созданных файлов. Используйте текстовый редактор, например `nano`, для редактирования файлов на сервере.

**Пример редактирования файла `drone_control_server.py`:**
```bash
nano drone_control_server.py
```
Вставьте в него код, затем нажмите `Ctrl+X`, потом `Y` и `Enter`, чтобы сохранить и выйти. Повторите эту процедуру для всех файлов ниже.

<details>
<summary><strong>1. `drone_control_server.py` (Нажмите, чтобы развернуть код)</strong></summary>

```python
"""
drone_control_server.py (Production-Ready Version)

Сервер управления боксами и станциями дронов.
Основные улучшения:
- Управление состоянием в памяти для высокой производительности (DeviceManager).
- Потокобезопасность с использованием threading.Lock.
- Корректная интеграция Flask (sync) и WebSocket (async).
- API-эндпоинты для динамического фронтенда.
- Конфигурация вынесена для удобства развертывания.
"""
import os
import bcrypt
import asyncio
import threading
import json
import websockets
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin

# --- Конфигурация ---
# В продакшене лучше использовать переменные окружения
SECRET_KEY = os.environ.get('SECRET_KEY', 'supersecretkey-for-dev')
DATA_FILE = 'data.json'
WS_HOST = '0.0.0.0'
WS_PORT = 8765
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 5000

# --- Инициализация Flask ---
app = Flask(__name__)
app.secret_key = SECRET_KEY

# --- Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- Потокобезопасный менеджер состояний ---
class DeviceManager:
    """
    Класс для управления состоянием устройств в памяти. Потокобезопасен.
    """
    def __init__(self, device_config):
        self.lock = threading.Lock()
        # Статическая информация об устройствах (имя, пароль)
        self.devices_config = {d['name']: d for d in device_config}
        # Динамическое состояние (статус, телеметрия, websocket-соединение)
        self.clients = {}
        self.last_telemetry = {}
        self.statuses = {name: "offline" for name in self.devices_config}

    def get_device_config(self, name):
        return self.devices_config.get(name)

    def get_all_statuses(self):
        with self.lock:
            return list(self.statuses.items())

    def get_full_device_data(self):
        with self.lock:
            # Возвращает полные данные для API
            data = []
            for name, config in self.devices_config.items():
                device_data = config.copy()
                device_data['status'] = self.statuses.get(name, "offline")
                data.append(device_data)
            return data

    def set_online(self, name, websocket):
        with self.lock:
            self.clients[name] = websocket
            self.statuses[name] = "online"
        print(f"✅ Устройство {name} подключилось")

    def set_offline(self, name):
        with self.lock:
            self.clients.pop(name, None)
            self.statuses[name] = "offline"
        print(f"❌ Устройство {name} отключилось")

    def update_telemetry(self, name, telemetry_data):
        with self.lock:
            self.last_telemetry[name] = telemetry_data
            if 'status' in telemetry_data:
                self.statuses[name] = telemetry_data['status']
        print(f"📡 Телеметрия от {name}: {telemetry_data.get('status', 'unknown')}")

    def get_telemetry(self, name):
        with self.lock:
            return self.last_telemetry.get(name, {"error": "no data for this device"})

    def get_websocket(self, name):
        with self.lock:
            return self.clients.get(name)

# --- Глобальные переменные для взаимодействия потоков ---
# Загружаем конфигурацию один раз при старте
try:
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        initial_data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"CRITICAL ERROR: Cannot load or parse {DATA_FILE}: {e}")
    exit(1)

device_manager = DeviceManager(initial_data['devices'])
users_data = {u['username']: u for u in initial_data['users']}
users_by_id = {str(u['id']): u for u in initial_data['users']}

# Цикл событий asyncio для WebSocket сервера
websocket_event_loop = None

# --- Модель пользователя ---
class User(UserMixin):
    def __init__(self, id_, username):
        self.id = id_
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    user_info = users_by_id.get(user_id)
    return User(user_info['id'], user_info['username']) if user_info else None

# --- Аутентификация ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password'].encode('utf-8')
        user_info = users_data.get(username)

        if user_info and bcrypt.checkpw(password, user_info['password_hash'].encode('utf-8')):
            login_user(User(user_info['id'], username))
            return redirect(url_for('index'))

        flash("Неверный логин или пароль", "error")
        return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- Веб-интерфейс (HTML) ---
@app.route('/')
@login_required
def index():
    return render_template('index.html', username=current_user.username)

# --- API эндпоинты (JSON) ---
@app.route('/api/devices', methods=['GET'])
@login_required
def get_devices_status():
    """Возвращает JSON со списком всех устройств и их статусом."""
    return jsonify(device_manager.get_full_device_data())

@app.route('/api/telemetry', methods=['GET'])
@login_required
def get_telemetry():
    """Возвращает последнюю телеметрию для указанного устройства."""
    device_name = request.args.get('device')
    if not device_name:
        return jsonify({"error": "device name is required"}), 400
    return jsonify(device_manager.get_telemetry(device_name))

@app.route('/api/send_command', methods=['POST'])
@login_required
def send_command_api():
    """Принимает команду и отправляет ее устройству через WebSocket."""
    data = request.json
    name = data.get('device_name')
    command = data.get('command')
    value = data.get('value', None)

    if not name or not command:
        return jsonify({"status": "error", "message": "Заполните обязательные поля"}), 400

    try:
        # Корректно вызываем async функцию из sync контекста Flask
        future = asyncio.run_coroutine_threadsafe(
            send_command_to_device(name, command, value),
            websocket_event_loop
        )
        # Ждем результат (опционально, но хорошо для обратной связи)
        success = future.get(timeout=5)

        if success:
            return jsonify({"status": "ok", "message": f"Команда '{command}' отправлена устройству {name}"})
        else:
            return jsonify({"status": "error", "message": f"Устройство {name} не в сети или не найдено"}), 404

    except Exception as e:
        print(f"Ошибка при отправке команды: {e}")
        return jsonify({"status": "error", "message": f"Ошибка сервера: {str(e)}"}), 500

# --- WebSocket-сервер ---
async def ws_handler(websocket):
    """Обрабатывает подключения устройств через WebSocket."""
    device_name = None
    try:
        auth_message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
        auth_data = json.loads(auth_message)

        if auth_data.get('type') != 'auth':
            await websocket.send(json.dumps({"error": "auth_required"}))
            return

        device_name = auth_data.get('name')
        password = auth_data.get('password')
        device_config = device_manager.get_device_config(device_name)

        if not device_config or device_config['password'] != password:
            await websocket.send(json.dumps({"error": "unauthorized"}))
            return

        device_manager.set_online(device_name, websocket)
        await websocket.send(json.dumps({"status": "ok", "message": "authenticated"}))

        async for message in websocket:
            data = json.loads(message)
            if data.get('type') == 'telemetry':
                device_manager.update_telemetry(device_name, data)

    except (websockets.exceptions.ConnectionClosed, asyncio.TimeoutError, json.JSONDecodeError) as e:
        print(f"Соединение с {device_name or 'unknown device'} закрыто: {type(e).__name__}")
    finally:
        if device_name:
            device_manager.set_offline(device_name)

async def send_command_to_device(name, command, value=None):
    """Асинхронно отправляет команду подключенному устройству."""
    ws = device_manager.get_websocket(name)
    if not ws:
        return False

    cmd_payload = {"command": command}
    if value is not None:
        cmd_payload["value"] = str(value)

    await ws.send(json.dumps(cmd_payload))
    return True

def start_websocket_server():
    """Запускает WebSocket сервер в отдельном потоке."""
    global websocket_event_loop
    # Создаем и сохраняем event loop для этого потока
    websocket_event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(websocket_event_loop)

    server = websockets.serve(ws_handler, WS_HOST, WS_PORT)
    websocket_event_loop.run_until_complete(server)
    websocket_event_loop.run_forever()

# --- Точка входа ---
if __name__ == '__main__':
    # Запускаем WebSocket сервер в фоновом потоке
    ws_thread = threading.Thread(target=start_websocket_server, daemon=True)
    ws_thread.start()

    # Запускаем Flask сервер (для разработки)
    # В продакшене используйте Gunicorn: gunicorn --worker-class eventlet -w 1 drone_control_server:app
    print(f"Flask-сервер запущен на http://{FLASK_HOST}:{FLASK_PORT}")
    print(f"WebSocket-сервер запущен на ws://{WS_HOST}:{WS_PORT}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=True)
```
</details>

<details>
<summary><strong>2. `data.json`</strong></summary>

```json
{
  "users": [
    {
      "id": 1,
      "username": "admin",
      "password_hash": "$2b$12$Uqz1pRUOVsNujHjYoMvq4eEuLVov8RtJY7KBLQkFZC84yi/ZegvSa"
    },
    {
      "id": 2,
      "username": "operator",
      "password_hash": "$2b$12$37NqNQExqUSOKRgyv5TqxORL6vKHeCTtIxlwEu5We.9W8zjOBUuVe"
    }
  ],
  "devices": [
    {
      "name": "esp01",
      "type": "box",
      "password": "1234",
      "status": "offline"
    },
    {
      "name": "esp02",
      "type": "station",
      "password": "5678",
      "status": "offline"
    },
    {
      "name": "esp03",
      "type": "box",
      "password": "abcd",
      "status": "offline"
    }
  ]
}
```
</details>

<details>
<summary><strong>3. `requirements.txt`</strong></summary>

```txt
Flask
Flask-Login
bcrypt
websockets
eventlet
gunicorn
```
</details>

<details>
<summary><strong>4. `templates/login.html`</strong></summary>

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Вход в систему</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
    <div class="container mt-5">
        <div class="row justify-content-center">
            <div class="col-md-6 col-lg-4">
                <div class="card">
                    <div class="card-header">
                        <h3 class="text-center">Сервер управления дронами</h3>
                    </div>
                    <div class="card-body">
                        <h4 class="card-title text-center mb-4">Авторизация</h4>
                        
                        {% with messages = get_flashed_messages(with_categories=true) %}
                          {% if messages %}
                            {% for category, message in messages %}
                              <div class="alert alert-danger" role="alert">
                                {{ message }}
                              </div>
                            {% endfor %}
                          {% endif %}
                        {% endwith %}

                        <form method="POST" action="{{ url_for('login') }}">
                            <div class="mb-3">
                                <label for="username" class="form-label">Имя пользователя</label>
                                <input type="text" class="form-control" id="username" name="username" required>
                            </div>
                            <div class="mb-3">
                                <label for="password" class="form-label">Пароль</label>
                                <input type="password" class="form-control" id="password" name="password" required>
                            </div>
                            <div class="d-grid">
                                <button type="submit" class="btn btn-primary">Войти</button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
```
</details>

<details>
<summary><strong>5. `templates/index.html`</strong></summary>

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Панель управления</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="#">Панель управления</a>
            <div class="d-flex">
                <span class="navbar-text me-3">Пользователь: <strong>{{ username }}</strong></span>
                <a href="{{ url_for('logout') }}" class="btn btn-outline-light">Выйти</a>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="row">
            <!-- Список устройств -->
            <div class="col-md-7">
                <h3>Устройства</h3>
                <div id="devices-list" class="list-group">
                    <!-- Устройства будут загружены сюда через JS -->
                    <div class="text-center p-5"><div class="spinner-border" role="status"></div></div>
                </div>
            </div>

            <!-- Отправка команд -->
            <div class="col-md-5">
                <h3>Отправить команду</h3>
                <div class="card">
                    <div class="card-body">
                        <form id="command-form">
                            <div class="mb-3">
                                <label for="device-select" class="form-label">Имя устройства</label>
                                <select id="device-select" class="form-select" required></select>
                            </div>
                            <div class="mb-3">
                                <label for="command-input" class="form-label">Команда</label>
                                <input type="text" class="form-control" id="command-input" placeholder="например, open_cover" required>
                            </div>
                            <div class="mb-3">
                                <label for="value-input" class="form-label">Значение (опционально)</label>
                                <input type="text" class="form-control" id="value-input" placeholder="например, 1">
                            </div>
                            <button type="submit" class="btn btn-primary w-100">Отправить</button>
                        </form>
                        <div id="command-result" class="mt-3"></div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Модальное окно для телеметрии -->
        <div class="modal fade" id="telemetryModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title" id="telemetryModalLabel">Телеметрия</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <pre><code id="telemetry-content">Загрузка...</code></pre>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        const devicesList = document.getElementById('devices-list');
        const deviceSelect = document.getElementById('device-select');
        const commandForm = document.getElementById('command-form');
        const commandResult = document.getElementById('command-result');
        const telemetryModal = new bootstrap.Modal(document.getElementById('telemetryModal'));
        const telemetryContent = document.getElementById('telemetry-content');
        const telemetryModalLabel = document.getElementById('telemetryModalLabel');

        // Функция для обновления списка устройств
        async function updateDeviceList() {
            try {
                const response = await fetch('/api/devices');
                const devices = await response.json();

                devicesList.innerHTML = ''; // Очистить список
                const selectedDevice = deviceSelect.value;
                deviceSelect.innerHTML = ''; // Очистить селектор

                if (devices.length === 0) {
                    devicesList.innerHTML = '<p class="text-muted">Устройства не найдены.</p>';
                }

                devices.forEach(device => {
                    // Обновляем список устройств
                    const statusClass = device.status === 'online' ? 'success' : (device.status === 'offline' ? 'danger' : 'warning');
                    const statusText = device.status;
                    const deviceElement = `
                        <div class="list-group-item list-group-item-action d-flex justify-content-between align-items-center">
                            <div>
                                <h5 class="mb-1">${device.name} <span class="badge bg-secondary">${device.type}</span></h5>
                                <p class="mb-1">Статус: <span class="status-indicator bg-${statusClass}"></span> ${statusText}</p>
                            </div>
                            <button class="btn btn-sm btn-info" onclick="showTelemetry('${device.name}')" ${!['online', 'idle', 'charging'].includes(device.status) ? 'disabled' : ''}>
                                Телеметрия
                            </button>
                        </div>
                    `;
                    devicesList.insertAdjacentHTML('beforeend', deviceElement);

                    // Обновляем селектор для отправки команд
                    const optionElement = `<option value="${device.name}" ${device.name === selectedDevice ? 'selected' : ''}>${device.name}</option>`;
                    deviceSelect.insertAdjacentHTML('beforeend', optionElement);
                });
            } catch (error) {
                console.error("Ошибка при обновлении списка устройств:", error);
                devicesList.innerHTML = '<p class="text-danger">Не удалось загрузить список устройств.</p>';
            }
        }

        // Функция для отображения телеметрии
        async function showTelemetry(deviceName) {
            telemetryModalLabel.innerText = `Телеметрия для: ${deviceName}`;
            telemetryContent.innerText = 'Загрузка...';
            telemetryModal.show();
            try {
                const response = await fetch(`/api/telemetry?device=${deviceName}`);
                const data = await response.json();
                telemetryContent.innerText = JSON.stringify(data, null, 2);
            } catch (error) {
                telemetryContent.innerText = 'Ошибка при загрузке телеметрии.';
            }
        }

        // Обработчик отправки команды
        commandForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const deviceName = document.getElementById('device-select').value;
            const command = document.getElementById('command-input').value;
            const value = document.getElementById('value-input').value;

            commandResult.innerHTML = `<div class="spinner-border spinner-border-sm" role="status"></div> Отправка...`;

            try {
                const payload = {
                    device_name: deviceName,
                    command: command,
                };
                if (value) {
                    payload.value = value;
                }

                const response = await fetch('/api/send_command', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                const result = await response.json();

                if (response.ok) {
                    commandResult.innerHTML = `<div class="alert alert-success">${result.message}</div>`;
                } else {
                    commandResult.innerHTML = `<div class="alert alert-danger">${result.message}</div>`;
                }
            } catch (error) {
                commandResult.innerHTML = `<div class="alert alert-danger">Сетевая ошибка при отправке команды.</div>`;
            }
            // Очищаем сообщение через 5 секунд
            setTimeout(() => { commandResult.innerHTML = ''; }, 5000);
        });

        // Первоначальная загрузка и периодическое обновление
        document.addEventListener('DOMContentLoaded', () => {
            updateDeviceList();
            setInterval(updateDeviceList, 3000); // Обновлять каждые 3 секунды
        });
    </script>
</body>
</html>
```
</details>

<details>
<summary><strong>6. `static/style.css`</strong></summary>

```css
.status-indicator {
    display: inline-block;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    margin-right: 5px;
    vertical-align: middle;
}

#telemetry-content {
    background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    padding: 1rem;
    border-radius: .25rem;
    max-height: 60vh;
    overflow-y: auto;
}
```
</details>

<details>
<summary><strong>7. `tests/mock_device.py`</strong></summary>

```python
import asyncio
import websockets
import json
import random

# --- Настройки мок-устройства ---
DEVICE_NAME = "esp01"
DEVICE_PASSWORD = "1234"
SERVER_URI = "ws://localhost:8765" # Для локального теста. При тесте с Nginx замените на "ws://<your_server_ip>/ws/"

async def run_mock_device():
    """
    Имитирует работу устройства: подключается, аутентифицируется,
    отправляет телеметрию и слушает команды.
    """
    while True:
        try:
            # Для подключения через Nginx используйте `websockets.connect(SERVER_URI, subprotocols=['websocket'])`
            async with websockets.connect(SERVER_URI) as websocket:
                print(f"[{DEVICE_NAME}] Пытаюсь подключиться к {SERVER_URI}...")
                
                # 1. Аутентификация
                auth_payload = {
                    "type": "auth",
                    "name": DEVICE_NAME,
                    "password": DEVICE_PASSWORD
                }
                await websocket.send(json.dumps(auth_payload))
                
                response = await websocket.recv()
                response_data = json.loads(response)
                if response_data.get("status") != "ok":
                    print(f"[{DEVICE_NAME}] Аутентификация не удалась: {response_data.get('message')}")
                    return

                print(f"[{DEVICE_NAME}] ✅ Аутентификация пройдена успешно!")

                # 2. Параллельно отправляем телеметрию и слушаем команды
                consumer_task = asyncio.create_task(listen_for_commands(websocket))
                producer_task = asyncio.create_task(send_telemetry(websocket))
                
                done, pending = await asyncio.wait(
                    [consumer_task, producer_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                
                for task in pending:
                    task.cancel()

        except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError) as e:
            print(f"[{DEVICE_NAME}] ❌ Соединение потеряно или не установлено: {e}. Повторная попытка через 5 секунд...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[{DEVICE_NAME}] Произошла непредвиденная ошибка: {e}")
            await asyncio.sleep(5)


async def listen_for_commands(websocket):
    """Слушает входящие команды от сервера."""
    async for message in websocket:
        command = json.loads(message)
        print(f"[{DEVICE_NAME}] 📩 Получена команда: {command}")

async def send_telemetry(websocket):
    """Отправляет телеметрию каждые 10 секунд."""
    statuses = ["idle", "charging", "flying"]
    while True:
        telemetry_payload = {
            "type": "telemetry",
            "status": random.choice(statuses),
            "battery": round(random.uniform(80.0, 100.0), 2),
            "temperature": round(random.uniform(20.0, 35.0), 2)
        }
        await websocket.send(json.dumps(telemetry_payload))
        print(f"[{DEVICE_NAME}] 📡 Телеметрия отправлена: {telemetry_payload}")
        await asyncio.sleep(10)


if __name__ == "__main__":
    try:
        asyncio.run(run_mock_device())
    except KeyboardInterrupt:
        print(f"\n[{DEVICE_NAME}] Мок-устройство остановлено.")

```
</details>

---

### Раздел 2: Настройка окружения Python

#### Шаг 2.1: Установка Python и Venv

```bash
sudo apt update
sudo apt install python3-pip python3-venv -y
```

#### Шаг 2.2: Создание и активация виртуального окружения

Находясь в каталоге `~/drone_server`, создадим изолированное окружение.

```bash
# Создаем окружение в папке venv
python3 -m venv venv

# Активируем его
source venv/bin/activate
```
После активации в начале вашей командной строки появится `(venv)`.

#### Шаг 2.3: Установка зависимостей

Теперь установим все необходимые Python-библиотеки из файла `requirements.txt`.

```bash
pip install -r requirements.txt
```

---

### Раздел 3: Настройка Nginx и Gunicorn

Мы будем использовать Gunicorn для запуска нашего приложения и Nginx как реверс-прокси, который будет принимать внешние запросы и направлять их на нужные сервисы.

#### Шаг 3.1: Установка Nginx

```bash
sudo apt install nginx -y
```

#### Шаг 3.2: Настройка Nginx

1.  Создадим файл конфигурации для нашего сайта:
    ```bash
    sudo nano /etc/nginx/sites-available/drone_server
    ```

2.  Вставьте в этот файл следующую конфигурацию. **Обязательно замените `<your_server_ip>` на реальный IP-адрес вашего сервера.**

    ```nginx
    server {
        listen 80;
        server_name <your_server_ip>; # <-- ЗАМЕНИТЕ НА ВАШ IP

        # Перенаправляем HTTP-запросы (веб-интерфейс) на Gunicorn (порт 5000)
        location / {
            proxy_pass http://127.0.0.1:5000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }

        # Перенаправляем WebSocket-запросы (от устройств) на наш WS-сервер (порт 8765)
        # Устройства должны будут подключаться к ws://<your_server_ip>/ws/
        location /ws/ {
            proxy_pass http://127.0.0.1:8765;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "Upgrade";
            proxy_set_header Host $host;
        }
    }
    ```

3.  Активируем нашу конфигурацию, создав символическую ссылку:
    ```bash
    sudo ln -s /etc/nginx/sites-available/drone_server /etc/nginx/sites-enabled/
    ```

4.  Проверим синтаксис конфигурации Nginx:
    ```bash
    sudo nginx -t
    ```
    Ожидаемый результат: `nginx: configuration file /etc/nginx/nginx.conf test is successful`.

5.  Перезапускаем Nginx для применения изменений:
    ```bash
    sudo systemctl restart nginx
    ```

---

### Раздел 4: Запуск приложения

#### Шаг 4.1: Запуск Gunicorn

Убедитесь, что вы находитесь в директории `~/drone_server` и ваше виртуальное окружение `(venv)` активно. Запустите Gunicorn:

```bash
gunicorn --bind 0.0.0.0:5000 --worker-class eventlet -w 1 drone_control_server:app
```

**Ожидаемый результат в терминале:**
Вы увидите несколько строк, сообщающих о запуске Gunicorn, включая:
```
[INFO] Starting gunicorn ...
[INFO] Listening at: http://0.0.0.0:5000 ...
[INFO] Using worker: eventlet
[INFO] Booting worker with pid: ...
Flask-сервер запущен на http://0.0.0.0:5000
WebSocket-сервер запущен на ws://0.0.0.0:8765
```
**Не закрывайте этот терминал!** Сервер работает, пока запущена эта команда.

---

### Раздел 5: Тестирование системы

Для тестирования нам понадобятся **два терминала**, подключенных к серверу.

*   **Терминал 1:** Gunicorn уже запущен и работает.
*   **Терминал 2:** Мы будем использовать его для запуска имитатора устройства.

#### Шаг 5.1: Запуск имитатора устройства

1.  Откройте **второй терминал** и подключитесь к серверу по SSH.
2.  Перейдите в каталог проекта и активируйте виртуальное окружение:
    ```bash
    cd ~/drone_server
    source venv/bin/activate
    ```
3.  **Важно!** Отредактируйте файл `tests/mock_device.py`, чтобы он подключался через Nginx.
    ```bash
    nano tests/mock_device.py
    ```
    Найдите строку `SERVER_URI = "ws://localhost:8765"` и измените ее на:
    ```python
    SERVER_URI = "ws://<your_server_ip>/ws/" # <-- ЗАМЕНИТЕ НА ВАШ IP
    ```
    Сохраните файл.

4.  Запустите имитатор:
    ```bash
    python tests/mock_device.py
    ```

**Ожидаемый результат в Терминале 2:**
```
[esp01] Пытаюсь подключиться к ws://<your_server_ip>/ws/...
[esp01] ✅ Аутентификация пройдена успешно!
[esp01] 📡 Телеметрия отправлена: {'type': 'telemetry', 'status': 'idle', ...}
```
**Ожидаемый результат в Терминале 1:**
```
✅ Устройство esp01 подключилось
📡 Телеметрия от esp01: idle
```

#### Шаг 5.2: Проверка веб-интерфейса

1.  Откройте веб-браузер на своем компьютере и перейдите по адресу:
    `http://<your_server_ip>`

2.  Вы увидите страницу входа. Используйте данные из `data.json`:
    *   **Логин:** `admin`
    *   **Пароль:** `admin`

3.  **Ожидаемый результат:** Вы вошли в систему и видите панель управления. В списке устройств `esp01` должен иметь **зеленый индикатор** и статус, который присылает имитатор (например, `idle` или `charging`). Другие устройства будут `offline`.

#### Шаг 5.3: Отправка команды

1.  На панели управления в форме "Отправить команду" выберите `esp01`.
2.  В поле "Команда" введите `test_command`.
3.  Нажмите кнопку "Отправить".

**Ожидаемый результат в браузере:** Появится зеленое уведомление "Команда 'test_command' отправлена устройству esp01".

**Ожидаемый результат в Терминале 2 (где работает имитатор):**
```
[esp01] 📩 Получена команда: {'command': 'test_command'}
```

#### Шаг 5.4: Проверка отключения

1.  Вернитесь в **Терминал 2**.
2.  Остановите имитатор устройства, нажав `Ctrl+C`.

**Ожидаемый результат в Терминале 1 (Gunicorn):**
```
❌ Устройство esp01 отключилось
```

**Ожидаемый результат в браузере:** Через несколько секунд (до 3-х) статус устройства `esp01` на панели управления изменится на `offline` с **красным индикатором**.

---

**Поздравляем!** Вы успешно развернули, настроили и протестировали сервер управления дронами.
