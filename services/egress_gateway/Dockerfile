FROM python-base

COPY pyproject.toml CODEX_PROMPT.md /app/
COPY packages /app/packages
COPY services /app/services
RUN uv pip install --system -e .

ENV PYTHONPATH=/app/services/egress_gateway

CMD ["uvicorn", "egress_gateway.app:app", "--host", "0.0.0.0", "--port", "8091"]
