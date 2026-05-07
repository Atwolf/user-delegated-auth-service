from __future__ import annotations

from developer_mcp.tools import mcp


def main() -> None:
    mcp.run(transport="http", host="0.0.0.0", port=8001)


if __name__ == "__main__":
    main()
