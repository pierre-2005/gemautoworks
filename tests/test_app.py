"""End-to-end checks of the web app through its HTTP routes (no browser)."""
from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest

TMP = tempfile.mkdtemp(prefix='gem-test-')
os.environ.update(SECRET_KEY='t' * 48, DATA_DIR=TMP, ADMIN_EMAIL='owner@example.test', ADMIN_PASSWORD='owner-password-123',
                  COOKIE_SECURE='false', BUSINESS_TIMEZONE='America/New_York')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import booking as bk  # noqa: E402
from app.db import connection  # noqa: E402
from app.main import app  # noqa: E402
from app.security import reset_throttles  # noqa: E402


@pytest.fixture()
def client():
    reset_throttles()
    with TestClient(app) as c:
        yield c


def csrf(client, path='/book'):
    html = client.get(path).text
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def open_slot(minutes=150):
    with connection() as c:
        start = bk.now_local().date() + timedelta(days=2)
        for i in range(30):
            d = start + timedelta(days=i)
            free = bk.slots(c, d, minutes)
            if free:
                return d.isoformat(), free[0]
    raise AssertionError('no open slot')


def services():
    with connection() as c:
        return {s['slug']: s for s in bk.list_services(c)}


def book(client, **over):
    s = services()['interior']
    day, at = open_slot(s['prices']['sedan']['minutes'])
    data = {'csrf': csrf(client), 'service': s['id'], 'size': 'sedan', 'make': 'Honda', 'model': 'Civic', 'year': '2019',
            'location_type': 'mobile', 'street': '12 Elm St', 'town': 'Worcester', 'day': day, 'time': at,
            'name': 'Test Customer', 'email': 'cust@example.test', 'phone': '(508) 555-0100', 'notes': ''}
    data.update(over)
    return client.post('/book', data=data, follow_redirects=False), data


def test_public_pages(client):
    for path in ('/', '/services', '/work', '/about', '/contact', '/reviews', '/book', '/privacy', '/terms',
                 '/account/login', '/account/signup', '/admin/login', '/robots.txt', '/sitemap.xml', '/health'):
        r = client.get(path)
        assert r.status_code == 200, path
    assert client.get('/missing-page').status_code == 404
    home = client.get('/').text
    assert '$89' in home and 'Book a detail' in home and 'lorem' not in home.lower()


def test_quote_and_offer(client):
    s = services()['gem-detail']
    q = client.get(f"/api/quote?service={s['id']}&size=suv").json()
    assert q['price'] == '$199' and q['discount'] == '$19.90' and q['total'] == '$179.10' and q['offer']


def test_guest_booking_and_manage(client):
    r, data = book(client)
    assert r.status_code == 303 and r.headers['location'].startswith('/booking/')
    page = client.get(r.headers['location'])
    assert page.status_code == 200 and 'Your request is in' in page.text
    # the same time cannot be booked twice
    r2, _ = book(client, email='other@example.test', day=data['day'], time=data['time'])
    assert r2.status_code == 400 and 'just taken' in r2.text
    # cancel through the emailed link
    token = r.headers['location'].split('/')[2].split('?')[0]
    c = client.post(f'/booking/{token}/cancel', data={'csrf': csrf(client)}, follow_redirects=False)
    assert c.status_code == 303
    with connection() as conn:
        assert conn.execute('SELECT status FROM appointments WHERE manage_token=?', (token,)).fetchone()[0] == 'cancelled'
        assert conn.execute("SELECT COUNT(*) FROM email_outbox WHERE recipient='cust@example.test'").fetchone()[0] >= 2


def test_booking_validation(client):
    r, _ = book(client, email='not-an-email', phone='12', make='', model='')
    assert r.status_code == 400
    assert 'Write an email address' in r.text and 'Write the make and model' in r.text


def test_csrf_required(client):
    r = client.post('/contact', data={'name': 'A', 'email': 'a@example.test', 'message': 'hello there'}, follow_redirects=False)
    assert r.status_code == 400


def test_contact_and_review(client):
    r = client.post('/contact', data={'csrf': csrf(client, '/contact'), 'name': 'Sam', 'email': 'sam@example.test',
                                      'message': 'Can you do a 3-row SUV?'}, follow_redirects=False)
    assert r.status_code == 303
    r = client.post('/reviews', data={'csrf': csrf(client, '/reviews'), 'name': 'Sam', 'rating': '5',
                                      'message': 'Great job on my truck, like new.'}, follow_redirects=False)
    assert r.status_code == 303
    assert 'Great job on my truck' not in client.get('/reviews').text   # waits for approval


