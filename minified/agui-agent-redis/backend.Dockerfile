FROM python-base

ARG SERVICE_PATH
ARG SERVICE_MODULE
ARG SERVICE_PORT

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY services /app/services

RUN uv pip install --system -e .

ENV PYTHONPATH=/app/services/${SERVICE_PATH}
ENV SERVICE_MODULE=${SERVICE_MODULE}
ENV SERVICE_PORT=${SERVICE_PORT}

CMD ["sh", "-c", "uvicorn ${SERVICE_MODULE}:app --host 0.0.0.0 --port ${SERVICE_PORT}"]
