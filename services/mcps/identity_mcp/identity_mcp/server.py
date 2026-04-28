from __future__ import annotations

from identity_mcp.tools import mcp


def main() -> None:
    run = getattr(mcp, "run", None)
    if not callable(run):
        raise RuntimeError("FastMCP runtime is not installed")
    run(transport="http", host="0.0.0.0", port=8003)


if __name__ == "__main__":
    main()
