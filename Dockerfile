FROM python:3.15-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

ENTRYPOINT ["arch-qube"]
