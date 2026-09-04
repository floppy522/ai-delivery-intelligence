FROM python:3.13-slim
WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock /app/apps/api/
RUN pip install --no-cache-dir uv \
    && uv sync --project /app/apps/api --frozen --no-dev --no-install-project
COPY apps/api /app/apps/api
RUN uv sync --project /app/apps/api --frozen --no-dev \
    && python -c "import adi"
COPY demo /app/demo
COPY policies /app/policies
COPY config /app/config
RUN groupadd --gid 10001 adi && useradd --uid 10001 --gid 10001 --no-create-home adi \
    && chown -R adi:adi /app
ENV PATH="/app/apps/api/.venv/bin:$PATH" ADI_ROOT=/app
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "adi.main:app", "--host", "0.0.0.0", "--port", "8000"]
