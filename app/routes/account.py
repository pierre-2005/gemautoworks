"""Customer accounts: sign up, sign in, password reset, garage, saved addresses and recurring plans."""
from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from .. import booking as bk
from ..db import SIZE_LABEL, connection, get_settings, stamp, transaction
from ..mail import link, queue
from ..security import (check_csrf, clean, email_ok, hash_password, password_problem, phone_ok, session_rotate,
                        throttle, token_hash, verify_password)

router = APIRouter(prefix='/account')


def current_customer(request: Request) -> dict | None:
    cid = request.session.get('customer_id')
    if not cid:
        return None
    with connection() as c:
        row = c.execute('SELECT id, email, name, phone FROM customers WHERE id=?', (cid,)).fetchone()
    if not row:
        request.session.pop('customer_id', None)
        return None
    return dict(row)


def need_customer(request: Request) -> dict:
    cust = current_customer(request)
    if not cust:
        raise HTTPException(303, headers={'Location': f'/account/login?next={request.url.path}'})
    return cust


def _render(request, name, **ctx):
    from ..main import render
    return render(request, name, **ctx)


def _safe_next(value: str) -> str:
    return value if value.startswith('/') and not value.startswith('//') else '/account'


def _claim_guest_bookings(c, cust_id: int, email: str) -> None:
    c.execute('UPDATE appointments SET customer_id=? WHERE customer_id IS NULL AND email=?', (cust_id, email))


@router.get('/signup')
def signup_page(request: Request, next: str = '/account'):
    return _render(request, 'account/auth.html', mode='signup', errors={}, form={}, next=_safe_next(next))


@router.post('/signup')
def signup(request: Request, csrf: str = Form(''), name: str = Form(''), email: str = Form(''), phone: str = Form(''),
           password: str = Form(''), next: str = Form('/account'), website: str = Form('')):
    check_csrf(request, csrf)
    if website:
        return RedirectResponse('/', 303)
    form = {'name': clean(name, 100), 'email': clean(email, 254).lower(), 'phone': clean(phone, 40)}
    errors = {}
    if not form['name']:
        errors['name'] = 'Write your name.'
    if not email_ok(form['email']):
        errors['email'] = 'Write an email address with an @, like name@example.com.'
    if form['phone'] and not phone_ok(form['phone']):
        errors['phone'] = 'Write a phone number with its area code, or leave it empty.'
    problem = password_problem(password)
    if problem:
        errors['password'] = problem
    if errors:
        return _render(request, 'account/auth.html', mode='signup', errors=errors, form=form, next=_safe_next(next))
    throttle(request, 'signup', 6, 3600)
    with connection() as c:
        existing = c.execute('SELECT id, password_hash FROM customers WHERE email=?', (form['email'],)).fetchone()
        if existing and existing['password_hash']:
            errors['email'] = 'That email already has an account. Sign in instead, or reset your password.'
            return _render(request, 'account/auth.html', mode='signup', errors=errors, form=form, next=_safe_next(next))
        with transaction(c):
            if existing:
                c.execute('UPDATE customers SET name=?, phone=?, password_hash=? WHERE id=?',
                          (form['name'], form['phone'], hash_password(password), existing['id']))
                cid = existing['id']
            else:
                cid = c.execute('INSERT INTO customers(email,password_hash,name,phone,created_at) VALUES(?,?,?,?,?)',
                                (form['email'], hash_password(password), form['name'], form['phone'], stamp())).lastrowid
            _claim_guest_bookings(c, cid, form['email'])
    session_rotate(request)
    request.session['customer_id'] = cid
    return RedirectResponse(_safe_next(next) + ('?welcome=1' if _safe_next(next) == '/account' else ''), 303)


@router.get('/login')
def login_page(request: Request, next: str = '/account', reset: int = 0):
    if current_customer(request):
        return RedirectResponse(_safe_next(next), 303)
    return _render(request, 'account/auth.html', mode='login', errors={}, form={}, next=_safe_next(next), reset=bool(reset))


