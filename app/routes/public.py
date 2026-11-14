"""Public pages, contact, reviews and the booking flow (guest or signed in)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .. import booking as bk
from ..db import SIZE_LABEL, connection, get_settings, stamp, transaction
from ..mail import booking_emails, queue
from ..security import check_csrf, clean, email_ok, phone_ok, throttle

router = APIRouter()


def _render(request, name, **ctx):
    from ..main import render
    return render(request, name, **ctx)


def _gallery(c, featured_only=False):
    q = 'SELECT * FROM gallery' + (' WHERE featured=1' if featured_only else '') + ' ORDER BY sort_order, id'
    return [dict(r) for r in c.execute(q)]


def _modes(site: dict) -> list[str]:
    mode = site.get('service_mode', 'both')
    return ['mobile', 'shop'] if mode == 'both' else [mode if mode in ('mobile', 'shop') else 'mobile']


@router.get('/')
def home(request: Request):
    with connection() as c:
        services = bk.list_services(c)
        pairs = [g for g in _gallery(c) if g['before_path']][:3]
        singles = [g for g in _gallery(c) if not g['before_path']]
        reviews = [dict(r) for r in c.execute("SELECT * FROM reviews WHERE status='approved' ORDER BY id DESC LIMIT 3")]
        posts = [dict(r) for r in c.execute('SELECT * FROM instagram_posts WHERE visible=1 ORDER BY sort_order, id LIMIT 5')]
        opening = bk.next_opening(c, 150)
    return _render(request, 'public/home.html', services=services, pairs=pairs, singles=singles, reviews=reviews,
                   posts=posts, opening=opening, opening_text=_opening_text(opening))


def _opening_text(dt: datetime | None) -> str:
    if not dt:
        return ''
    today = bk.now_local().date()
    if dt.date() == today:
        day = 'Today'
    elif dt.date() == today + timedelta(days=1):
        day = 'Tomorrow'
    else:
        day = dt.strftime('%A')
    return f'{day} at {bk.nice_time(dt.time())}'


@router.get('/services')
def services(request: Request):
    with connection() as c:
        return _render(request, 'public/services.html', services=bk.list_services(c), addons=bk.list_addons(c),
                       pairs=[g for g in _gallery(c) if g['before_path']][:1])


@router.get('/work')
def work(request: Request):
    with connection() as c:
        items = _gallery(c)
        posts = [dict(r) for r in c.execute('SELECT * FROM instagram_posts WHERE visible=1 ORDER BY sort_order, id')]
    return _render(request, 'public/work.html', pairs=[g for g in items if g['before_path']],
                   singles=[g for g in items if not g['before_path']], posts=posts)


@router.get('/about')
def about(request: Request):
    return _render(request, 'public/about.html')


def _posts(c, limit=5):
    return [dict(r) for r in c.execute('SELECT * FROM instagram_posts WHERE visible=1 ORDER BY sort_order, id LIMIT ?', (limit,))]


@router.get('/contact')
def contact(request: Request, sent: int = 0):
    with connection() as c:
        posts = _posts(c)
    return _render(request, 'public/contact.html', sent=bool(sent), errors={}, form={}, posts=posts)


@router.post('/contact')
def contact_send(request: Request, csrf: str = Form(''), name: str = Form(''), email: str = Form(''), phone: str = Form(''),
                 topic: str = Form(''), message: str = Form(''), website: str = Form('')):
    check_csrf(request, csrf)
    if website:  # honeypot
        return RedirectResponse('/contact?sent=1', 303)
    form = {'name': clean(name, 100), 'email': clean(email, 254).lower(), 'phone': clean(phone, 40),
            'topic': clean(topic, 60), 'message': clean(message, 3000)}
    errors = {}
    if not form['name']:
        errors['name'] = 'Write your name so we know who to reply to.'
    if not email_ok(form['email']):
        errors['email'] = 'Write an email address with an @, like name@example.com.'
    if form['phone'] and not phone_ok(form['phone']):
        errors['phone'] = 'Write a phone number with its area code, or leave it empty.'
    if len(form['message']) < 5:
        errors['message'] = 'Write a few words about your car or your question.'
    if errors:
        with connection() as c:
            posts = _posts(c)
        return _render(request, 'public/contact.html', sent=False, errors=errors, form=form, posts=posts)
    throttle(request, 'contact', 6, 3600)
    with connection() as c:
        c.execute('INSERT INTO messages(name,email,phone,topic,body,created_at) VALUES(?,?,?,?,?,?)',
                  (form['name'], form['email'], form['phone'], form['topic'], form['message'], stamp()))
        site = get_settings(c)
        queue(c, site['email'], f"Website message from {form['name']}",
              f"{form['message']}\n\nFrom: {form['name']} <{form['email']}> {form['phone']}\nTopic: {form['topic'] or '-'}")
    return RedirectResponse('/contact?sent=1#message', 303)


@router.get('/reviews')
def reviews(request: Request, sent: int = 0):
    with connection() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM reviews WHERE status='approved' ORDER BY id DESC")]
    return _render(request, 'public/reviews.html', reviews=rows, sent=bool(sent), errors={}, form={})


@router.post('/reviews')
def review_send(request: Request, csrf: str = Form(''), name: str = Form(''), rating: str = Form(''), vehicle: str = Form(''),
                message: str = Form(''), website: str = Form('')):
    check_csrf(request, csrf)
    if website:
        return RedirectResponse('/reviews?sent=1', 303)
    form = {'name': clean(name, 80), 'rating': rating, 'vehicle': clean(vehicle, 80), 'message': clean(message, 1500)}
    errors = {}
    if not form['name']:
        errors['name'] = 'Write the name to show with your review.'
    if rating not in {'1', '2', '3', '4', '5'}:
        errors['rating'] = 'Choose a rating from 1 to 5 stars.'
    if len(form['message']) < 10:
        errors['message'] = 'Write at least a sentence about your detail.'
    if errors:
        with connection() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM reviews WHERE status='approved' ORDER BY id DESC")]
        return _render(request, 'public/reviews.html', reviews=rows, sent=False, errors=errors, form=form)
    throttle(request, 'review', 4, 3600)
    with connection() as c:
        c.execute('INSERT INTO reviews(name,rating,vehicle,message,created_at) VALUES(?,?,?,?,?)',
                  (form['name'], int(rating), form['vehicle'], form['message'], stamp()))
    return RedirectResponse('/reviews?sent=1#write', 303)


@router.get('/privacy')
def privacy(request: Request):
    return _render(request, 'public/legal.html', kind='privacy')


@router.get('/terms')
def terms(request: Request):
    return _render(request, 'public/legal.html', kind='terms')


# ------------------------------------------------------------------ booking

def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _ids(values) -> list[int]:
    return [i for i in (_int(v) for v in (values or [])) if i]


@router.get('/book')
def book(request: Request, service: str = '', size: str = '', day: str = '', vehicle: str = '', plan: str = ''):
    from .account import current_customer
    cust = current_customer(request)
    with connection() as c:
        site = get_settings(c)
        services = bk.list_services(c)
        addons = bk.list_addons(c)
        vehicles, addresses = [], []
        if cust:
            vehicles = [dict(r) for r in c.execute('SELECT * FROM vehicles WHERE customer_id=? AND archived=0 ORDER BY id', (cust['id'],))]
            addresses = [dict(r) for r in c.execute('SELECT * FROM addresses WHERE customer_id=? ORDER BY id', (cust['id'],))]
        sel_service = _int(service) or (next((s['id'] for s in services if s['slug'] == service), 0))
        sel_vehicle = next((v for v in vehicles if v['id'] == _int(vehicle)), None)
        sel_size = size if size in SIZE_LABEL else (sel_vehicle['size'] if sel_vehicle else '')
        times, sel_day = [], None
        try:
            sel_day = date.fromisoformat(day) if day else None
        except ValueError:
            sel_day = None
        if sel_service and sel_size and sel_day:
            try:
                q = bk.quote(c, sel_service, sel_size, settings=site)
                times = bk.slots(c, sel_day, q.minutes, site)
            except bk.BookingError:
                times = []
        returning = bk.is_returning(c, cust['email'] if cust else None, cust['id'] if cust else None)
    return _render(request, 'book/book.html', services=services, addons=addons, vehicles=vehicles, addresses=addresses,
                   modes=_modes(site), sel={'service': sel_service, 'size': sel_size, 'day': sel_day.isoformat() if sel_day else '',
                                            'vehicle': sel_vehicle['id'] if sel_vehicle else 0},
                   times=times, errors={}, form={}, returning=returning, today=bk.now_local().date())


@router.get('/api/days')
def api_days(service: int, size: str, addons: str = ''):
    with connection() as c:
        try:
            q = bk.quote(c, service, size, _ids(addons.split(',')))
        except bk.BookingError as e:
            raise HTTPException(400, str(e))
        return {'minutes': q.minutes, 'days': bk.month_availability(c, q.minutes, 42)}


@router.get('/api/slots')
def api_slots(service: int, size: str, day: str, addons: str = ''):
    try:
        d = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(400, 'Pick a day.')
    with connection() as c:
        try:
            q = bk.quote(c, service, size, _ids(addons.split(',')))
        except bk.BookingError as e:
            raise HTTPException(400, str(e))
        free = bk.slots(c, d, q.minutes)
    return {'day': day, 'label': bk.nice_day(d), 'times': [{'value': t, 'label': bk.nice_time(t)} for t in free]}


@router.get('/api/quote')
def api_quote(request: Request, service: int, size: str, addons: str = ''):
    from .account import current_customer
    cust = current_customer(request)
    with connection() as c:
        try:
            # only a signed-in customer's own history is looked up, so the estimate never reveals who has booked before
            q = bk.quote(c, service, size, _ids(addons.split(',')), email=cust['email'] if cust else None,
                         customer_id=cust['id'] if cust else None)
        except bk.BookingError as e:
            raise HTTPException(400, str(e))
    hours = q.minutes / 60
    return {'service': q.service['name'], 'size': SIZE_LABEL[q.size], 'minutes': q.minutes,
            'duration': f'About {hours:g} hours' if hours != 1 else 'About 1 hour',
            'price': bk.money(q.price_cents), 'discount': bk.money(q.discount_cents) if q.discount_cents else '',
            'total': bk.money(q.total_cents), 'offer': q.offer_applies}


@router.post('/book')
async def book_submit(request: Request):
    from .account import current_customer
    form = await request.form()
    check_csrf(request, form.get('csrf'))
    if form.get('website'):
        return RedirectResponse('/', 303)
    cust = current_customer(request)
    f = {k: clean(str(form.get(k, '')), 600 if k in ('notes',) else 200) for k in
         ('service', 'size', 'vehicle_id', 'year', 'make', 'model', 'color', 'location_type', 'address_id', 'street', 'town',
          'day', 'time', 'name', 'email', 'phone', 'notes', 'save_vehicle')}
    f['email'] = f['email'].lower()
    addon_ids = _ids(form.getlist('addons'))
    errors: dict[str, str] = {}
    with connection() as c:
        site = get_settings(c)
        modes = _modes(site)
        vehicle = None
        if cust and _int(f['vehicle_id']):
            vehicle = c.execute('SELECT * FROM vehicles WHERE id=? AND customer_id=?', (_int(f['vehicle_id']), cust['id'])).fetchone()
            if vehicle:
                f['size'] = vehicle['size']
        if not _int(f['service']):
            errors['service'] = 'Choose a package.'
        if f['size'] not in SIZE_LABEL:
            errors['size'] = 'Choose the size of your vehicle.'
        if not vehicle and (not f['make'] or not f['model']):
            errors['vehicle'] = 'Write the make and model, like Honda Civic.'
        loc = f['location_type'] if f['location_type'] in modes else (modes[0] if len(modes) == 1 else '')
        if not loc:
            errors['location_type'] = 'Choose where the detail happens.'
        address = ''
        if loc == 'mobile':
            saved = c.execute('SELECT * FROM addresses WHERE id=? AND customer_id=?', (_int(f['address_id']), cust['id'])).fetchone() if cust else None
            if saved:
                address = f"{saved['street']}, {saved['town']}" + (f" ({saved['notes']})" if saved['notes'] else '')
            elif f['street'] and f['town']:
                address = f"{f['street']}, {f['town']}"
            else:
                errors['address'] = 'Write the street and town where the car will be parked.'
        try:
            d = date.fromisoformat(f['day'])
        except ValueError:
            d = None
            errors['day'] = 'Pick a day.'
        if d and not f['time']:
            errors['time'] = 'Pick a start time.'
        name = cust['name'] if cust and not f['name'] else f['name']
        email = cust['email'] if cust and not f['email'] else f['email']
        phone = f['phone'] or (cust['phone'] if cust else '')
        if not name:
            errors['name'] = 'Write your name.'
        if not email_ok(email):
            errors['email'] = 'Write an email address with an @, like name@example.com.'
        if not phone_ok(phone):
            errors['phone'] = 'Write a phone number with its area code so we can text you on the day.'
        q = None
        if not errors.get('service') and not errors.get('size'):
            try:
                q = bk.quote(c, _int(f['service']), f['size'], addon_ids, email=email, customer_id=cust['id'] if cust else None, settings=site)
            except bk.BookingError as e:
                errors['service'] = str(e)
        if errors or not q or not d:
            return _rerender_book(request, c, site, cust, f, addon_ids, errors)
        throttle(request, 'book', 10, 3600)
        live = c.execute("SELECT COUNT(*) FROM appointments WHERE (email=? OR phone=?) AND status IN ('pending','confirmed') AND start_local>=?",
                         (email, phone, bk.now_local().strftime('%Y-%m-%dT%H:%M'))).fetchone()[0]
        if live >= 4:
            errors['time'] = f"You already have {live} upcoming bookings. Call or text {site['phone']} to add more."
            return _rerender_book(request, c, site, cust, f, addon_ids, errors)
        vtext = bk.vehicle_label(vehicle) if vehicle else ' '.join(x for x in (f['year'], f['make'], f['model']) if x) + (f", {f['color']}" if f['color'] else '')
        try:
            with transaction(c):
                vid = vehicle['id'] if vehicle else None
                if cust and not vehicle and f['save_vehicle']:
                    cur = c.execute('INSERT INTO vehicles(customer_id,year,make,model,color,size,created_at) VALUES(?,?,?,?,?,?,?)',
                                    (cust['id'], f['year'], f['make'], f['model'], f['color'], f['size'], stamp()))
                    vid = cur.lastrowid
                appt = bk.create_appointment(c, q=q, day=d, at=f['time'], name=name, email=email, phone=phone, vehicle_text=vtext,
                                             location_type=loc, address=address, notes=f['notes'],
                                             customer_id=cust['id'] if cust else None, vehicle_id=vid)
                booking_emails(c, appt, 'requested' if appt['status'] == 'pending' else 'confirmed')
        except bk.BookingError as e:
            errors['time'] = str(e)
            return _rerender_book(request, c, site, cust, f, addon_ids, errors)
    request.session['last_booking'] = appt['manage_token']
    return RedirectResponse(f"/booking/{appt['manage_token']}?new=1", 303)


def _rerender_book(request, c, site, cust, f, addon_ids, errors):
    from ..main import render
    vehicles, addresses = [], []
    if cust:
        vehicles = [dict(r) for r in c.execute('SELECT * FROM vehicles WHERE customer_id=? AND archived=0 ORDER BY id', (cust['id'],))]
        addresses = [dict(r) for r in c.execute('SELECT * FROM addresses WHERE customer_id=? ORDER BY id', (cust['id'],))]
    times = []
    try:
        if _int(f['service']) and f['size'] in SIZE_LABEL and f['day']:
            q = bk.quote(c, _int(f['service']), f['size'], addon_ids, settings=site)
            times = bk.slots(c, date.fromisoformat(f['day']), q.minutes, site)
    except (ValueError, bk.BookingError):
        times = []
    return render(request, 'book/book.html', status=400, services=bk.list_services(c), addons=bk.list_addons(c), vehicles=vehicles,
                  addresses=addresses, modes=_modes(site), times=times, errors=errors, form={**f, 'addons': addon_ids},
                  sel={'service': _int(f['service']), 'size': f['size'], 'day': f['day'], 'vehicle': _int(f['vehicle_id'])},
                  returning=bk.is_returning(c, cust['email'] if cust else None, cust['id'] if cust else None),
                  today=bk.now_local().date())


def _appt_by_token(c, token: str):
    row = c.execute('SELECT * FROM appointments WHERE manage_token=?', (token,)).fetchone()
    if not row:
        raise HTTPException(404, 'That booking link is not valid. Check the link in your email.')
    return row


@router.get('/booking/{token}')
def manage(request: Request, token: str, new: int = 0, day: str = '', changed: int = 0):
    with connection() as c:
        site = get_settings(c)
        a = _appt_by_token(c, token)
        view = bk.appointment_view(a)
        can_change = bk.can_customer_change(a, site)
        times, sel_day = [], None
        if can_change and day:
            try:
                sel_day = date.fromisoformat(day)
                times = bk.slots(c, sel_day, a['minutes'], site, exclude_id=a['id'])
            except ValueError:
                sel_day = None
        days = bk.month_availability(c, a['minutes'], 28) if can_change else []
    return _render(request, 'book/manage.html', a=view, new=bool(new), changed=bool(changed), can_change=can_change, times=times,
                   sel_day=sel_day.isoformat() if sel_day else '', days=days, token=token)


@router.post('/booking/{token}/cancel')
def manage_cancel(request: Request, token: str, csrf: str = Form('')):
    check_csrf(request, csrf)
    with connection() as c:
        site = get_settings(c)
        a = _appt_by_token(c, token)
        if not bk.can_customer_change(a, site):
            raise HTTPException(400, f"This booking can no longer be changed online. Call or text {site['phone']}.")
        c.execute("UPDATE appointments SET status='cancelled', updated_at=? WHERE id=?", (stamp(), a['id']))
        booking_emails(c, dict(c.execute('SELECT * FROM appointments WHERE id=?', (a['id'],)).fetchone()), 'cancelled')
    return RedirectResponse(f'/booking/{token}?changed=1', 303)


@router.post('/booking/{token}/reschedule')
def manage_reschedule(request: Request, token: str, csrf: str = Form(''), day: str = Form(''), at: str = Form('')):
    check_csrf(request, csrf)
    with connection() as c:
        site = get_settings(c)
        a = _appt_by_token(c, token)
        if not bk.can_customer_change(a, site):
            raise HTTPException(400, f"This booking can no longer be changed online. Call or text {site['phone']}.")
        try:
            d = date.fromisoformat(day)
            time.fromisoformat(at)
        except ValueError:
            raise HTTPException(400, 'Pick a day and a start time.')
        cutoff = int(site.get('cancel_cutoff_hours') or 24)
        if datetime.combine(d, time.fromisoformat(at)) - bk.now_local() < timedelta(hours=cutoff):
            raise HTTPException(400, f"Online changes need at least {cutoff} hours' notice. Call or text {site['phone']} for a sooner time.")
        with transaction(c):
            if at not in bk.slots(c, d, a['minutes'], site, exclude_id=a['id']):
                raise HTTPException(400, 'That time was just taken. Go back and pick another time.')
            status = 'pending' if site.get('booking_requires_approval') == '1' else a['status']
            c.execute('UPDATE appointments SET start_local=?, status=?, reminder_sent=0, updated_at=? WHERE id=?',
                      (f'{d.isoformat()}T{at}', status, stamp(), a['id']))
            booking_emails(c, dict(c.execute('SELECT * FROM appointments WHERE id=?', (a['id'],)).fetchone()), 'changed')
    return RedirectResponse(f'/booking/{token}?changed=1', 303)


@router.get('/api/next-opening')
def next_open():
    with connection() as c:
        dt = bk.next_opening(c, 150)
    return JSONResponse({'text': _opening_text(dt)})
