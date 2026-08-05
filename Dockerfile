FROM python:3.13-alpine
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ADD pyproject.toml .
ADD LICENSE.txt .
ADD README.rst .
ADD clashogram ./clashogram
RUN uv pip install --system --no-cache .

ENV LC_ALL=C.UTF-8
ENTRYPOINT ["clashogram"]
