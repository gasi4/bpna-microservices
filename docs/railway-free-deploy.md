# Railway Free Deployment

This project can be deployed to Railway Free as a single Railway service while keeping the codebase split into microservices.

## Why this mode exists

Railway Free allows only a small number of services per project. Because this project also needs PostgreSQL, deploying each backend service separately quickly hits that limit.

To work around that, the repository includes:

- `Railway.free.Dockerfile`
- `deploy/railway_free/launcher.py`

The launcher starts all backend services inside one container:

- auth-service
- telemetry-service
- device-service
- control-service
- wifi-service
- detection-service
- api-gateway

The public entrypoint remains the API gateway, and the internal services continue to communicate over localhost ports.

## Railway project layout

Recommended services in Railway Free:

- `bpna` - application service from this GitHub repository
- `Postgres` - Railway PostgreSQL plugin
- `Redis` - optional; remove it if you want a cleaner free-tier setup

Only `bpna` needs a public domain.

## Configure the `bpna` service

In Railway -> `bpna` -> Settings:

- Root Directory: `/`
- Dockerfile Path: `Railway.free.Dockerfile`

In Railway -> `bpna` -> Variables:

```env
PORT=8000
DATABASE_URL=${{Postgres.DATABASE_URL}}
SECRET_KEY=change-this-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
DEVICE_SECRET=change-me-device
YOLO_MODEL_PATH=/opt/bpna/yolo11s.pt
```

Notes:

- `DATABASE_URL` from Railway Postgres is normalized automatically inside the launcher to `postgresql+asyncpg://...` when needed.
- `PORT` is used by the public API gateway.
- Internal services run on localhost ports `8001` through `8006` inside the same container.

## Networking

In Railway -> `bpna` -> Networking:

- Generate Domain

Use that generated public URL as the main server URL.

## What works in this mode

- web interface via API gateway
- authentication
- device websocket
- telemetry
- Wi-Fi map endpoints
- detection service

## Tradeoff

This is a single deployment unit for hosting convenience, not separate Railway services. The application architecture in the repository remains microservice-based, but Railway Free runs them together inside one container because of platform limits.