def signup(client, email='garage@example.test'):
    return client.post('/account/signup', data={'csrf': csrf(client, '/account/signup'), 'name': 'Gina Garage', 'email': email,
                                                'phone': '508-555-0199', 'password': 'a-long-password'}, follow_redirects=False)


def test_account_garage_and_plan(client):
    assert signup(client).status_code == 303
    t = csrf(client, '/account')
    assert client.post('/account/vehicles', data={'csrf': t, 'year': '2021', 'make': 'Toyota', 'model': 'RAV4', 'size': 'suv'},
                       follow_redirects=False).status_code == 303
    assert client.post('/account/addresses', data={'csrf': t, 'label': 'Home', 'street': '5 Oak Rd', 'town': 'Shrewsbury'},
                       follow_redirects=False).status_code == 303
    page = client.get('/account').text
    assert 'RAV4' in page and '5 Oak Rd' in page
    with connection() as c:
        vid = c.execute("SELECT id FROM vehicles WHERE model='RAV4'").fetchone()[0]
        aid = c.execute("SELECT id FROM addresses WHERE street='5 Oak Rd'").fetchone()[0]
    sid = services()['exterior']['id']
    r = client.post('/account/plans', data={'csrf': t, 'vehicle_id': vid, 'service_id': sid, 'interval_weeks': 2, 'weekday': 2,
                                            'preferred_time': '10:00', 'location_type': 'mobile', 'address_id': aid}, follow_redirects=False)
    assert r.status_code == 303
    # admin approves: the next three visits are put on the calendar
    admin = TestClient(app)
    admin.post('/admin/login', data={'csrf': csrf(admin, '/admin/login'), 'email': 'owner@example.test', 'password': 'owner-password-123'})
    with connection() as c:
        pid = c.execute("SELECT id FROM plans WHERE vehicle_id=?", (vid,)).fetchone()[0]
    assert admin.post(f'/admin/plans/{pid}/approve', data={'csrf': csrf(admin, '/admin/plans')}, follow_redirects=False).status_code == 303
    with connection() as c:
        visits = c.execute("SELECT start_local, status FROM appointments WHERE plan_id=? AND status!='cancelled'", (pid,)).fetchall()
    assert len(visits) == 3
    days = sorted(v[0][:10] for v in visits)
    from datetime import date
    gaps = {(date.fromisoformat(b) - date.fromisoformat(a)).days for a, b in zip(days, days[1:])}
    assert gaps == {14}
    # skip one: it is cancelled and a new one keeps three on the calendar
    assert client.post(f'/account/plans/{pid}/skip', data={'csrf': csrf(client, '/account')}, follow_redirects=False).status_code == 303
    with connection() as c:
        assert c.execute("SELECT COUNT(*) FROM appointments WHERE plan_id=? AND status!='cancelled'", (pid,)).fetchone()[0] == 3


def test_login_logout_and_bad_password(client):
    signup(client, 'login@example.test')
    client.post('/account/logout', data={'csrf': csrf(client, '/account')})
    r = client.post('/account/login', data={'csrf': csrf(client, '/account/login'), 'email': 'login@example.test', 'password': 'wrong-password'})
    assert 'do not match' in r.text
    r = client.post('/account/login', data={'csrf': csrf(client, '/account/login'), 'email': 'login@example.test', 'password': 'a-long-password'},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'] == '/account'


def test_admin_pages_and_service_mode(client):
    assert client.get('/admin', follow_redirects=False).status_code == 303
    client.post('/admin/login', data={'csrf': csrf(client, '/admin/login'), 'email': 'owner@example.test', 'password': 'owner-password-123'})
    for path in ('/admin', '/admin/appointments', '/admin/calendar', '/admin/customers', '/admin/plans', '/admin/services',
                 '/admin/availability', '/admin/site', '/admin/gallery', '/admin/reviews', '/admin/messages', '/admin/system',
                 '/admin/appointments/new', '/admin/export/bookings.csv'):
        assert client.get(path).status_code == 200, path
    t = csrf(client, '/admin/site')
    form = {k: v for k, v in {'csrf': t, 'service_mode': 'shop', 'service_area': 'Central Massachusetts', 'service_towns': '',
                              'shop_address': '1 Main St, Worcester', 'shop_note': '', 'pricing_note': 'Prices vary.'}.items()}
    assert client.post('/admin/settings/service', data=form, follow_redirects=False).status_code == 303
    assert 'We come to you' not in client.get('/book').text
    form['service_mode'] = 'both'
    client.post('/admin/settings/service', data=form)
    assert 'We come to you' in client.get('/book').text
