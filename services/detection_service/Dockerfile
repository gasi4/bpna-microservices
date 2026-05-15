FROM python:3.11-slim

WORKDIR /service
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install heavy ML dependencies in separate cached layers. If a network timeout
# happens, rerunning docker compose build continues from the last successful layer.
RUN python -m pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir --default-timeout=300 --retries=10 "fastapi>=0.115.0" "uvicorn[standard]>=0.30.0" "python-multipart>=0.0.9" numpy
RUN pip install --no-cache-dir --default-timeout=300 --retries=10 opencv-python-headless
RUN pip install --no-cache-dir --default-timeout=600 --retries=10 torch torchvision
RUN pip install --no-cache-dir --default-timeout=600 --retries=10 ultralytics

COPY app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
