FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AULA_DATA=/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/uploads

EXPOSE 8765

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-${AULA_PORT:-8765}} --proxy-headers --forwarded-allow-ips='*'"]
