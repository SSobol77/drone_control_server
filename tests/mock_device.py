import asyncio
import websockets
import json
import random

# --- Настройки мок-устройства ---
DEVICE_NAME = "esp01"
DEVICE_PASSWORD = "1234"
SERVER_URI = "ws://localhost:8765"
# Если используете Nginx, то: "ws://your_domain.com/ws/"

async def run_mock_device():
    """
    Имитирует работу устройства: подключается, аутентифицируется,
    отправляет телеметрию и слушает команды.
    """
    while True:
        try:
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
                
                # Ждем завершения одной из задач (например, если соединение разорвется)
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
        # Здесь может быть логика обработки команды

async def send_telemetry(websocket):
    """Отправляет телеметрию каждые 10 секунд."""
    while True:
        telemetry_payload = {
            "type": "telemetry",
            "status": "idle",
            "battery": round(random.uniform(80.0, 100.0), 2),
            "temperature": round(random.uniform(20.0, 35.0), 2)
        }
        await websocket.send(json.dumps(telemetry_payload))
        print(f"[{DEVICE_NAME}] 📡 Телеметрия отправлена.")
        await asyncio.sleep(10)


if __name__ == "__main__":
    try:
        asyncio.run(run_mock_device())
    except KeyboardInterrupt:
        print(f"\n[{DEVICE_NAME}] Мок-устройство остановлено.")
