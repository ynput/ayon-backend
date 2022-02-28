FROM python:3.10-bullseye
ENV PYTHONUNBUFFERED=1
RUN mkdir /openpype

RUN pip install \
    nxtools \
    orjson \
    fastapi \
    strawberry-graphql[fastapi] \
    uvicorn[standard] \
    aioredis \
    asyncpg \
    email-validator \
    httpx \
    yaoauth2 \
    pytest \
    pytest-order

WORKDIR /openpype
