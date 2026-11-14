"""Prices, availability and recurring plans.

Times are stored as local business time ('YYYY-MM-DDTHH:MM' in BUSINESS_TIMEZONE): one detailer, one
calendar, so local wall-clock time is what everyone reads. A slot is free when it fits the day's
hours, misses every block, and clears every live appointment by the travel buffer on both sides.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from . import config
from .db import SIZE_LABEL, get_settings, new_reference, stamp

LIVE = ('pending', 'confirmed')          # statuses that hold time on the calendar
STATUS_LABEL = {
    'pending': 'Waiting for confirmation', 'confirmed': 'Confirmed', 'completed': 'Completed',
    'cancelled': 'Cancelled', 'no_show': 'No-show', 'needs_time': 'Needs a time',
}


class BookingError(ValueError):
    pass


def now_local() -> datetime:
    return datetime.now(config.TZ).replace(tzinfo=None, second=0, microsecond=0)


def money(cents: int | None) -> str:
    if cents is None:
        return 'Price on request'
    return f'${cents / 100:,.0f}' if cents % 100 == 0 else f'${cents / 100:,.2f}'


def hm(value: str) -> int:
    t = time.fromisoformat(value)
    return t.hour * 60 + t.minute


def fmt_hm(minutes: int) -> str:
    return f'{minutes // 60:02}:{minutes % 60:02}'


def nice_time(value: str | time) -> str:
    t = value if isinstance(value, time) else time.fromisoformat(value)
    h = t.hour % 12 or 12
    return f'{h}:{t.minute:02} {"am" if t.hour < 12 else "pm"}' if t.minute else f'{h} {"am" if t.hour < 12 else "pm"}'


def nice_day(d: date) -> str:
    return d.strftime('%A, %B ') + str(d.day)


def parse_local(value: str) -> datetime:
    return datetime.fromisoformat(value)


# ------------------------------------------------------------------ services and prices

def list_services(c: sqlite3.Connection, active_only: bool = True) -> list[dict]:
    rows = c.execute('SELECT * FROM services' + (' WHERE active=1' if active_only else '') + ' ORDER BY sort_order, id').fetchall()
    prices = {}
    for p in c.execute('SELECT * FROM service_prices'):
        prices.setdefault(p['service_id'], {})[p['size']] = {'cents': p['price_cents'], 'minutes': p['minutes']}
    out = []
    for r in rows:
        d = dict(r)
        d['includes'] = json.loads(r['includes'] or '[]')
        d['prices'] = prices.get(r['id'], {})
        cents = [v['cents'] for v in d['prices'].values()]
        d['from_cents'] = min(cents) if cents else None
        out.append(d)
    return out


def list_addons(c: sqlite3.Connection, active_only: bool = True) -> list[dict]:
    q = 'SELECT * FROM addons' + (' WHERE active=1' if active_only else '') + ' ORDER BY sort_order, id'
    return [dict(r) for r in c.execute(q)]


@dataclass
class Quote:
    service: dict
    size: str
    addons: list[dict]
    minutes: int
    price_cents: int | None
    discount_cents: int
    offer_applies: bool

    @property
    def total_cents(self) -> int | None:
        return None if self.price_cents is None else self.price_cents - self.discount_cents


def is_returning(c: sqlite3.Connection, email: str | None, customer_id: int | None) -> bool:
    if customer_id:
        row = c.execute("SELECT 1 FROM appointments WHERE customer_id=? AND status IN ('confirmed','completed') LIMIT 1", (customer_id,)).fetchone()
        if row:
            return True
    if email:
        row = c.execute("SELECT 1 FROM appointments WHERE email=? AND status IN ('confirmed','completed') LIMIT 1", (email,)).fetchone()
        if row:
            return True
    return False


def quote(c: sqlite3.Connection, service_id: int, size: str, addon_ids: list[int] | None = None,
          email: str | None = None, customer_id: int | None = None, settings: dict | None = None) -> Quote:
    if size not in SIZE_LABEL:
        raise BookingError('Choose the size of your vehicle.')
    services = {s['id']: s for s in list_services(c)}
    service = services.get(service_id)
    if not service or size not in service['prices']:
        raise BookingError('Choose a package.')
    base = service['prices'][size]
    addons = [a for a in list_addons(c) if a['id'] in set(addon_ids or [])]
    minutes = base['minutes'] + sum(a['minutes'] for a in addons)
    price = base['cents']
    if any(a['price_cents'] is None for a in addons):
        price_known: int | None = None
    else:
        price_known = price + sum(a['price_cents'] for a in addons)
    s = settings or get_settings(c)
    offer = s.get('offer_enabled') == '1' and not is_returning(c, email, customer_id)
    pct = max(0, min(50, int(s.get('offer_percent') or 0)))
    discount = round((price_known or 0) * pct / 100) if offer and price_known else 0
    return Quote(service, size, addons, minutes, price_known, discount, offer and pct > 0)


# ------------------------------------------------------------------ availability

def day_hours(c: sqlite3.Connection, day: date) -> tuple[int, int] | None:
    o = c.execute('SELECT * FROM date_overrides WHERE day=?', (day.isoformat(),)).fetchone()
    if o:
        if o['closed'] or not o['open_at'] or not o['close_at']:
            return None
        return hm(o['open_at']), hm(o['close_at'])
    h = c.execute('SELECT * FROM hours WHERE weekday=?', (day.weekday(),)).fetchone()
    if not h or h['closed']:
        return None
    return hm(h['open_at']), hm(h['close_at'])


def _busy(c: sqlite3.Connection, day: date, buffer: int, exclude_id: int | None) -> list[tuple[int, int]]:
    """Minute ranges on `day` that a new job may not overlap (appointments carry the travel buffer)."""
    lo = datetime.combine(day, time()) - timedelta(days=1)
    hi = datetime.combine(day, time()) + timedelta(days=2)
    spans = []
    for r in c.execute('SELECT id, start_local, minutes FROM appointments WHERE status IN (?,?) AND start_local>=? AND start_local<?',
                       (*LIVE, lo.strftime('%Y-%m-%dT%H:%M'), hi.strftime('%Y-%m-%dT%H:%M'))):
        if exclude_id and r['id'] == exclude_id:
            continue
        s = parse_local(r['start_local'])
        e = s + timedelta(minutes=r['minutes'])
        spans.append((s - timedelta(minutes=buffer), e + timedelta(minutes=buffer)))
    for b in c.execute('SELECT start_local, end_local FROM blocks WHERE end_local>? AND start_local<?',
                       (lo.strftime('%Y-%m-%dT%H:%M'), hi.strftime('%Y-%m-%dT%H:%M'))):
        spans.append((parse_local(b['start_local']), parse_local(b['end_local'])))
    base = datetime.combine(day, time())
    out = []
    for s, e in spans:
        out.append((int((s - base).total_seconds() // 60), int((e - base).total_seconds() // 60)))
    return out


def slots(c: sqlite3.Connection, day: date, minutes: int, settings: dict | None = None,
          exclude_id: int | None = None, ignore_window: bool = False) -> list[str]:
    s = settings or get_settings(c)
    today = now_local()
    window = max(1, min(365, int(s.get('booking_window_days') or 60)))
    if not ignore_window and (day < today.date() or day > today.date() + timedelta(days=window)):
        return []
    hours = day_hours(c, day)
    if not hours:
        return []
    open_m, close_m = hours
    step = max(15, min(120, int(s.get('slot_step_minutes') or 30)))
    lead = max(0, min(168, int(s.get('booking_lead_hours') or 12)))
    buffer = max(0, min(180, int(s.get('travel_buffer_minutes') or 0)))
    earliest = today + timedelta(hours=lead)
    busy = _busy(c, day, buffer, exclude_id)
    out = []
    for m in range(open_m, close_m - minutes + 1, step):
        start = datetime.combine(day, time()) + timedelta(minutes=m)
        if not ignore_window and start < earliest:
            continue
        if any(m < e and m + minutes > b for b, e in busy):
            continue
        out.append(fmt_hm(m))
    return out


def month_availability(c: sqlite3.Connection, minutes: int, days: int = 42) -> list[dict]:
    s = get_settings(c)
    start = now_local().date()
    window = int(s.get('booking_window_days') or 60)
    out = []
    for i in range(min(days, window + 1)):
        d = start + timedelta(days=i)
        out.append({'day': d.isoformat(), 'label': nice_day(d), 'count': len(slots(c, d, minutes, s))})
    return out


def next_opening(c: sqlite3.Connection, minutes: int = 150) -> datetime | None:
    s = get_settings(c)
    start = now_local().date()
    for i in range(int(s.get('booking_window_days') or 60) + 1):
        d = start + timedelta(days=i)
        free = slots(c, d, minutes, s)
        if free:
            return datetime.combine(d, time.fromisoformat(free[0]))
    return None


# ------------------------------------------------------------------ appointments

def create_appointment(c: sqlite3.Connection, *, q: Quote, day: date, at: str, name: str, email: str, phone: str,
                       vehicle_text: str, location_type: str, address: str, notes: str,
                       customer_id: int | None = None, vehicle_id: int | None = None, plan_id: int | None = None,
                       status: str | None = None, source: str = 'web', check_free: bool = True) -> dict:
    s = get_settings(c)
    if check_free and at not in slots(c, day, q.minutes, s):
        raise BookingError('That time was just taken. Pick another time.')
    if status is None:
        status = 'pending' if s.get('booking_requires_approval') == '1' else 'confirmed'
    now = stamp()
    ref = new_reference(c)
    token = secrets.token_urlsafe(24)
    c.execute('''INSERT INTO appointments(reference,manage_token,customer_id,vehicle_id,plan_id,service_id,service_name,size,addons,
                 vehicle_text,location_type,address,start_local,minutes,status,price_cents,discount_cents,name,email,phone,notes,
                 source,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (ref, token, customer_id, vehicle_id, plan_id, q.service['id'], q.service['name'], q.size,
               json.dumps([{'id': a['id'], 'name': a['name']} for a in q.addons]), vehicle_text, location_type, address,
               f'{day.isoformat()}T{at}', q.minutes, status, q.price_cents, q.discount_cents, name, email, phone, notes,
               source, now, now))
    return dict(c.execute('SELECT * FROM appointments WHERE reference=?', (ref,)).fetchone())


def can_customer_change(appt: dict | sqlite3.Row, settings: dict) -> bool:
    if appt['status'] not in LIVE:
        return False
    cutoff = int(settings.get('cancel_cutoff_hours') or 24)
    return parse_local(appt['start_local']) - now_local() >= timedelta(hours=cutoff)


def appointment_view(a: sqlite3.Row | dict) -> dict:
    d = dict(a)
    start = parse_local(d['start_local'])
    d['start'] = start
    d['end'] = start + timedelta(minutes=d['minutes'])
    d['day_text'] = nice_day(start.date())
    d['time_text'] = nice_time(start.time())
    d['end_text'] = nice_time(d['end'].time())
    d['status_text'] = STATUS_LABEL.get(d['status'], d['status'].title())
    d['size_text'] = SIZE_LABEL.get(d['size'], d['size'])
    d['addon_list'] = json.loads(d.get('addons') or '[]')
    d['total_text'] = money(None if d['price_cents'] is None else d['price_cents'] - (d['discount_cents'] or 0))
    return d


# ------------------------------------------------------------------ recurring plans

def plan_dates(plan: sqlite3.Row | dict, after: date, count: int) -> list[date]:
    start = date.fromisoformat(plan['start_on'])
    # first occurrence: the plan's weekday on or after its start date
    first = start + timedelta(days=(plan['weekday'] - start.weekday()) % 7)
    step = timedelta(weeks=max(1, plan['interval_weeks']))
    d = first
    while d < after:
        d += step
    out = []
    while len(out) < count:
        out.append(d)
        d += step
    return out


def fill_plan(c: sqlite3.Connection, plan_id: int) -> list[dict]:
    """Keep the next N visits of an active plan on the calendar. A visit that cannot keep its usual time
    takes the nearest free time that day; with none free it is saved as 'needs_time' for the admin."""
    plan = c.execute('SELECT * FROM plans WHERE id=?', (plan_id,)).fetchone()
    if not plan or plan['status'] != 'active':
        return []
    s = get_settings(c)
    horizon = max(1, min(6, int(s.get('plan_horizon_visits') or 3)))
    vehicle = c.execute('SELECT * FROM vehicles WHERE id=?', (plan['vehicle_id'],)).fetchone()
    cust = c.execute('SELECT * FROM customers WHERE id=?', (plan['customer_id'],)).fetchone()
    if not vehicle or not cust:
        return []
    today = now_local().date()
    upcoming = c.execute("SELECT start_local, status FROM appointments WHERE plan_id=? AND start_local>=?",
                         (plan_id, today.isoformat())).fetchall()
    have = {r['start_local'][:10] for r in upcoming}
    holding = sum(1 for r in upcoming if r['status'] != 'cancelled')
    created = []
    for d in plan_dates(plan, today + timedelta(days=1), horizon + len(have)):
        if holding >= horizon:
            break
        if d.isoformat() in have:
            continue      # already scheduled or skipped by the customer (a cancelled visit stays skipped)
        q = quote(c, plan['service_id'], vehicle['size'], email=cust['email'], customer_id=cust['id'], settings=s)
        free = slots(c, d, q.minutes, s, ignore_window=True)
        free = [t for t in free if datetime.combine(d, time.fromisoformat(t)) > now_local()]
        want = hm(plan['preferred_time'])
        status, at, check = 'confirmed', plan['preferred_time'], True
        if free:
            at = min(free, key=lambda t: abs(hm(t) - want))
        else:
            status, check = 'needs_time', False
        vtext = vehicle_label(vehicle)
        appt = create_appointment(c, q=q, day=d, at=at, name=cust['name'], email=cust['email'], phone=cust['phone'],
                                  vehicle_text=vtext, location_type=plan['location_type'], address=plan['address'],
                                  notes=plan['notes'], customer_id=cust['id'], vehicle_id=vehicle['id'], plan_id=plan_id,
                                  status=status, source='plan', check_free=check)
        created.append(appt)
        holding += 1
    if created:
        c.execute('UPDATE plans SET updated_at=? WHERE id=?', (stamp(), plan_id))
    return created


def fill_all_plans(c: sqlite3.Connection) -> int:
    n = 0
    for p in c.execute("SELECT id FROM plans WHERE status='active'").fetchall():
        n += len(fill_plan(c, p['id']))
    return n


def vehicle_label(v: sqlite3.Row | dict) -> str:
    parts = [v['year'], v['make'], v['model']]
    text = ' '.join(p for p in parts if p)
    if v['color']:
        text += f', {v["color"]}'
    return text


WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
INTERVALS = [(2, 'Every 2 weeks'), (4, 'Every 4 weeks'), (6, 'Every 6 weeks'), (8, 'Every 8 weeks')]