@router.post('/login')
def login(request: Request, csrf: str = Form(''), email: str = Form(''), password: str = Form(''), next: str = Form('/account')):
    check_csrf(request, csrf)
    throttle(request, 'login', 10, 900)
    email = clean(email, 254).lower()
    with connection() as c:
        row = c.execute('SELECT id, password_hash FROM customers WHERE email=?', (email,)).fetchone()
        ok = verify_password(row['password_hash'] if row else None, password)
        if ok:
            c.execute('UPDATE customers SET last_login_at=? WHERE id=?', (stamp(), row['id']))
            _claim_guest_bookings(c, row['id'], email)
    if not ok:
        return _render(request, 'account/auth.html', mode='login', errors={'form': 'That email and password do not match. Try again or reset your password.'},
                       form={'email': email}, next=_safe_next(next))
    session_rotate(request)
    request.session['customer_id'] = row['id']
    return RedirectResponse(_safe_next(next), 303)


@router.post('/logout')
def logout(request: Request, csrf: str = Form('')):
    check_csrf(request, csrf)
    request.session.pop('customer_id', None)
    return RedirectResponse('/', 303)


@router.get('/forgot')
def forgot_page(request: Request, sent: int = 0):
    return _render(request, 'account/auth.html', mode='forgot', errors={}, form={}, sent=bool(sent), next='/account')


@router.post('/forgot')
def forgot(request: Request, csrf: str = Form(''), email: str = Form('')):
    check_csrf(request, csrf)
    throttle(request, 'forgot', 5, 3600)
    email = clean(email, 254).lower()
    with connection() as c:
        row = c.execute('SELECT id, name FROM customers WHERE email=? AND password_hash IS NOT NULL', (email,)).fetchone()
        if row:
            token = secrets.token_urlsafe(32)
            expires = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(timespec='seconds')
            c.execute('INSERT INTO password_resets(token_hash,customer_id,expires_at) VALUES(?,?,?)', (token_hash(token), row['id'], expires))
            queue(c, email, 'Reset your GEM Autoworks password',
                  f"Hi {row['name'].split(' ')[0]},\n\nUse this link within 2 hours to choose a new password:\n{link('/account/reset/' + token)}\n\n"
                  'If you did not ask for this, ignore this email.\n\nGEM Autoworks')
    # same answer either way, so the form does not reveal who has an account
    return RedirectResponse('/account/forgot?sent=1', 303)


def _reset_row(c, token: str):
    row = c.execute('SELECT * FROM password_resets WHERE token_hash=? AND used=0', (token_hash(token),)).fetchone()
    if not row or row['expires_at'] < datetime.now(timezone.utc).isoformat(timespec='seconds'):
        raise HTTPException(400, 'This reset link has expired or was already used. Ask for a new one.')
    return row


@router.get('/reset/{token}')
def reset_page(request: Request, token: str):
    with connection() as c:
        _reset_row(c, token)
    return _render(request, 'account/auth.html', mode='reset', errors={}, form={}, token=token, next='/account')


@router.post('/reset/{token}')
def reset(request: Request, token: str, csrf: str = Form(''), password: str = Form('')):
    check_csrf(request, csrf)
    problem = password_problem(password)
    with connection() as c:
        row = _reset_row(c, token)
        if problem:
            return _render(request, 'account/auth.html', mode='reset', errors={'password': problem}, form={}, token=token, next='/account')
        c.execute('UPDATE customers SET password_hash=? WHERE id=?', (hash_password(password), row['customer_id']))
        c.execute('UPDATE password_resets SET used=1 WHERE customer_id=?', (row['customer_id'],))
    return RedirectResponse('/account/login?reset=1', 303)


# ------------------------------------------------------------------ dashboard

