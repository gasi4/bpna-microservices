FROM python:3.11-slim

WORKDIR /service
COPY services/api_gateway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/api_gateway/app ./app
COPY static /static

CMD ["sh", "-c", "uvicorn app.main:app --host ${HOSTNAME:-0.0.0.0} --port ${PORT:-8000}"]
