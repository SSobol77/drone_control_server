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
