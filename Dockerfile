FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-relay.txt .
RUN pip install --no-cache-dir -r requirements-relay.txt

COPY phone ./phone
COPY relay ./relay

CMD ["python", "-m", "relay.main"]
