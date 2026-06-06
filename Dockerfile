FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py title_formatter.py feed_store.py secret_store.py seen_store.py hackernews.py feed_fetcher.py posts_store.py bot.py ./

RUN useradd --create-home --uid 10001 feedbot
USER feedbot

ENTRYPOINT ["python", "-u", "bot.py"]
