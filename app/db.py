"""SQLite schema, numbered migrations, seed content and the one-time import from the v1 database."""
from __future__ import annotations

import json
import logging
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import config

log = logging.getLogger('gem.db')

SIZES = [('sedan', 'Sedan or coupe'), ('suv', 'SUV or crossover'), ('truck', 'Large SUV or truck')]
SIZE_LABEL = dict(SIZES)

DEFAULT_SETTINGS = {
    'business_name': 'GEM Autoworks',
    'tagline': 'Your Car. Our Craft.',
    'phone': '(774) 291-1596',
    'email': 'gemautoworksllc@gmail.com',
    'instagram_url': 'https://www.instagram.com/gemautoworksllc/',
    'instagram_handle': '@gemautoworksllc',
    'facebook_url': '',
    'service_area': 'Central Massachusetts',
    'service_towns': '',
    # mobile | shop | both: changes the booking flow and the wording across the site
    'service_mode': 'both',
    'shop_address': '',
    'shop_note': 'The drop-off address is sent with your confirmation.',
    'pricing_note': 'Prices can change with the vehicle’s condition and the distance to you. We confirm the price before we start.',
    'offer_enabled': '1',
    'offer_percent': '10',
    'offer_text': '10% off your first detail',
    'hero_title': 'Mobile car detailing in Central MA',
    'hero_lead': 'We come to you anywhere in Central Massachusetts. Interior, exterior or the full GEM Detail, priced by the size of your car.',
    'about_title': 'Meet Pavly, the owner of GEM Autoworks',
    'about_text': 'I’m 23 years old and the owner of GEM Autoworks. I started this business to combine my passion for cars with the opportunity to serve my community.',
    'about_text_2': 'My goal is to provide professional, high-quality detailing and a great customer experience every time. When you book with GEM Autoworks, you can expect reliable service, attention to detail, and a commitment to your satisfaction.',
    'plans_title': 'Cleaning plans, every 2 to 8 weeks',
    'plans_text': 'Save your car, pick a package and how often. We keep the next three visits on the calendar and email a reminder the day before each one.',
    'booking_requires_approval': '1',
    'booking_lead_hours': '12',
    'booking_window_days': '60',
    'slot_step_minutes': '30',
    'travel_buffer_minutes': '30',
    'cancel_cutoff_hours': '24',
    'plan_horizon_visits': '3',
    'reminders_enabled': '1',
    'seo_description': 'Mobile car detailing in Central Massachusetts by GEM Autoworks. Interior, exterior and full details from $89. Book online, save your cars and set up regular cleanings.',
}

