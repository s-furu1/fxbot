FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    TZ=UTC \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

ENTRYPOINT ["python", "-m", "fxbot.main"]
CMD []
