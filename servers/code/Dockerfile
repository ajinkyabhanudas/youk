FROM python:3.13-slim

WORKDIR /app

COPY servers/code/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY servers/shared/ /shared/
COPY servers/code/src/ .

CMD ["python", "server.py"]
