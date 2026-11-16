"""Admin panel: the day's jobs, bookings, customers, plans, prices, availability, content and settings."""
from __future__ import annotations

import csv
import io
import json
import math
import secrets
import tempfile
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 40_000_000   # a 40 MP photo is plenty; larger ones could exhaust the Pi's memory

from .. import booking as bk
from .. import config
from ..db import SIZE_LABEL, SIZES, backup_copy, connection, get_settings, set_setting, stamp, transaction
from ..mail import booking_emails, send_pending
from ..security import check_csrf, clean, email_ok, hash_password, password_problem, session_rotate, throttle, verify_password

router = APIRouter(prefix='/admin')

SETTING_GROUPS = {
    'business': ['business_name', 'tagline', 'phone', 'email', 'instagram_url', 'instagram_handle', 'facebook_url'],
    'service': ['service_mode', 'service_area', 'service_towns', 'shop_address', 'shop_note', 'pricing_note'],
    'offer': ['offer_enabled', 'offer_percent', 'offer_text'],
    'copy': ['hero_title', 'hero_lead', 'about_title', 'about_text', 'about_text_2', 'plans_title', 'plans_text', 'seo_description'],
    'rules': ['booking_requires_approval', 'booking_lead_hours', 'booking_window_days', 'slot_step_minutes',
              'travel_buffer_minutes', 'cancel_cutoff_hours', 'plan_horizon_visits', 'reminders_enabled'],
}
NUMERIC = {'offer_percent': (0, 50), 'booking_lead_hours': (0, 168), 'booking_window_days': (7, 365), 'slot_step_minutes': (15, 120),
           'travel_buffer_minutes': (0, 180), 'cancel_cutoff_hours': (0, 168), 'plan_horizon_visits': (1, 6)}
FLAGS = {'offer_enabled', 'booking_requires_approval', 'reminders_enabled'}


def admin_id(request: Request) -> int | None:
    return request.session.get('admin_id')


def need_admin(request: Request) -> int:
    aid = admin_id(request)
    if aid:
        with connection() as c:
            row = c.execute('SELECT session_version FROM admins WHERE id=?', (aid,)).fetchone()
        if not row or row['session_version'] != request.session.get('admin_sv', 0):
            request.session.pop('admin_id', None)
            aid = None
    if not aid:
        raise HTTPException(303, headers={'Location': '/admin/login'})
    return aid


def _render(request, name, **ctx):
    from ..main import render
    with connection() as c:
        ctx.setdefault('counts', _counts(c))
    return render(request, name, **ctx)


def _counts(c) -> dict:
    today = bk.now_local().strftime('%Y-%m-%dT00:00')
    return {
        'pending': c.execute("SELECT COUNT(*) FROM appointments WHERE status='pending' AND start_local>=?", (today,)).fetchone()[0],
        'needs_time': c.execute("SELECT COUNT(*) FROM appointments WHERE status='needs_time' AND start_local>=?", (today,)).fetchone()[0],
        'plans': c.execute("SELECT COUNT(*) FROM plans WHERE status='requested'").fetchone()[0],
        'messages': c.execute("SELECT COUNT(*) FROM messages WHERE status='new'").fetchone()[0],
        'reviews': c.execute("SELECT COUNT(*) FROM reviews WHERE status='pending'").fetchone()[0],
    }


def back(path: str, msg: str = 'saved') -> RedirectResponse:
    sep = '&' if '?' in path else '?'
    return RedirectResponse(f'{path}{sep}msg={msg}', 303)


# ------------------------------------------------------------------ sign in

@router.get('/login')
def login_page(request: Request):
    if admin_id(request):
        return RedirectResponse('/admin', 303)
    return _render(request, 'admin/login.html', error='')


@router.post('/login')
def login(request: Request, csrf: str = Form(''), email: str = Form(''), password: str = Form('')):
    check_csrf(request, csrf)
    throttle(request, 'admin-login', 8, 900)
    with connection() as c:
        row = c.execute('SELECT * FROM admins WHERE email=?', (clean(email, 254).lower(),)).fetchone()
    if not verify_password(row['password_hash'] if row else None, password):
        return _render(request, 'admin/login.html', error='That email and password do not match.')
    session_rotate(request)
    request.session['admin_id'] = row['id']
    request.session['admin_sv'] = row['session_version']
    return RedirectResponse('/admin', 303)


@router.post('/logout')
def logout(request: Request, csrf: str = Form('')):
    check_csrf(request, csrf)
    request.session.pop('admin_id', None)
    return RedirectResponse('/admin/login', 303)


# ------------------------------------------------------------------ today