MIGRATIONS: list[str] = [
    # 1: base schema
    '''
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE admins (
        id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE customers (
        id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL COLLATE NOCASE, password_hash TEXT,
        name TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, last_login_at TEXT
    );
    CREATE TABLE vehicles (
        id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
        nickname TEXT NOT NULL DEFAULT '', year TEXT NOT NULL DEFAULT '', make TEXT NOT NULL,
        model TEXT NOT NULL, color TEXT NOT NULL DEFAULT '', size TEXT NOT NULL DEFAULT 'sedan',
        notes TEXT NOT NULL DEFAULT '', archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
    );
    CREATE TABLE addresses (
        id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
        label TEXT NOT NULL DEFAULT 'Home', street TEXT NOT NULL, town TEXT NOT NULL,
        notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
    );
    CREATE TABLE services (
        id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
        includes TEXT NOT NULL DEFAULT '[]', active INTEGER NOT NULL DEFAULT 1, sort_order INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE service_prices (
        service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE, size TEXT NOT NULL,
        price_cents INTEGER NOT NULL, minutes INTEGER NOT NULL, PRIMARY KEY (service_id, size)
    );
    CREATE TABLE addons (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
        price_cents INTEGER, minutes INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
        sort_order INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE hours (
        weekday INTEGER PRIMARY KEY, open_at TEXT NOT NULL, close_at TEXT NOT NULL, closed INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE date_overrides (
        day TEXT PRIMARY KEY, closed INTEGER NOT NULL DEFAULT 1, open_at TEXT, close_at TEXT, note TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE blocks (
        id INTEGER PRIMARY KEY, start_local TEXT NOT NULL, end_local TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE plans (
        id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
        vehicle_id INTEGER NOT NULL REFERENCES vehicles(id), service_id INTEGER NOT NULL REFERENCES services(id),
        interval_weeks INTEGER NOT NULL, weekday INTEGER NOT NULL, preferred_time TEXT NOT NULL,
        location_type TEXT NOT NULL, address TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'requested', start_on TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE appointments (
        id INTEGER PRIMARY KEY, reference TEXT UNIQUE NOT NULL, manage_token TEXT UNIQUE NOT NULL,
        customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
        vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL,
        plan_id INTEGER REFERENCES plans(id) ON DELETE SET NULL,
        service_id INTEGER REFERENCES services(id), service_name TEXT NOT NULL,
        size TEXT NOT NULL DEFAULT 'sedan', addons TEXT NOT NULL DEFAULT '[]',
        vehicle_text TEXT NOT NULL DEFAULT '', location_type TEXT NOT NULL DEFAULT 'mobile',
        address TEXT NOT NULL DEFAULT '', start_local TEXT NOT NULL, minutes INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        price_cents INTEGER, discount_cents INTEGER NOT NULL DEFAULT 0,
        name TEXT NOT NULL, email TEXT NOT NULL COLLATE NOCASE, phone TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '', admin_notes TEXT NOT NULL DEFAULT '',
        reminder_sent INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT 'web',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE INDEX idx_appt_start ON appointments(start_local, status);
    CREATE INDEX idx_appt_customer ON appointments(customer_id);
    CREATE INDEX idx_appt_email ON appointments(email);
    CREATE TABLE reviews (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, rating INTEGER NOT NULL, message TEXT NOT NULL,
        vehicle TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL
    );
    CREATE TABLE gallery (
        id INTEGER PRIMARY KEY, title TEXT NOT NULL, alt TEXT NOT NULL DEFAULT '',
        before_path TEXT, after_path TEXT NOT NULL, before_alt TEXT NOT NULL DEFAULT '',
        featured INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
    );
    CREATE TABLE instagram_posts (
        id INTEGER PRIMARY KEY, image_path TEXT NOT NULL, alt TEXT NOT NULL DEFAULT '', caption TEXT NOT NULL DEFAULT '',
        url TEXT NOT NULL, posted_on TEXT NOT NULL DEFAULT '', visible INTEGER NOT NULL DEFAULT 1,
        sort_order INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE messages (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '',
        topic TEXT NOT NULL DEFAULT '', body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new', created_at TEXT NOT NULL
    );
    CREATE TABLE email_outbox (
        id INTEGER PRIMARY KEY, recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
    );
    CREATE TABLE password_resets (
        token_hash TEXT PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
        expires_at TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0
    );
    ''',
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stamp() -> str:
    return utcnow().isoformat(timespec='seconds')


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(config.DB_PATH), timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=15000')
    return conn


@contextmanager
def connection():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection):
    """BEGIN IMMEDIATE so two visitors can never book the same time at once."""
    conn.execute('BEGIN IMMEDIATE')
    try:
        yield conn
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise


def get_settings(c: sqlite3.Connection) -> dict[str, str]:
    data = dict(DEFAULT_SETTINGS)
    data.update({r['key']: r['value'] for r in c.execute('SELECT key, value FROM settings')})
    return data


def set_setting(c: sqlite3.Connection, key: str, value: str) -> None:
    c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))


def new_reference(c: sqlite3.Connection) -> str:
    alphabet = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
    while True:
        ref = 'GEM-' + ''.join(secrets.choice(alphabet) for _ in range(6))
        if not c.execute('SELECT 1 FROM appointments WHERE reference=?', (ref,)).fetchone():
            return ref


SEED_SERVICES = [
    {
        'slug': 'exterior', 'name': 'Exterior Detail',
        'summary': 'A full hand wash and dry that brings the gloss back to paint, glass and wheels.',
        'includes': ['Thorough hand wash', 'Non-contact wheel cleaning and tire shine', 'Door jambs cleaned',
                     'Exterior windows and mirrors', 'Hand dry with microfiber towels', 'Exterior trim cleaned'],
        'prices': {'sedan': (8900, 90), 'suv': (9900, 105), 'truck': (10900, 120)},
    },
    {
        'slug': 'interior', 'name': 'Interior Detail',
        'summary': 'A complete refresh of the cabin, from the carpets and seats to the vents and trunk.',
        'includes': ['Full vacuum: seats, carpets, mats and trunk', 'Carpet and floor mat cleaning',
                     'Seat cleaning, cloth or leather', 'Dashboard, console and door panels',
                     'Cup holders, vents and crevices', 'Interior surfaces wiped and sanitized',
                     'Interior windows and mirrors', 'Leather cleaned and conditioned, if applicable',
                     'Light stain and spot treatment', 'Interior finishing protectant'],
        'prices': {'sedan': (11900, 150), 'suv': (13900, 180), 'truck': (15900, 210)},
    },
    {
        'slug': 'gem-detail', 'name': 'GEM Detail',
        'summary': 'Everything in the Interior and Exterior Details, done in one visit.',
        'includes': ['Complete interior vacuum', 'Seats, carpets and mats cleaned',
                     'Dashboard, console, doors, vents and crevices', 'Interior windows and mirrors',
                     'Leather cleaning and conditioning, if applicable', 'Full exterior hand wash',
                     'Non-contact wheel cleaning and tire shine', 'Door jambs', 'Exterior glass'],
        'prices': {'sedan': (17900, 240), 'suv': (19900, 270), 'truck': (21900, 300)},
    },
]

