FROM python:3.11-slim-bullseye

WORKDIR /app

RUN rm -rf /var/lib/apt/lists/* \
    && apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/Xquantum398/pigi.git .

RUN pip install --no-cache-dir -r requirements.txt
