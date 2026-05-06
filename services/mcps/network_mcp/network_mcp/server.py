from __future__ import annotations

from network_mcp.tools import mcp


def main() -> None:
    mcp.run(transport="http", host="0.0.0.0", port=8011)


if __name__ == "__main__":
    main()
