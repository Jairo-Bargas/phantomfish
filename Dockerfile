# 3.12 (no 3.13) para asegurar que todas las dependencias tengan wheel
# precompilado en ARM (el servidor gratis de Oracle es ARM) y no haya que
# compilar nada en una máquina de 1 GB de RAM.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# El volumen persistente se monta en /data (ver fly.toml).
# FORWARDED_ALLOW_IPS=*: confiar en el X-Forwarded-Proto del proxy de Fly, para
# que la cookie de sesión 'secure' se emita correctamente detrás de HTTPS.
ENV DATABASE_URL=sqlite:////data/phantomfish.db \
    STORAGE_DIR=/data/uploads \
    COOKIE_SECURE=true \
    FORWARDED_ALLOW_IPS=*

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