SEED_GALLERY = [
    # title, after, before, alt, before_alt, featured
    ('Nissan Altima, full interior', '/static/img/work/altima-after', '/static/img/work/altima-before',
     'Nissan Altima driver seat and dash after the interior detail, clean mats and wiped console',
     'The same Altima before: grit on the driver mat and dust across the dash', 1),
    ('Ford F-150, full interior', '/static/img/work/f150-after', '/static/img/work/f150-before',
     'Ford F-150 cab after the detail: washed rubber mats and clean cloth seats',
     'The F-150 cab before: mud dried into the floor liner', 1),
    ('Nissan Altima, center console', '/static/img/work/altima-console-after', '/static/img/work/altima-console-before',
     'Altima center console after cleaning: dust-free cup holders and shifter trim',
     'The console before: dust and crumbs in the cup holders', 0),
    ('Kia K5, front cabin', '/static/img/work/kia-k5-front', None,
     'Kia K5 front cabin after an interior detail, leather seats and dash cleaned', '', 0),
    ('Kia K5, rear seats', '/static/img/work/kia-k5-rear', None,
     'Kia K5 rear seats and carpet after the interior detail', '', 0),
]

SEED_INSTAGRAM = [
    ('/static/img/work/kia-k5-front', 'Kia K5 cabin after a full interior detail',
     'Fresh, clean, and looking brand new. This Kia K5 got the full interior treatment.',
     'https://www.instagram.com/p/DfXbeZoEcmz/', '2026-11-05'),
    ('/static/img/work/altima-after', 'Nissan Altima interior after the detail',
     'Nissan Altima in for a full interior detail.',
     'https://www.instagram.com/p/De4yj_WGZcw/', '2026-10-24'),
    ('/static/img/work/g37-before', 'Infiniti G37 interior at the start of the job',
     'Infiniti G37 interior transformation, brought back to life with the GEM Autoworks touch.',
     'https://www.instagram.com/reel/Dey0hNJRPHa/', '2026-10-22'),
    ('/static/img/work/grand-cherokee', 'Jeep Grand Cherokee front seats during the detail',
     'Jeep Grand Cherokee, full interior detail.',
     'https://www.instagram.com/reel/DestLIntOVP/', '2026-10-19'),
    ('/static/img/work/f150-after', 'Ford F-150 cab after the interior detail',
     'Another truck, another fresh interior. This Ford F-150 got the Full Interior Detail.',
     'https://www.instagram.com/p/DeNdFKDmTLY/', '2026-10-07'),
]


def migrate() -> None:
    with connection() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)')
        row = c.execute('SELECT version FROM schema_version').fetchone()
        current = row['version'] if row else 0
        fresh = current == 0
        for number, script in enumerate(MIGRATIONS, start=1):
            if number <= current:
                continue
            c.executescript('BEGIN;' + script + 'COMMIT;')
            if row:
                c.execute('UPDATE schema_version SET version=?', (number,))
            else:
                c.execute('INSERT INTO schema_version(version) VALUES(?)', (number,))
                row = {'version': number}
            log.info('database migrated to version %s', number)
        if fresh:
            seed(c)
            import_legacy(c)
        ensure_admin(c)


