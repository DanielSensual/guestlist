import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FIXTURES = ROOT / "tests" / "fixtures"

# Tests never touch the network or the real spend ledger.
os.environ.setdefault("GUESTLIST_CACHE", str(ROOT / ".pytest-cache-guestlist"))
os.environ.pop("MODEL_API_KEY", None)
