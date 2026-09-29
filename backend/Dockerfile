FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY migrations ./migrations
COPY src ./src
COPY tests ./tests
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir ".[dev]"

EXPOSE 8000

CMD ["uvicorn", "price_lens.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
