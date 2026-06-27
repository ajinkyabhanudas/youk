FROM python:3.13-slim

WORKDIR /app

COPY servers/core/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY servers/shared/ /shared/
COPY servers/core/src/ .

CMD ["python", "server.py"]
