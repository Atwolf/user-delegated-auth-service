FROM python-base

COPY pyproject.toml CODEX_PROMPT.md /app/
COPY packages /app/packages
COPY services /app/services
RUN uv pip install --system -e .

CMD ["python", "-m", "network_mcp.server"]
