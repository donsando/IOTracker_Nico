FROM --platform=linux/amd64 postgis/postgis:16-3.5

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgrouting \
    && rm -rf /var/lib/apt/lists/*
