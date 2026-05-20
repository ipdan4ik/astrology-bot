FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "uvicorn", "quantuum.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
