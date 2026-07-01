FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY servers/core/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY servers/shared/ /shared/
COPY servers/core/src/ .

CMD ["python", "server.py"]
