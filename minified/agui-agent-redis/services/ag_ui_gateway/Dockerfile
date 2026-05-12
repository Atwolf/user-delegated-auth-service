FROM python-base

COPY pyproject.toml README.md /app/
COPY services /app/services

RUN uv pip install --system -e .

ENV PYTHONPATH=/app/services/ag_ui_gateway

CMD ["uvicorn", "ag_ui_gateway_simple.app:app", "--host", "0.0.0.0", "--port", "8088"]
