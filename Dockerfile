FROM python:3.13.0-alpine3.20

WORKDIR /app

RUN apk add --no-cache git openssh

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
