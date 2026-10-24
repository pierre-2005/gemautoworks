"""One-time secure configuration wizard. Run: python3 setup.py"""
import getpass
import re
import secrets
from pathlib import Path

here=Path(__file__).resolve().parent
path=here/'.env'
if path.exists():
    print('A .env file already exists. For safety, setup will not overwrite it.')
    raise SystemExit(1)
print('GEM Autoworks first-run configuration')
email=input('Admin login email: ').strip().lower()
if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
    raise SystemExit('Invalid email address.')
password=getpass.getpass('Admin password (14+ characters, will not show): ')
confirm=getpass.getpass('Confirm password: ')
if len(password)<14 or password!=confirm:
    raise SystemExit('Passwords do not match or are under 14 characters.')
timezone=input('Business timezone [America/New_York]: ').strip() or 'America/New_York'
try:
    from zoneinfo import ZoneInfo
    ZoneInfo(timezone)
except Exception:
    raise SystemExit('Invalid timezone. Example: America/New_York or America/Edmonton')
print('SMTP configuration can be added later. Without it, bookings save but email will not send.')
add_smtp=input('Set up Gmail notifications now? [y/N]: ').strip().lower()=='y'
from_email=''
app_password=''
if add_smtp:
    from_email=input('Gmail sender email (must be your Gmail account): ').strip()
    app_password=getpass.getpass('Gmail app password (16 characters, no spaces): ').replace(' ','')
    if not from_email or not app_password: raise SystemExit('SMTP information incomplete.')
settings={
 'SECRET_KEY':secrets.token_urlsafe(48),
 'ADMIN_EMAIL':email,
 'ADMIN_PASSWORD':password,
 'COOKIE_SECURE':'true',
 'BUSINESS_TIMEZONE':timezone,
 'SMTP_HOST':'smtp.gmail.com',
 'SMTP_PORT':'465',
 'SMTP_SECURITY':'ssl',
 'SMTP_USER':from_email,
 'SMTP_PASSWORD':app_password,
 'SMTP_FROM':from_email,
}
# This is shell env_file format. Disallow interpolation / control chars in password.
for k,v in settings.items():
    if '\n' in v or '\r' in v or '$' in v or '#' in v:
        raise SystemExit('Please avoid $, #, or newline characters in environment values. Use other strong password characters.')
path.write_text(''.join(f'{k}={v}\n' for k,v in settings.items()))
path.chmod(0o600)
print('\nConfiguration saved to .env with restricted permissions.')
print('Next: docker compose up -d --build')
print('Admin: https://YOUR-DOMAIN/admin/login')