@router.get('')
def today_view(request: Request):
    need_admin(request)
    now = bk.now_local()
    with connection() as c:
        d0 = now.strftime('%Y-%m-%dT00:00')
        d1 = (now + timedelta(days=1)).strftime('%Y-%m-%dT00:00')
        d7 = (now + timedelta(days=8)).strftime('%Y-%m-%dT00:00')
        today = [bk.appointment_view(r) for r in c.execute(
            "SELECT * FROM appointments WHERE start_local>=? AND start_local<? AND status IN ('pending','confirmed','completed','needs_time') ORDER BY start_local", (d0, d1))]
        week = [bk.appointment_view(r) for r in c.execute(
            "SELECT * FROM appointments WHERE start_local>=? AND start_local<? AND status IN ('pending','confirmed','needs_time') ORDER BY start_local", (d1, d7))]
        attention = [bk.appointment_view(r) for r in c.execute(
            "SELECT * FROM appointments WHERE start_local>=? AND status IN ('pending','needs_time') ORDER BY start_local LIMIT 20", (d0,))]
        site = get_settings(c)
        month_total = c.execute("SELECT COALESCE(SUM(price_cents-discount_cents),0) FROM appointments WHERE status='completed' AND start_local>=?",
                                (now.strftime('%Y-%m-01'),)).fetchone()[0]
        opening = bk.next_opening(c, 150)
    return _render(request, 'admin/today.html', section='today', today_list=today, week=week, attention=attention, now=now,
                   month_total=month_total, opening=opening, smtp=config.smtp_configured(), site_settings=site)


# ------------------------------------------------------------------ appointments

@router.get('/appointments')
def appointments(request: Request, view: str = 'upcoming', q: str = '', msg: str = ''):
    need_admin(request)
    today = bk.now_local().strftime('%Y-%m-%dT00:00')
    where, args, order = [], [], 'start_local'
    if view == 'upcoming':
        where.append("start_local>=? AND status IN ('pending','confirmed','needs_time')"); args.append(today)
    elif view == 'pending':
        where.append("status IN ('pending','needs_time') AND start_local>=?"); args.append(today)
    elif view == 'past':
        where.append('start_local<?'); args.append(today); order = 'start_local DESC'
    elif view == 'cancelled':
        where.append("status='cancelled'"); order = 'start_local DESC'
    if q:
        where.append('(name LIKE ? OR email LIKE ? OR phone LIKE ? OR reference LIKE ? OR vehicle_text LIKE ?)')
        args += [f'%{q}%'] * 5
    sql = 'SELECT * FROM appointments' + (' WHERE ' + ' AND '.join(where) if where else '') + f' ORDER BY {order} LIMIT 300'
    with connection() as c:
        rows = [bk.appointment_view(r) for r in c.execute(sql, args)]
    return _render(request, 'admin/appointments.html', section='appointments', rows=rows, view=view, q=q, msg=msg)


@router.get('/appointments/new')
def new_appointment_page(request: Request, msg: str = ''):
    need_admin(request)
    with connection() as c:
        return _render(request, 'admin/appointment_new.html', section='appointments', services=bk.list_services(c, False),
                       addons=bk.list_addons(c, False), msg=msg, today=bk.now_local().date())


@router.post('/appointments/new')
async def new_appointment(request: Request):
    need_admin(request)
    form = await request.form()
    check_csrf(request, form.get('csrf'))
    g = lambda k, n=200: clean(str(form.get(k, '')), n)  # noqa: E731
    try:
        d = date.fromisoformat(g('day'))
        time.fromisoformat(g('time'))
    except ValueError:
        raise HTTPException(400, 'Pick a day and a start time.')
    if not g('name') or not email_ok(g('email').lower()):
        raise HTTPException(400, 'Write the customer name and a valid email.')
    with connection() as c:
        try:
            q = bk.quote(c, _int(g('service'), 'Package'), g('size'), [int(x) for x in form.getlist('addons') if str(x).isdigit()],
                         email=g('email').lower())
        except bk.BookingError as e:
            raise HTTPException(400, str(e) or 'Choose a package and size.')
        if g('price').strip():
            q.price_cents = _dollars(g('price'))
            q.discount_cents = 0
        cust = c.execute('SELECT id FROM customers WHERE email=?', (g('email').lower(),)).fetchone()
        try:
          with transaction(c):
            appt = bk.create_appointment(c, q=q, day=d, at=g('time'), name=g('name'), email=g('email').lower(), phone=g('phone'),
                                         vehicle_text=g('vehicle'), location_type=g('location_type') or 'mobile', address=g('address'),
                                         notes=g('notes', 600), customer_id=cust['id'] if cust else None, status='confirmed',
                                         source='admin', check_free=not form.get('override'))
            if form.get('notify'):
                booking_emails(c, appt, 'confirmed')
        except bk.BookingError:
            raise HTTPException(400, 'That time overlaps another booking or falls outside your hours. Tick "Allow it to overlap" to book it anyway.')
    return back(f"/admin/appointments/{appt['id']}", 'created')


@router.get('/appointments/{aid}')
def appointment_detail(request: Request, aid: int, msg: str = '', day: str = ''):
    need_admin(request)
    with connection() as c:
        a = c.execute('SELECT * FROM appointments WHERE id=?', (aid,)).fetchone()
        if not a:
            raise HTTPException(404, 'That booking was not found.')
        view = bk.appointment_view(a)
        try:
            pick = date.fromisoformat(day) if day else view['start'].date()
        except ValueError:
            pick = view['start'].date()
        times = bk.slots(c, pick, a['minutes'], exclude_id=aid, ignore_window=True)
        history = [bk.appointment_view(r) for r in c.execute(
            'SELECT * FROM appointments WHERE email=? AND id!=? ORDER BY start_local DESC LIMIT 10', (a['email'], aid))]
        customer = c.execute('SELECT * FROM customers WHERE email=?', (a['email'],)).fetchone()
    return _render(request, 'admin/appointment.html', section='appointments', a=view, msg=msg, pick=pick.isoformat(), times=times,
                   history=history, customer=dict(customer) if customer else None, statuses=bk.STATUS_LABEL)


