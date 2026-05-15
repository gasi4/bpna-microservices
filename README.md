# BPNA Server

Этот репозиторий содержит только микросервисную версию backend-системы БПНА.

## Структура

- `services/api_gateway` — единая входная точка, UI и HTTP/WS proxy
- `services/auth_service` — аутентификация, JWT и пользователи
- `services/telemetry_service` — телеметрия, история и экспорт
- `services/device_service` — WebSocket-канал устройства, видеопоток и состояние борта
- `services/control_service` — команды оператора и логика управления
- `services/wifi_service` — Wi-Fi измерения, heatmap и сканирование
- `services/detection_service` — YOLO-детекция объектов
- `static` — frontend-панель управления
- `tests` — локальные эмуляторы и вспомогательные тестовые скрипты

## Локальный запуск

```powershell
cd C:\Users\ilyha\OneDrive\Desktop\server
docker compose -f docker-compose.microservices.yml up --build
```

Для фонового запуска:

```powershell
docker compose -f docker-compose.microservices.yml up -d
```

## Точки входа

- UI и API gateway: `http://localhost:8000`
- Auth service: `http://localhost:8001/docs`
- Telemetry service: `http://localhost:8002/docs`
- Device service: `http://localhost:8003/docs`
- Control service: `http://localhost:8004/docs`
- Wi-Fi service: `http://localhost:8005/docs`
- Detection service: `http://localhost:8006/docs`

## Логин по умолчанию

```text
operator / operator123
```
