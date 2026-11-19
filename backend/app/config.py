from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "app.sqlite"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
FRONTEND_DIR = ROOT / "frontend"

# Bump when korean_analyzer / matcher logic changes; stored with each analysed passage.
ANALYZER_VERSION = "1"
