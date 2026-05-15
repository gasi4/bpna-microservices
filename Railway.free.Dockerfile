FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/bpna

COPY services/api_gateway/requirements.txt /tmp/api_gateway.txt
COPY services/auth_service/requirements.txt /tmp/auth_service.txt
COPY services/control_service/requirements.txt /tmp/control_service.txt
COPY services/detection_service/requirements.txt /tmp/detection_service.txt
COPY services/device_service/requirements.txt /tmp/device_service.txt
COPY services/telemetry_service/requirements.txt /tmp/telemetry_service.txt
COPY services/wifi_service/requirements.txt /tmp/wifi_service.txt

RUN pip install --no-cache-dir -r /tmp/api_gateway.txt \
    && pip install --no-cache-dir -r /tmp/auth_service.txt \
    && pip install --no-cache-dir -r /tmp/control_service.txt \
    && pip install --no-cache-dir -r /tmp/detection_service.txt \
    && pip install --no-cache-dir -r /tmp/device_service.txt \
    && pip install --no-cache-dir -r /tmp/telemetry_service.txt \
    && pip install --no-cache-dir -r /tmp/wifi_service.txt

COPY services ./services
COPY static /static
COPY deploy/railway_free ./deploy/railway_free
COPY yolo11s.pt ./yolo11s.pt

CMD ["python", "deploy/railway_free/launcher.py"]