@router.post('/appointments/{aid}')
def appointment_update(request: Request, aid: int, csrf: str = Form(''), status: str = Form(''), price: str = Form(''),
                       admin_notes: str = Form(''), notify: str = Form('')):
    need_admin(request)
    check_csrf(request, csrf)
    if status not in bk.STATUS_LABEL:
        raise HTTPException(400, 'Choose a status.')
    with connection() as c:
        a = c.execute('SELECT * FROM appointments WHERE id=?', (aid,)).fetchone()
        if not a:
            raise HTTPException(404, 'That booking was not found.')
        cents = a['price_cents']
        if price.strip():
            cents = _dollars(price)
        with transaction(c):
            if status in bk.LIVE and a['status'] not in bk.LIVE:
                start = bk.parse_local(a['start_local'])
                if start.strftime('%H:%M') not in bk.slots(c, start.date(), a['minutes'], exclude_id=aid, ignore_window=True):
                    raise HTTPException(400, 'That time now overlaps another booking. Pick a new time first.')
            c.execute('UPDATE appointments SET status=?, price_cents=?, admin_notes=?, updated_at=? WHERE id=?',
                      (status, cents, clean(admin_notes, 2000), stamp(), aid))
            fresh = dict(c.execute('SELECT * FROM appointments WHERE id=?', (aid,)).fetchone())
            if notify and status != a['status'] and status in ('confirmed', 'cancelled'):
                booking_emails(c, fresh, status)
            if notify and status == 'completed' and a['status'] != 'completed':
                from ..mail import link, queue
                site = get_settings(c)
                queue(c, fresh['email'], 'How did your GEM detail go?',
                      f"Hi {fresh['name'].split(' ')[0]},\n\nThanks for choosing GEM Autoworks. If you have a minute, a short review "
                      f"helps a small business a lot:\n{link('/reviews?b=' + fresh['manage_token'])}\n\nGEM Autoworks, {site['phone']}")
    return back(f'/admin/appointments/{aid}')


@router.post('/appointments/{aid}/move')
def appointment_move(request: Request, aid: int, csrf: str = Form(''), day: str = Form(''), at: str = Form(''),
                     notify: str = Form(''), override: str = Form('')):
    need_admin(request)
    check_csrf(request, csrf)
    try:
        d = date.fromisoformat(day)
        time.fromisoformat(at)
    except ValueError:
        raise HTTPException(400, 'Pick a day and a start time.')
    with connection() as c:
        a = c.execute('SELECT * FROM appointments WHERE id=?', (aid,)).fetchone()
        if not a:
            raise HTTPException(404, 'That booking was not found.')
        with transaction(c):
            if not override and at not in bk.slots(c, d, a['minutes'], exclude_id=aid, ignore_window=True):
                raise HTTPException(400, 'That time overlaps another booking or falls outside your hours.')
            status = 'confirmed' if a['status'] == 'needs_time' else a['status']
            c.execute('UPDATE appointments SET start_local=?, status=?, reminder_sent=0, updated_at=? WHERE id=?',
                      (f'{d.isoformat()}T{at}', status, stamp(), aid))
            if notify:
                booking_emails(c, dict(c.execute('SELECT * FROM appointments WHERE id=?', (aid,)).fetchone()), 'changed')
    return back(f'/admin/appointments/{aid}', 'moved')


@router.get('/calendar')
def calendar(request: Request, start: str = ''):
    need_admin(request)
    try:
        s = date.fromisoformat(start) if start else bk.now_local().date()
    except ValueError:
        s = bk.now_local().date()
    s = s - timedelta(days=s.weekday())
    days = [s + timedelta(days=i) for i in range(7)]
    with connection() as c:
        rows = [bk.appointment_view(r) for r in c.execute(
            "SELECT * FROM appointments WHERE start_local>=? AND start_local<? AND status!='cancelled' ORDER BY start_local",
            (s.isoformat(), (s + timedelta(days=7)).isoformat()))]
        blocks = [dict(r) for r in c.execute('SELECT * FROM blocks WHERE end_local>? AND start_local<? ORDER BY start_local',
                                             (s.isoformat(), (s + timedelta(days=7)).isoformat()))]
        hours = {d: bk.day_hours(c, d) for d in days}
    by_day = {d: [r for r in rows if r['start'].date() == d] for d in days}
    return _render(request, 'admin/calendar.html', section='calendar', days=days, by_day=by_day, blocks=blocks, hours=hours,
                   prev=(s - timedelta(days=7)).isoformat(), next=(s + timedelta(days=7)).isoformat(), today=bk.now_local().date())


# ------------------------------------------------------------------ customers

