FROM python-base

COPY pyproject.toml CODEX_PROMPT.md /app/
COPY services /app/services
RUN uv pip install --system -e .

CMD ["uvicorn", "identity_provider_mock.app:app", "--host", "0.0.0.0", "--port", "8099"]