def seed(c: sqlite3.Connection) -> None:
    now = stamp()
    for i, s in enumerate(SEED_SERVICES):
        cur = c.execute('INSERT INTO services(slug,name,summary,includes,sort_order) VALUES(?,?,?,?,?)',
                        (s['slug'], s['name'], s['summary'], json.dumps(s['includes']), i))
        for size, (price, minutes) in s['prices'].items():
            c.execute('INSERT INTO service_prices(service_id,size,price_cents,minutes) VALUES(?,?,?,?)',
                      (cur.lastrowid, size, price, minutes))
    # Weekly hours are a starting point only; Pavly sets the real ones in Admin > Availability.
    for wd in range(7):
        c.execute('INSERT INTO hours(weekday,open_at,close_at,closed) VALUES(?,?,?,?)', (wd, '08:00', '18:00', int(wd == 6)))
    for i, (title, after, before, alt, before_alt, featured) in enumerate(SEED_GALLERY):
        c.execute('INSERT INTO gallery(title,alt,before_path,after_path,before_alt,featured,sort_order,created_at) VALUES(?,?,?,?,?,?,?,?)',
                  (title, alt, before, after, before_alt, featured, i, now))
    for i, (img, alt, caption, url, posted) in enumerate(SEED_INSTAGRAM):
        c.execute('INSERT INTO instagram_posts(image_path,alt,caption,url,posted_on,sort_order) VALUES(?,?,?,?,?,?)',
                  (img, alt, caption, url, posted, i))


def import_legacy(c: sqlite3.Connection) -> None:
    """Copy the v1 admin login, bookings, reviews and photos. The v1 file itself is never written to."""
    path: Path = config.LEGACY_DB_PATH
    if not path.exists():
        return
    try:
        old = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        old.row_factory = sqlite3.Row
        tables = {r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        now = stamp()
        if 'admin_users' in tables:
            for r in old.execute('SELECT email, password_hash FROM admin_users'):
                c.execute('INSERT OR IGNORE INTO admins(email,password_hash,created_at) VALUES(?,?,?)', (r['email'], r['password_hash'], now))
        if 'appointments' in tables:
            services = {r['id']: r['title'] for r in old.execute('SELECT id, title FROM services')} if 'services' in tables else {}
            for r in old.execute('SELECT * FROM appointments'):
                start = f"{r['day']}T{r['at_time']}"
                c.execute('''INSERT OR IGNORE INTO appointments(reference,manage_token,service_name,vehicle_text,start_local,minutes,
                             status,name,email,phone,notes,source,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                          (r['reference'], secrets.token_urlsafe(24), services.get(r['service_id'], 'Appointment'), r['vehicle'],
                           start, r['duration'], r['status'], r['name'], r['email'], r['phone'], r['notes'], 'v1',
                           r['created_at'], r['updated_at']))
        if 'reviews' in tables:
            for r in old.execute('SELECT * FROM reviews'):
                c.execute('INSERT INTO reviews(name,rating,message,status,created_at) VALUES(?,?,?,?,?)',
                          (r['name'], r['rating'], r['message'], r['status'], r['created_at']))
        if 'gallery' in tables:
            for r in old.execute("SELECT * FROM gallery WHERE image_path LIKE '/uploads/%'"):
                c.execute('INSERT INTO gallery(title,alt,after_path,sort_order,created_at) VALUES(?,?,?,?,?)',
                          (r['title'], r['alt'], r['image_path'], 100 + r['sort_order'], now))
        old.close()
        log.warning('Imported v1 data from %s (the old file was left untouched).', path)
    except sqlite3.Error:
        log.exception('Could not import v1 data; continuing with a fresh database')


def ensure_admin(c: sqlite3.Connection) -> None:
    from .security import hash_password
    if c.execute('SELECT 1 FROM admins LIMIT 1').fetchone():
        return
    if not config.ADMIN_EMAIL or len(config.ADMIN_PASSWORD) < 14:
        raise RuntimeError('First boot needs ADMIN_EMAIL and ADMIN_PASSWORD (at least 14 characters).')
    c.execute('INSERT INTO admins(email,password_hash,created_at) VALUES(?,?,?)',
              (config.ADMIN_EMAIL, hash_password(config.ADMIN_PASSWORD), stamp()))
    log.warning('First admin account created for %s.', config.ADMIN_EMAIL)


def backup_copy() -> Path:
    """A consistent copy of the live database for the admin's download button."""
    target = config.DATA_DIR / 'backup-latest.sqlite3'
    with connection() as c:
        dst = sqlite3.connect(str(target))
        c.backup(dst)
        dst.close()
    return target


__all__ = ['SIZES', 'SIZE_LABEL', 'connect', 'connection', 'transaction', 'get_settings', 'set_setting',
           'migrate', 'stamp', 'utcnow', 'new_reference', 'backup_copy']