@router.get('/customers')
def customers(request: Request, q: str = ''):
    need_admin(request)
    with connection() as c:
        sql = '''SELECT email, MAX(name) AS name, MAX(phone) AS phone, COUNT(*) AS visits, MAX(start_local) AS last_visit,
                 SUM(CASE WHEN status='completed' THEN price_cents-discount_cents ELSE 0 END) AS spent
                 FROM appointments WHERE status!='cancelled' {w} GROUP BY email ORDER BY last_visit DESC LIMIT 500'''
        args = []
        w = ''
        if q:
            w = 'AND (name LIKE ? OR email LIKE ? OR phone LIKE ?)'
            args = [f'%{q}%'] * 3
        rows = [dict(r) for r in c.execute(sql.format(w=w), args)]
        accounts = {r['email'].lower(): dict(r) for r in c.execute('SELECT * FROM customers')}
        for acc in accounts.values():
            if not any(r['email'].lower() == acc['email'].lower() for r in rows) and (not q or q.lower() in (acc['name'] + acc['email']).lower()):
                rows.append({'email': acc['email'], 'name': acc['name'], 'phone': acc['phone'], 'visits': 0, 'last_visit': None, 'spent': 0})
    for r in rows:
        r['account'] = r['email'].lower() in accounts
    return _render(request, 'admin/customers.html', section='customers', rows=rows, q=q)


@router.get('/customers/view')
def customer_view(request: Request, email: str):
    need_admin(request)
    with connection() as c:
        acc = c.execute('SELECT * FROM customers WHERE email=?', (email,)).fetchone()
        appts = [bk.appointment_view(r) for r in c.execute('SELECT * FROM appointments WHERE email=? ORDER BY start_local DESC', (email,))]
        vehicles = [dict(r) for r in c.execute('SELECT * FROM vehicles WHERE customer_id=? ORDER BY archived, id', (acc['id'],))] if acc else []
        addresses = [dict(r) for r in c.execute('SELECT * FROM addresses WHERE customer_id=?', (acc['id'],))] if acc else []
        plans = [dict(r) for r in c.execute('SELECT p.*, s.name AS service_name FROM plans p JOIN services s ON s.id=p.service_id WHERE customer_id=?',
                                            (acc['id'],))] if acc else []
    if not acc and not appts:
        raise HTTPException(404, 'No customer with that email.')
    name = acc['name'] if acc else appts[0]['name']
    return _render(request, 'admin/customer.html', section='customers', acc=dict(acc) if acc else None, email=email, name=name,
                   appts=appts, vehicles=vehicles, addresses=addresses, plans=plans, weekdays=bk.WEEKDAYS)


@router.post('/customers/notes')
def customer_notes(request: Request, csrf: str = Form(''), email: str = Form(''), notes: str = Form('')):
    need_admin(request)
    check_csrf(request, csrf)
    with connection() as c:
        c.execute('UPDATE customers SET notes=? WHERE email=?', (clean(notes, 2000), email))
    return back(f'/admin/customers/view?email={email}')


# ------------------------------------------------------------------ plans

@router.get('/plans')
def plans(request: Request, msg: str = ''):
    need_admin(request)
    with connection() as c:
        rows = []
        for p in c.execute('''SELECT p.*, s.name AS service_name, c.name AS customer_name, c.email, c.phone,
                              v.year, v.make, v.model, v.color, v.size FROM plans p JOIN services s ON s.id=p.service_id
                              JOIN customers c ON c.id=p.customer_id JOIN vehicles v ON v.id=p.vehicle_id
                              ORDER BY CASE p.status WHEN 'requested' THEN 0 WHEN 'active' THEN 1 WHEN 'paused' THEN 2 ELSE 3 END, p.id DESC'''):
            d = dict(p)
            d['upcoming'] = [bk.appointment_view(r) for r in c.execute(
                "SELECT * FROM appointments WHERE plan_id=? AND start_local>=? AND status!='cancelled' ORDER BY start_local LIMIT 4",
                (p['id'], bk.now_local().strftime('%Y-%m-%dT00:00')))]
            rows.append(d)
    return _render(request, 'admin/plans.html', section='plans', rows=rows, weekdays=bk.WEEKDAYS, msg=msg)


@router.post('/plans/{pid}/{action}')
def plan_action(request: Request, pid: int, action: str, csrf: str = Form('')):
    need_admin(request)
    check_csrf(request, csrf)
    status = {'approve': 'active', 'pause': 'paused', 'resume': 'active', 'cancel': 'cancelled'}.get(action)
    if not status:
        raise HTTPException(400, 'Unknown plan action.')
    with connection() as c:
        p = c.execute('SELECT * FROM plans WHERE id=?', (pid,)).fetchone()
        if not p:
            raise HTTPException(404, 'That plan was not found.')
        with transaction(c):
            c.execute('UPDATE plans SET status=?, updated_at=? WHERE id=?', (status, stamp(), pid))
            if status in ('paused', 'cancelled'):
                bk.drop_future_plan_visits(c, pid)
            created = bk.fill_plan(c, pid) if status == 'active' else []
            if action == 'approve':
                from ..mail import queue, link
                cust = c.execute('SELECT * FROM customers WHERE id=?', (p['customer_id'],)).fetchone()
                visits = '\n'.join(f"- {bk.appointment_view(a)['day_text']} at {bk.appointment_view(a)['time_text']}" for a in created)
                queue(c, cust['email'], 'Your GEM Autoworks cleaning plan is active',
                      f"Hi {cust['name'].split(' ')[0]},\n\nYour plan is approved. Your next visits:\n{visits or '- We will text you to set the first time.'}\n\n"
                      f"See or change them: {link('/account')}\n\nGEM Autoworks")
    return back('/admin/plans', action)


