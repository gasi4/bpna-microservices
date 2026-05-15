# Railway Deployment Guide

Этот проект разворачивается на Railway как набор отдельных сервисов из одного репозитория.

## Что уже есть

- `Postgres` можно использовать как основную базу данных.
- `Redis` в текущей версии backend не обязателен. Его можно оставить или удалить позже.

## Общая схема на Railway

Нужны отдельные сервисы:

- `api-gateway`
- `auth-service`
- `telemetry-service`
- `device-service`
- `control-service`
- `wifi-service`
- `detection-service`

## Важный момент про gateway

`api-gateway` должен собираться из корня репозитория, потому что ему нужен каталог `static`.
Для него используется файл `Railway.api-gateway.Dockerfile`.

## Шаг 1. Настрой существующий сервис `bpna` как gateway

В Railway:

1. Открой сервис `bpna`.
2. Переименуй его в `api-gateway`.
3. Source Repo оставь тот же GitHub-репозиторий.
4. Root Directory оставь `/`.
5. В Variables добавь:

```text
RAILWAY_DOCKERFILE_PATH=Railway.api-gateway.Dockerfile
PORT=8000
AUTH_SERVICE_URL=http://${{auth-service.RAILWAY_PRIVATE_DOMAIN}}:8000
TELEMETRY_SERVICE_URL=http://${{telemetry-service.RAILWAY_PRIVATE_DOMAIN}}:8000
CONTROL_SERVICE_URL=http://${{control-service.RAILWAY_PRIVATE_DOMAIN}}:8000
WIFI_SERVICE_URL=http://${{wifi-service.RAILWAY_PRIVATE_DOMAIN}}:8000
DEVICE_WS_URL=ws://${{device-service.RAILWAY_PRIVATE_DOMAIN}}:8000
WIFI_WS_URL=ws://${{wifi-service.RAILWAY_PRIVATE_DOMAIN}}:8000
```

## Шаг 2. Создай остальные сервисы из того же репозитория

Для каждого нового сервиса:

1. `New` -> `Service` -> `GitHub Repo`
2. Выбери тот же репозиторий
3. Укажи Root Directory
4. Добавь переменные

### `auth-service`

Root Directory:

```text
/services/auth_service
```

Variables:

```text
PORT=8000
DATABASE_URL=${{Postgres.DATABASE_URL}}
SECRET_KEY=change-this-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

### `telemetry-service`

Root Directory:

```text
/services/telemetry_service
```

Variables:

```text
PORT=8000
DATABASE_URL=${{Postgres.DATABASE_URL}}
AUTH_SERVICE_URL=http://${{auth-service.RAILWAY_PRIVATE_DOMAIN}}:8000
```

### `device-service`

Root Directory:

```text
/services/device_service
```

Variables:

```text
PORT=8000
DEVICE_SECRET=change-me-device
AUTH_SERVICE_URL=http://${{auth-service.RAILWAY_PRIVATE_DOMAIN}}:8000
TELEMETRY_SERVICE_URL=http://${{telemetry-service.RAILWAY_PRIVATE_DOMAIN}}:8000
WIFI_SERVICE_URL=http://${{wifi-service.RAILWAY_PRIVATE_DOMAIN}}:8000
DETECTION_SERVICE_URL=http://${{detection-service.RAILWAY_PRIVATE_DOMAIN}}:8000
```

### `control-service`

Root Directory:

```text
/services/control_service
```

Variables:

```text
PORT=8000
AUTH_SERVICE_URL=http://${{auth-service.RAILWAY_PRIVATE_DOMAIN}}:8000
DEVICE_SERVICE_URL=http://${{device-service.RAILWAY_PRIVATE_DOMAIN}}:8000
```

### `wifi-service`

Root Directory:

```text
/services/wifi_service
```

Variables:

```text
PORT=8000
DATABASE_URL=${{Postgres.DATABASE_URL}}
AUTH_SERVICE_URL=http://${{auth-service.RAILWAY_PRIVATE_DOMAIN}}:8000
DEVICE_SERVICE_URL=http://${{device-service.RAILWAY_PRIVATE_DOMAIN}}:8000
```

### `detection-service`

Root Directory:

```text
/services/detection_service
```

Variables:

```text
PORT=8000
YOLO_MODEL_PATH=yolo11s.pt
```

Примечание: модель будет скачана/подготовлена самим сервисом при первом использовании, если файла нет в образе.

## Шаг 3. Public domain

Публичный домен нужен только для `api-gateway`.
Остальные сервисы могут остаться без публичных доменов и общаться через private network.

## Шаг 4. Что проверить после деплоя

Открой:

- `https://<api-gateway-domain>/health`
- `https://<api-gateway-domain>/`

Дальше проверь:

- логин `operator / operator123`
- подключение эмулятора к `/ws/esp`
- загрузку UI
- `/docs` у отдельных сервисов при необходимости

## Если сервис не поднялся

Проверь:

- правильный Root Directory
- правильный `PORT=8000`
- наличие `RAILWAY_DOCKERFILE_PATH=Railway.api-gateway.Dockerfile` у gateway
- ссылки на private domain через `${{service.RAILWAY_PRIVATE_DOMAIN}}`
- что `DATABASE_URL` берется из `${{Postgres.DATABASE_URL}}`
