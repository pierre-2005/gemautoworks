"""Customer portal smoke tests, isolated via test_site.py environment."""
import os, tempfile
os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='gem-portal-tests-'))
os.environ.setdefault('SECRET_KEY', 'portal-tests-only-secret-key-1234567890-123')
os.environ.setdefault('ADMIN_EMAIL', 'owner@example.com')
os.environ.setdefault('ADMIN_PASSWORD', 'PortalTestPassword-2026-1234')
os.environ.setdefault('COOKIE_SECURE', 'false')
from fastapi.testclient import TestClient
from app import app, connection, settings
from customer_portal import plus_months
from datetime import date

def test_account_feature_flag_and_pages():
    with TestClient(app) as client:
        assert client.get("/account/login").status_code == 404
        with connection() as c:
            c.execute("UPDATE settings SET value='1' WHERE key='customer_accounts_enabled'")
        assert client.get("/account/login").status_code == 200
        assert client.get("/account/register").status_code == 200
        assert client.get("/account/forgot").status_code == 200
        assert client.get("/account").status_code == 401
        assert "Sign In" in client.get("/").text

def test_recurring_date_rollover():
    assert plus_months(date(2026,1,31),1)==date(2026,2,28)
    assert plus_months(date(2024,1,31),1)==date(2024,2,29)
    assert plus_months(date(2026,12,5),12)==date(2027,12,5)