# ------------------------------------------------------------------ services and prices

@router.get('/services')
def services(request: Request, msg: str = ''):
    need_admin(request)
    with connection() as c:
        return _render(request, 'admin/services.html', section='services', services=bk.list_services(c, False),
                       addons=bk.list_addons(c, False), msg=msg)


def _dollars(v: str) -> int | None:
    v = (v or '').replace('$', '').replace(',', '').strip()
    if not v:
        return None
    try:
        amount = float(v)
    except ValueError:
        amount = float('nan')
    if not math.isfinite(amount) or not 0 <= amount <= 100000:
        raise HTTPException(400, f'Write prices as numbers from 0 to 100000, like 119. "{v[:20]}" is not one.')
    return round(amount * 100)


def _int(v, label: str, lo: int = -10**6, hi: int = 10**6) -> int:
    try:
        n = int(str(v).strip() or 0)
    except ValueError:
        raise HTTPException(400, f'{label} must be a whole number.')
    return max(lo, min(hi, n))


@router.post('/services/save')
async def save_service(request: Request):
    need_admin(request)
    form = await request.form()
    check_csrf(request, form.get('csrf'))
    sid = _int(form.get('id'), 'Package id', 0)
    name = clean(str(form.get('name', '')), 60)
    if not name:
        raise HTTPException(400, 'Give the package a name.')
    includes = [clean(x, 120) for x in str(form.get('includes', '')).splitlines() if x.strip()][:20]
    with connection() as c:
        with transaction(c):
            if sid:
                c.execute('UPDATE services SET name=?, summary=?, includes=?, active=?, sort_order=? WHERE id=?',
                          (name, clean(str(form.get('summary', '')), 300), json.dumps(includes), int(bool(form.get('active'))),
                           _int(form.get('sort_order'), 'Order', -999, 999), sid))
            else:
                slug = '-'.join(name.lower().split())[:40] + '-' + secrets.token_hex(2)
                sid = c.execute('INSERT INTO services(slug,name,summary,includes,active,sort_order) VALUES(?,?,?,?,?,?)',
                                (slug, name, clean(str(form.get('summary', '')), 300), json.dumps(includes), int(bool(form.get('active'))),
                                 _int(form.get('sort_order') or 99, 'Order', -999, 999))).lastrowid
            for size, _ in SIZES:
                cents = _dollars(str(form.get(f'price_{size}', '')))
                minutes = _int(form.get(f'minutes_{size}'), 'Time in minutes', 0, 24 * 60)
                if cents is None or minutes < 15:
                    raise HTTPException(400, f'Set a price and a time of at least 15 minutes for {SIZE_LABEL[size]}.')
                c.execute('INSERT INTO service_prices(service_id,size,price_cents,minutes) VALUES(?,?,?,?) '
                          'ON CONFLICT(service_id,size) DO UPDATE SET price_cents=excluded.price_cents, minutes=excluded.minutes',
                          (sid, size, cents, minutes))
    return back('/admin/services')


@router.post('/addons/save')
def save_addon(request: Request, csrf: str = Form(''), id: int = Form(0), name: str = Form(''), summary: str = Form(''),
               price: str = Form(''), minutes: int = Form(0), active: str = Form(''), sort_order: int = Form(0)):
    need_admin(request)
    check_csrf(request, csrf)
    if not clean(name, 60):
        raise HTTPException(400, 'Give the add-on a name.')
    vals = (clean(name, 60), clean(summary, 200), _dollars(price), max(0, minutes), int(bool(active)), sort_order)
    with connection() as c:
        if id:
            c.execute('UPDATE addons SET name=?, summary=?, price_cents=?, minutes=?, active=?, sort_order=? WHERE id=?', (*vals, id))
        else:
            c.execute('INSERT INTO addons(name,summary,price_cents,minutes,active,sort_order) VALUES(?,?,?,?,?,?)', vals)
    return back('/admin/services#addons')


@router.post('/addons/{aid}/delete')
def delete_addon(request: Request, aid: int, csrf: str = Form('')):
    need_admin(request)
    check_csrf(request, csrf)
    with connection() as c:
        c.execute('DELETE FROM addons WHERE id=?', (aid,))
    return back('/admin/services#addons', 'deleted')


# ------------------------------------------------------------------ availability

@router.get('/availability')
def availability(request: Request, msg: str = ''):
    need_admin(request)
    with connection() as c:
        hours = [dict(r) for r in c.execute('SELECT * FROM hours ORDER BY weekday')]
        overrides = [dict(r) for r in c.execute('SELECT * FROM date_overrides WHERE day>=? ORDER BY day', (bk.now_local().date().isoformat(),))]
        blocks = [dict(r) for r in c.execute('SELECT * FROM blocks WHERE end_local>=? ORDER BY start_local', (bk.now_local().strftime('%Y-%m-%dT%H:%M'),))]
        site = get_settings(c)
    return _render(request, 'admin/availability.html', section='availability', hours=hours, overrides=overrides, blocks=blocks,
                   weekdays=bk.WEEKDAYS, s=site, msg=msg)