@router.get('')
def dashboard(request: Request, welcome: int = 0, saved: str = ''):
    cust = need_customer(request)
    with connection() as c:
        site = get_settings(c)
        today = bk.now_local().strftime('%Y-%m-%dT00:00')
        rows = c.execute('SELECT * FROM appointments WHERE customer_id=? ORDER BY start_local', (cust['id'],)).fetchall()
        upcoming = [bk.appointment_view(r) for r in rows if r['start_local'] >= today and r['status'] in ('pending', 'confirmed', 'needs_time')]
        past = [bk.appointment_view(r) for r in reversed(rows) if not (r['start_local'] >= today and r['status'] in ('pending', 'confirmed', 'needs_time'))][:12]
        vehicles = [dict(r) for r in c.execute('SELECT * FROM vehicles WHERE customer_id=? AND archived=0 ORDER BY id', (cust['id'],))]
        addresses = [dict(r) for r in c.execute('SELECT * FROM addresses WHERE customer_id=? ORDER BY id', (cust['id'],))]
        plans = []
        for p in c.execute('''SELECT p.*, s.name AS service_name, v.make, v.model, v.year, v.nickname FROM plans p
                              JOIN services s ON s.id=p.service_id JOIN vehicles v ON v.id=p.vehicle_id
                              WHERE p.customer_id=? AND p.status!='cancelled' ORDER BY p.id''', (cust['id'],)):
            d = dict(p)
            nxt = next((a for a in upcoming if a['plan_id'] == p['id']), None)
            d['next'] = nxt
            plans.append(d)
        services = bk.list_services(c)
    for a in upcoming:
        a['can_change'] = bk.can_customer_change(a, site)
    return _render(request, 'account/dashboard.html', upcoming=upcoming, past=past, vehicles=vehicles, addresses=addresses,
                   plans=plans, services=services, welcome=bool(welcome), saved=saved, weekdays=bk.WEEKDAYS,
                   intervals=bk.INTERVALS, modes=_modes(site), errors={}, today=bk.now_local().date())


def _modes(site):
    mode = site.get('service_mode', 'both')
    return ['mobile', 'shop'] if mode == 'both' else [mode if mode in ('mobile', 'shop') else 'mobile']


@router.post('/profile')
def profile(request: Request, csrf: str = Form(''), name: str = Form(''), phone: str = Form('')):
    check_csrf(request, csrf)
    cust = need_customer(request)
    name, phone = clean(name, 100), clean(phone, 40)
    if not name or (phone and not phone_ok(phone)):
        raise HTTPException(400, 'Write your name, and a phone number with its area code (or leave the phone empty).')
    with connection() as c:
        c.execute('UPDATE customers SET name=?, phone=? WHERE id=?', (name, phone, cust['id']))
    return RedirectResponse('/account?saved=profile#profile', 303)


@router.post('/password')
def change_password(request: Request, csrf: str = Form(''), current: str = Form(''), new: str = Form('')):
    check_csrf(request, csrf)
    cust = need_customer(request)
    throttle(request, 'pw', 8, 3600)
    problem = password_problem(new)
    with connection() as c:
        row = c.execute('SELECT password_hash FROM customers WHERE id=?', (cust['id'],)).fetchone()
        if not verify_password(row['password_hash'], current):
            raise HTTPException(400, 'Your current password is not right. Go back and try again.')
        if problem:
            raise HTTPException(400, problem)
        c.execute('UPDATE customers SET password_hash=? WHERE id=?', (hash_password(new), cust['id']))
    return RedirectResponse('/account?saved=password#profile', 303)


# ------------------------------------------------------------------ garage

def _vehicle_form(year, make, model, color, size, nickname, notes):
    v = {'year': clean(year, 4), 'make': clean(make, 40), 'model': clean(model, 60), 'color': clean(color, 30),
         'size': size if size in SIZE_LABEL else '', 'nickname': clean(nickname, 40), 'notes': clean(notes, 300)}
    if not v['make'] or not v['model']:
        raise HTTPException(400, 'Write the make and model of the car, like Toyota RAV4.')
    if not v['size']:
        raise HTTPException(400, 'Choose the size of the car.')
    if v['year'] and not (v['year'].isdigit() and 1950 <= int(v['year']) <= date.today().year + 1):
        raise HTTPException(400, 'Write the year as four digits, like 2019.')
    return v


