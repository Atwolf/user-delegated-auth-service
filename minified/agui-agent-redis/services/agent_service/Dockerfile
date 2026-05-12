FROM python-base

COPY pyproject.toml README.md /app/
COPY services /app/services

RUN uv pip install --system -e .

ENV PYTHONPATH=/app/services/agent_service

CMD ["uvicorn", "agent_service_simple.app:app", "--host", "0.0.0.0", "--port", "8090"]