@router.post('/availability/hours')
async def save_hours(request: Request):
    need_admin(request)
    form = await request.form()
    check_csrf(request, form.get('csrf'))
    with connection() as c:
        with transaction(c):
            for wd in range(7):
                o, cl = str(form.get(f'open_{wd}', '08:00')), str(form.get(f'close_{wd}', '18:00'))
                closed = int(bool(form.get(f'closed_{wd}')))
                try:
                    if not closed and bk.hm(cl) <= bk.hm(o):
                        raise HTTPException(400, f'{bk.WEEKDAYS[wd]}: the closing time must be after the opening time.')
                except ValueError:
                    raise HTTPException(400, f'{bk.WEEKDAYS[wd]}: write times like 08:00.')
                c.execute('UPDATE hours SET open_at=?, close_at=?, closed=? WHERE weekday=?', (o, cl, closed, wd))
    return back('/admin/availability#hours')


@router.post('/availability/override')
def add_override(request: Request, csrf: str = Form(''), day: str = Form(''), closed: str = Form(''), open_at: str = Form(''),
                 close_at: str = Form(''), note: str = Form('')):
    need_admin(request)
    check_csrf(request, csrf)
    try:
        date.fromisoformat(day)
        if not closed:
            if bk.hm(close_at) <= bk.hm(open_at):
                raise HTTPException(400, 'The closing time must be after the opening time.')
    except ValueError:
        raise HTTPException(400, 'Pick a date, and times like 09:00.')
    with connection() as c:
        c.execute('INSERT INTO date_overrides(day,closed,open_at,close_at,note) VALUES(?,?,?,?,?) ON CONFLICT(day) DO UPDATE SET '
                  'closed=excluded.closed, open_at=excluded.open_at, close_at=excluded.close_at, note=excluded.note',
                  (day, int(bool(closed)), open_at or None, close_at or None, clean(note, 120)))
    return back('/admin/availability#days')


@router.post('/availability/override/{day}/delete')
def delete_override(request: Request, day: str, csrf: str = Form('')):
    need_admin(request)
    check_csrf(request, csrf)
    with connection() as c:
        c.execute('DELETE FROM date_overrides WHERE day=?', (day,))
    return back('/admin/availability#days', 'deleted')


@router.post('/availability/block')
def add_block(request: Request, csrf: str = Form(''), day: str = Form(''), start_at: str = Form(''), end_at: str = Form(''),
              note: str = Form('')):
    need_admin(request)
    check_csrf(request, csrf)
    try:
        d = date.fromisoformat(day)
        if bk.hm(end_at) <= bk.hm(start_at):
            raise HTTPException(400, 'The block must end after it starts.')
    except ValueError:
        raise HTTPException(400, 'Pick a date, and times like 13:00.')
    with connection() as c:
        c.execute('INSERT INTO blocks(start_local,end_local,note,created_at) VALUES(?,?,?,?)',
                  (f'{d.isoformat()}T{start_at}', f'{d.isoformat()}T{end_at}', clean(note, 120), stamp()))
    return back('/admin/availability#blocks')


@router.post('/availability/block/{bid}/delete')
def delete_block(request: Request, bid: int, csrf: str = Form('')):
    need_admin(request)
    check_csrf(request, csrf)
    with connection() as c:
        c.execute('DELETE FROM blocks WHERE id=?', (bid,))
    return back('/admin/availability#blocks', 'deleted')


# ------------------------------------------------------------------ settings

@router.get('/site')
def site_page(request: Request, msg: str = ''):
    need_admin(request)
    with connection() as c:
        s = get_settings(c)
    return _render(request, 'admin/site.html', section='site', s=s, msg=msg)


@router.post('/settings/{group}')
async def save_settings(request: Request, group: str):
    need_admin(request)
    form = await request.form()
    check_csrf(request, form.get('csrf'))
    keys = SETTING_GROUPS.get(group)
    if not keys:
        raise HTTPException(404, 'Unknown settings group.')
    with connection() as c:
        with transaction(c):
            for k in keys:
                if k in FLAGS:
                    value = '1' if form.get(k) else '0'
                else:
                    value = clean(str(form.get(k, '')), 1500)
                if k in NUMERIC:
                    lo, hi = NUMERIC[k]
                    try:
                        value = str(max(lo, min(hi, int(value or lo))))
                    except ValueError:
                        raise HTTPException(400, f'{k.replace("_", " ").capitalize()} must be a whole number.')
                if k == 'service_mode' and value not in ('mobile', 'shop', 'both'):
                    raise HTTPException(400, 'Choose mobile, shop or both.')
                if k == 'email' and value and not email_ok(value):
                    raise HTTPException(400, 'Write a valid business email.')
                if k in ('instagram_url', 'facebook_url') and value and not value.startswith('https://'):
                    raise HTTPException(400, 'Links must start with https://')
                set_setting(c, k, value)
    target = '/admin/availability#rules' if group == 'rules' else f'/admin/site#{group}'
    return back(target)


# ------------------------------------------------------------------ photos

