from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOKEN_BROKER_SRC = PROJECT_ROOT / "packages" / "token_broker" / "src"

sys.path.insert(0, str(TOKEN_BROKER_SRC))
