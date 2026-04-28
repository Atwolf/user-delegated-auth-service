FROM python-base

COPY pyproject.toml CODEX_PROMPT.md /app/
COPY packages /app/packages
COPY services /app/services
RUN uv pip install --system -e .

CMD ["uvicorn", "observability_sidecar.app:app", "--host", "0.0.0.0", "--port", "4319"]