def _save_image(upload: UploadFile, data: bytes, stem: str) -> str:
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(400, 'Photos must be under 15 MB.')
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > Image.MAX_IMAGE_PIXELS:
            raise HTTPException(400, 'That photo is too large. Use one under 40 megapixels.')
        img.verify()
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert('RGB')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        raise HTTPException(400, 'That file is not a photo we can read. Use a JPG, PNG, HEIC-exported JPG or WebP.')
    for w in (480, 960, 1600):
        if w > img.width and w != 480:
            continue
        ww = min(w, img.width)
        out = img.resize((ww, round(img.height * ww / img.width)), Image.LANCZOS) if ww != img.width else img
        out.save(config.UPLOAD_DIR / f'{stem}-{ww}.webp', 'WEBP', quality=82, method=5)
    return f'/uploads/{stem}'


@router.get('/gallery')
def gallery(request: Request, msg: str = ''):
    need_admin(request)
    with connection() as c:
        rows = [dict(r) for r in c.execute('SELECT * FROM gallery ORDER BY sort_order, id')]
        posts = [dict(r) for r in c.execute('SELECT * FROM instagram_posts ORDER BY sort_order, id')]
    return _render(request, 'admin/gallery.html', section='gallery', rows=rows, posts=posts, msg=msg)


@router.post('/gallery')
async def add_gallery(request: Request, csrf: str = Form(''), title: str = Form(''), alt: str = Form(''), before_alt: str = Form(''),
                      featured: str = Form(''), after: UploadFile = File(...), before: UploadFile | None = File(None)):
    need_admin(request)
    check_csrf(request, csrf)
    if not clean(title, 100) or not clean(alt, 200):
        raise HTTPException(400, 'Write a title and describe what the photo shows.')
    stem = 'g' + secrets.token_hex(6)
    after_path = _save_image(after, await after.read(), stem + 'a')
    before_path = None
    if before is not None and before.filename:
        before_path = _save_image(before, await before.read(), stem + 'b')
    with connection() as c:
        c.execute('INSERT INTO gallery(title,alt,before_path,after_path,before_alt,featured,sort_order,created_at) VALUES(?,?,?,?,?,?,?,?)',
                  (clean(title, 100), clean(alt, 200), before_path, after_path, clean(before_alt, 200), int(bool(featured)), 50, stamp()))
    return back('/admin/gallery')


@router.post('/gallery/{gid}')
def edit_gallery(request: Request, gid: int, csrf: str = Form(''), title: str = Form(''), alt: str = Form(''), featured: str = Form(''),
                 sort_order: int = Form(0)):
    need_admin(request)
    check_csrf(request, csrf)
    with connection() as c:
        c.execute('UPDATE gallery SET title=?, alt=?, featured=?, sort_order=? WHERE id=?',
                  (clean(title, 100), clean(alt, 200), int(bool(featured)), sort_order, gid))
    return back('/admin/gallery')


@router.post('/gallery/{gid}/delete')
def delete_gallery(request: Request, gid: int, csrf: str = Form('')):
    need_admin(request)
    check_csrf(request, csrf)
    with connection() as c:
        c.execute('DELETE FROM gallery WHERE id=?', (gid,))
    return back('/admin/gallery', 'deleted')


@router.post('/instagram')
async def add_post(request: Request, csrf: str = Form(''), url: str = Form(''), caption: str = Form(''), alt: str = Form(''),
                   posted_on: str = Form(''), photo: UploadFile = File(...)):
    need_admin(request)
    check_csrf(request, csrf)
    url = clean(url, 300)
    if not url.startswith('https://www.instagram.com/'):
        raise HTTPException(400, 'Paste the post link from Instagram, starting with https://www.instagram.com/')
    path = _save_image(photo, await photo.read(), 'ig' + secrets.token_hex(6))
    with connection() as c:
        c.execute('INSERT INTO instagram_posts(image_path,alt,caption,url,posted_on,sort_order) VALUES(?,?,?,?,?,?)',
                  (path, clean(alt, 200), clean(caption, 600), url, clean(posted_on, 10), -1))
    return back('/admin/gallery#instagram')


@router.post('/instagram/{pid}/{action}')
def post_action(request: Request, pid: int, action: str, csrf: str = Form('')):
    need_admin(request)
    check_csrf(request, csrf)
    with connection() as c:
        if action == 'toggle':
            c.execute('UPDATE instagram_posts SET visible=1-visible WHERE id=?', (pid,))
        elif action == 'delete':
            c.execute('DELETE FROM instagram_posts WHERE id=?', (pid,))
        else:
            raise HTTPException(400, 'Unknown action.')
    return back('/admin/gallery#instagram')


# ------------------------------------------------------------------ reviews and messages

@router.get('/reviews')
def reviews(request: Request, msg: str = ''):
    need_admin(request)
    with connection() as c:
        rows = []
        for r in c.execute("SELECT * FROM reviews ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, id DESC"):
            d = dict(r)
            d['booking'] = bk.appointment_view(c.execute('SELECT * FROM appointments WHERE id=?', (r['appointment_id'],)).fetchone()) \
                if r['appointment_id'] else None
            # any bookings at all under this email, even if none completed yet
            d['other'] = c.execute("SELECT COUNT(*) FROM appointments WHERE email=? AND status!='cancelled'", (r['email'],)).fetchone()[0] if r['email'] else 0
            rows.append(d)
    return _render(request, 'admin/reviews.html', section='reviews', rows=rows, msg=msg)