@router.post('/vehicles')
def add_vehicle(request: Request, csrf: str = Form(''), year: str = Form(''), make: str = Form(''), model: str = Form(''),
                color: str = Form(''), size: str = Form(''), nickname: str = Form(''), notes: str = Form('')):
    check_csrf(request, csrf)
    cust = need_customer(request)
    v = _vehicle_form(year, make, model, color, size, nickname, notes)
    with connection() as c:
        if c.execute('SELECT COUNT(*) FROM vehicles WHERE customer_id=? AND archived=0', (cust['id'],)).fetchone()[0] >= 20:
            raise HTTPException(400, 'Your garage holds up to 20 cars.')
        c.execute('INSERT INTO vehicles(customer_id,nickname,year,make,model,color,size,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                  (cust['id'], v['nickname'], v['year'], v['make'], v['model'], v['color'], v['size'], v['notes'], stamp()))
    return RedirectResponse('/account?saved=vehicle#garage', 303)


@router.post('/vehicles/{vid}')
def edit_vehicle(request: Request, vid: int, csrf: str = Form(''), year: str = Form(''), make: str = Form(''), model: str = Form(''),
                 color: str = Form(''), size: str = Form(''), nickname: str = Form(''), notes: str = Form('')):
    check_csrf(request, csrf)
    cust = need_customer(request)
    v = _vehicle_form(year, make, model, color, size, nickname, notes)
    with connection() as c:
        c.execute('UPDATE vehicles SET nickname=?, year=?, make=?, model=?, color=?, size=?, notes=? WHERE id=? AND customer_id=?',
                  (v['nickname'], v['year'], v['make'], v['model'], v['color'], v['size'], v['notes'], vid, cust['id']))
    return RedirectResponse('/account?saved=vehicle#garage', 303)


@router.post('/vehicles/{vid}/remove')
def remove_vehicle(request: Request, vid: int, csrf: str = Form('')):
    check_csrf(request, csrf)
    cust = need_customer(request)
    with connection() as c:
        if c.execute("SELECT 1 FROM plans WHERE vehicle_id=? AND status IN ('requested','active','paused')", (vid,)).fetchone():
            raise HTTPException(400, 'This car is on a cleaning plan. Cancel the plan first, then remove the car.')
        # archived, not deleted, so past bookings keep their car
        c.execute('UPDATE vehicles SET archived=1 WHERE id=? AND customer_id=?', (vid, cust['id']))
    return RedirectResponse('/account?saved=removed#garage', 303)


@router.post('/addresses')
def add_address(request: Request, csrf: str = Form(''), label: str = Form('Home'), street: str = Form(''), town: str = Form(''),
                notes: str = Form('')):
    check_csrf(request, csrf)
    cust = need_customer(request)
    street, town = clean(street, 120), clean(town, 60)
    if not street or not town:
        raise HTTPException(400, 'Write the street and the town.')
    with connection() as c:
        c.execute('INSERT INTO addresses(customer_id,label,street,town,notes,created_at) VALUES(?,?,?,?,?,?)',
                  (cust['id'], clean(label, 30) or 'Home', street, town, clean(notes, 200), stamp()))
    return RedirectResponse('/account?saved=address#addresses', 303)


@router.post('/addresses/{aid}/remove')
def remove_address(request: Request, aid: int, csrf: str = Form('')):
    check_csrf(request, csrf)
    cust = need_customer(request)
    with connection() as c:
        c.execute('DELETE FROM addresses WHERE id=? AND customer_id=?', (aid, cust['id']))
    return RedirectResponse('/account?saved=removed#addresses', 303)


# ------------------------------------------------------------------ plans

@router.post('/plans')
def request_plan(request: Request, csrf: str = Form(''), vehicle_id: int = Form(0), service_id: int = Form(0),
                 interval_weeks: int = Form(4), weekday: int = Form(0), preferred_time: str = Form('09:00'),
                 location_type: str = Form('mobile'), address_id: int = Form(0), start_on: str = Form(''), notes: str = Form('')):
    check_csrf(request, csrf)
    cust = need_customer(request)
    if interval_weeks not in (2, 4, 6, 8) or not 0 <= weekday <= 6:
        raise HTTPException(400, 'Choose how often and which day.')
    try:
        bk.hm(preferred_time)
        start = date.fromisoformat(start_on) if start_on else bk.now_local().date() + timedelta(days=1)
    except ValueError:
        raise HTTPException(400, 'Choose a start date and a usual time.')
    with connection() as c:
        site = get_settings(c)
        v = c.execute('SELECT * FROM vehicles WHERE id=? AND customer_id=? AND archived=0', (vehicle_id, cust['id'])).fetchone()
        if not v:
            raise HTTPException(400, 'Choose a car from your garage. Add one first if your garage is empty.')
        if not c.execute('SELECT 1 FROM services WHERE id=? AND active=1', (service_id,)).fetchone():
            raise HTTPException(400, 'Choose a package.')
        modes = _modes(site)
        loc = location_type if location_type in modes else modes[0]
        address = ''
        if loc == 'mobile':
            a = c.execute('SELECT * FROM addresses WHERE id=? AND customer_id=?', (address_id, cust['id'])).fetchone()
            if not a:
                raise HTTPException(400, 'Choose a saved address for the visits. Add one first under Addresses.')
            address = f"{a['street']}, {a['town']}" + (f" ({a['notes']})" if a['notes'] else '')
        now = stamp()
        c.execute('''INSERT INTO plans(customer_id,vehicle_id,service_id,interval_weeks,weekday,preferred_time,location_type,address,notes,
                     status,start_on,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (cust['id'], v['id'], service_id, interval_weeks, weekday, preferred_time, loc, address, clean(notes, 300),
                   'requested', start.isoformat(), now, now))
        queue(c, site['email'], f"New cleaning plan request from {cust['name']}",
              f"{cust['name']} asked for a plan: {bk.vehicle_label(v)}, every {interval_weeks} weeks on {bk.WEEKDAYS[weekday]} around "
              f"{bk.nice_time(preferred_time)}.\nApprove it here: {link('/admin/plans')}")
    return RedirectResponse('/account?saved=plan#plans', 303)


@router.post('/plans/{pid}/{action}')
def plan_action(request: Request, pid: int, action: str, csrf: str = Form('')):
    check_csrf(request, csrf)
    cust = need_customer(request)
    with connection() as c:
        p = c.execute('SELECT * FROM plans WHERE id=? AND customer_id=?', (pid, cust['id'])).fetchone()
        if not p:
            raise HTTPException(404, 'That plan was not found.')
        today = bk.now_local().strftime('%Y-%m-%dT00:00')
        with transaction(c):
            if action == 'pause' and p['status'] == 'active':
                c.execute("UPDATE plans SET status='paused', updated_at=? WHERE id=?", (stamp(), pid))
                c.execute("UPDATE appointments SET status='cancelled', updated_at=? WHERE plan_id=? AND start_local>=? AND status IN ('pending','confirmed','needs_time')",
                          (stamp(), pid, today))
            elif action == 'resume' and p['status'] == 'paused':
                c.execute("UPDATE plans SET status='active', start_on=?, updated_at=? WHERE id=?",
                          (bk.now_local().date().isoformat(), stamp(), pid))
                bk.fill_plan(c, pid)
            elif action == 'cancel' and p['status'] != 'cancelled':
                c.execute("UPDATE plans SET status='cancelled', updated_at=? WHERE id=?", (stamp(), pid))
                c.execute("UPDATE appointments SET status='cancelled', updated_at=? WHERE plan_id=? AND start_local>=? AND status IN ('pending','confirmed','needs_time')",
                          (stamp(), pid, today))
            elif action == 'skip' and p['status'] == 'active':
                nxt = c.execute("SELECT * FROM appointments WHERE plan_id=? AND start_local>=? AND status IN ('pending','confirmed','needs_time') ORDER BY start_local LIMIT 1",
                                (pid, today)).fetchone()
                if nxt:
                    c.execute("UPDATE appointments SET status='cancelled', updated_at=? WHERE id=?", (stamp(), nxt['id']))
                    bk.fill_plan(c, pid)
            else:
                raise HTTPException(400, 'That change is not available for this plan.')
    return RedirectResponse('/account?saved=plan#plans', 303)
