FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY etl etl
COPY ml ml
COPY sql sql
COPY tests tests
COPY pytest.ini .
RUN mkdir -p /app/artifacts && chown -R 10001:10001 /app
USER 10001:10001
CMD ["python", "-m", "etl.pipeline"]