@router.post('/reviews/{rid}/{action}')
def review_action(request: Request, rid: int, action: str, csrf: str = Form('')):
    need_admin(request)
    check_csrf(request, csrf)
    with connection() as c:
        if action in ('approved', 'denied', 'pending'):
            c.execute('UPDATE reviews SET status=? WHERE id=?', (action, rid))
        elif action == 'delete':
            c.execute('DELETE FROM reviews WHERE id=?', (rid,))
        else:
            raise HTTPException(400, 'Unknown action.')
    return back('/admin/reviews')


@router.get('/messages')
def messages(request: Request, msg: str = ''):
    need_admin(request)
    with connection() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM messages ORDER BY CASE status WHEN 'new' THEN 0 ELSE 1 END, id DESC LIMIT 200")]
    return _render(request, 'admin/messages.html', section='messages', rows=rows, msg=msg)


@router.post('/messages/{mid}/{action}')
def message_action(request: Request, mid: int, action: str, csrf: str = Form('')):
    need_admin(request)
    check_csrf(request, csrf)
    with connection() as c:
        if action in ('read', 'new', 'archived'):
            c.execute('UPDATE messages SET status=? WHERE id=?', (action, mid))
        elif action == 'delete':
            c.execute('DELETE FROM messages WHERE id=?', (mid,))
        else:
            raise HTTPException(400, 'Unknown action.')
    return back('/admin/messages')


# ------------------------------------------------------------------ system

@router.get('/system')
def system(request: Request, msg: str = ''):
    need_admin(request)
    with connection() as c:
        outbox = [dict(r) for r in c.execute('SELECT * FROM email_outbox ORDER BY id DESC LIMIT 40')]
        admins = [dict(r) for r in c.execute('SELECT id, email, created_at FROM admins ORDER BY id')]
    return _render(request, 'admin/system.html', section='system', outbox=outbox, admins=admins, smtp=config.smtp_configured(), msg=msg)


@router.post('/system/retry')
def retry(request: Request, csrf: str = Form('')):
    need_admin(request)
    check_csrf(request, csrf)
    with connection() as c:
        c.execute("UPDATE email_outbox SET attempts=0 WHERE state='failed'")
    send_pending()
    return back('/admin/system#email', 'retried')


@router.post('/system/password')
def admin_password(request: Request, csrf: str = Form(''), current: str = Form(''), new: str = Form('')):
    aid = need_admin(request)
    check_csrf(request, csrf)
    throttle(request, 'admin-pw', 6, 3600)
    if len(new) < 14:
        raise HTTPException(400, 'Admin passwords need at least 14 characters.')
    with connection() as c:
        row = c.execute('SELECT * FROM admins WHERE id=?', (aid,)).fetchone()
        if not verify_password(row['password_hash'], current):
            raise HTTPException(400, 'Your current password is not right.')
        c.execute('UPDATE admins SET password_hash=?, session_version=session_version+1 WHERE id=?', (hash_password(new), aid))
        request.session['admin_sv'] = c.execute('SELECT session_version FROM admins WHERE id=?', (aid,)).fetchone()[0]
    return back('/admin/system#security', 'password')


@router.post('/system/admins')
def add_admin(request: Request, csrf: str = Form(''), email: str = Form(''), password: str = Form('')):
    need_admin(request)
    check_csrf(request, csrf)
    email = clean(email, 254).lower()
    if not email_ok(email) or len(password) < 14:
        raise HTTPException(400, 'Write a valid email and a password of at least 14 characters.')
    if password_problem(password):
        raise HTTPException(400, password_problem(password))
    with connection() as c:
        c.execute('INSERT OR IGNORE INTO admins(email,password_hash,created_at) VALUES(?,?,?)', (email, hash_password(password), stamp()))
    return back('/admin/system#security', 'added')


@router.get('/export/bookings.csv')
def export(request: Request):
    need_admin(request)
    buf = io.StringIO()
    w = csv.writer(buf)
    safe = lambda v: "'" + v if isinstance(v, str) and v[:1] in ('=', '+', '-', '@', '\t', '\r') else v  # noqa: E731  (spreadsheet formula injection)
    w.writerow(['reference', 'start', 'minutes', 'status', 'package', 'size', 'vehicle', 'where', 'address', 'price', 'discount',
                'name', 'email', 'phone', 'notes', 'source', 'created'])
    with connection() as c:
        for r in c.execute('SELECT * FROM appointments ORDER BY start_local'):
            w.writerow([safe(v) for v in (r['reference'], r['start_local'], r['minutes'], r['status'], r['service_name'], r['size'], r['vehicle_text'],
                        r['location_type'], r['address'], bk.money(r['price_cents']), bk.money(r['discount_cents']), r['name'],
                        r['email'], r['phone'], r['notes'], r['source'], r['created_at'])])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type='text/csv',
                             headers={'Content-Disposition': f'attachment; filename="gem-bookings-{date.today()}.csv"'})


@router.get('/export/backup.sqlite3')
def backup(request: Request):
    need_admin(request)
    path = backup_copy()
    from starlette.background import BackgroundTask
    return FileResponse(path, filename=f'gem-backup-{datetime.now().strftime("%Y%m%d-%H%M")}.sqlite3',
                        background=BackgroundTask(path.unlink, missing_ok=True))
