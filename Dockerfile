FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN addgroup --system trader && adduser --system --ingroup trader trader
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install .
COPY config ./config
RUN mkdir -p /app/runtime && chown -R trader:trader /app
USER trader

ENTRYPOINT ["market-maker"]
CMD ["--config", "config/simulation.json"]
