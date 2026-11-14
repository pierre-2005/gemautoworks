"""Environment configuration. Everything secret comes from the environment (Portainer stack env)."""
from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get('DATA_DIR', str(ROOT / 'data')))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / 'gem_v2.sqlite3'
LEGACY_DB_PATH = DATA_DIR / 'gem.sqlite3'
UPLOAD_DIR = DATA_DIR / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SECRET_KEY = os.environ.get('SECRET_KEY', '')
if len(SECRET_KEY) < 32:
    raise RuntimeError('Set SECRET_KEY to a random value of at least 32 characters (see README).')

COOKIE_SECURE = os.environ.get('COOKIE_SECURE', 'true').lower() == 'true'
BUSINESS_TZ = os.environ.get('BUSINESS_TIMEZONE', 'America/New_York')
TZ = ZoneInfo(BUSINESS_TZ)
PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', '').rstrip('/')

ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '').strip().lower()
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')


def smtp_configured() -> bool:
    return all(os.environ.get(k) for k in ('SMTP_HOST', 'SMTP_FROM', 'SMTP_USER', 'SMTP_PASSWORD'))
