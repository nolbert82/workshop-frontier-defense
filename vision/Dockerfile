FROM python:3.12.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 YOLO_CONFIG_DIR=/tmp/ultralytics
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY vision/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r /tmp/requirements.txt && useradd --uid 10001 --create-home sentinel
COPY vision /app/vision
USER sentinel
CMD ["python", "-m", "vision.service", "--bind", "0.0.0.0", "--config", "/run/secrets/app.json", "--camera", "0"]
