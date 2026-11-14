"""Email outbox: every message is queued in SQLite and sent by a background worker with retries,
so a slow or failing mail server never blocks a booking."""
from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import sqlite3
from datetime import timedelta
from email.message import EmailMessage

from . import config
from .booking import appointment_view, fill_all_plans, now_local
from .db import connection, get_settings, stamp
from .security import email_ok

log = logging.getLogger('gem.mail')


def queue(c: sqlite3.Connection, recipient: str, subject: str, body: str) -> None:
    if email_ok(recipient):
        c.execute('INSERT INTO email_outbox(recipient,subject,body,created_at) VALUES(?,?,?,?)', (recipient, subject, body, stamp()))


def link(path: str) -> str:
    return f'{config.PUBLIC_BASE_URL}{path}' if config.PUBLIC_BASE_URL else path


def _summary(a: dict) -> str:
    lines = [
        f"Reference: {a['reference']}",
        f"When: {a['day_text']} at {a['time_text']} (about {round(a['minutes'] / 60, 1):g} hours)",
        f"Package: {a['service_name']} ({a['size_text']})",
    ]
    if a['addon_list']:
        lines.append('Add-ons: ' + ', '.join(x['name'] for x in a['addon_list']))
    if a['vehicle_text']:
        lines.append(f"Vehicle: {a['vehicle_text']}")
    lines.append('Where: ' + (a['address'] if a['location_type'] == 'mobile' else 'Drop-off at the shop'))
    lines.append(f"Estimate: {a['total_text']}")
    return '\n'.join(lines)


def booking_emails(c: sqlite3.Connection, appt: dict, event: str) -> None:
    """event: requested | confirmed | changed | cancelled"""
    s = get_settings(c)
    a = appointment_view(appt)
    manage = link(f"/booking/{a['manage_token']}")
    heads = {
        'requested': ('Your detail request is in', 'Thanks for booking with GEM Autoworks. Pavly will confirm your time by email or text, usually the same day.'),
        'confirmed': ('Your detail is confirmed', 'Your detail is confirmed. We will send a reminder the day before.'),
        'changed': ('Your detail has a new time', 'Your appointment details changed. Here is the latest:'),
        'cancelled': ('Your detail is cancelled', 'Your appointment is cancelled. Book again any time.'),
    }
    title, intro = heads[event]
    body = f"Hi {a['name'].split(' ')[0]},\n\n{intro}\n\n{_summary(a)}\n\nSee or change it: {manage}\n\n" \
           f"Questions? Call or text {s['phone']}.\n\nGEM Autoworks"
    queue(c, a['email'], f"{title}: {a['day_text']}", body)
    owner = s.get('email')
    if owner:
        queue(c, owner, f"[{event}] {a['service_name']} for {a['name']}, {a['day_text']} {a['time_text']}",
              f"{_summary(a)}\nCustomer: {a['name']}, {a['email']}, {a['phone']}\nNotes: {a['notes'] or '-'}\n\n"
              f"Open the admin: {link('/admin/appointments')}")


def send_pending() -> int:
    if not config.smtp_configured():
        return 0
    sent = 0
    with connection() as c:
        rows = c.execute("SELECT * FROM email_outbox WHERE state IN ('pending','failed') AND attempts<6 ORDER BY id LIMIT 20").fetchall()
        for m in rows:
            try:
                msg = EmailMessage()
                msg['From'] = os.environ['SMTP_FROM']
                msg['To'] = m['recipient']
                msg['Subject'] = m['subject']
                msg.set_content(m['body'])
                host, port = os.environ['SMTP_HOST'], int(os.environ.get('SMTP_PORT', '465'))
                mode = os.environ.get('SMTP_SECURITY', 'ssl').lower()
                smtp = smtplib.SMTP_SSL(host, port, timeout=15) if mode == 'ssl' else smtplib.SMTP(host, port, timeout=15)
                with smtp:
                    if mode == 'starttls':
                        smtp.starttls()
                    smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
                    smtp.send_message(msg)
                c.execute("UPDATE email_outbox SET state='sent', attempts=attempts+1, last_error='' WHERE id=?", (m['id'],))
                sent += 1
            except Exception as e:  # noqa: BLE001 - any SMTP failure is retried later
                log.error('email #%s failed: %s', m['id'], type(e).__name__)
                c.execute("UPDATE email_outbox SET state='failed', attempts=attempts+1, last_error=? WHERE id=?",
                          (f'{type(e).__name__}: {e}'[:200], m['id']))
    return sent


def queue_reminders() -> int:
    """One reminder per confirmed visit, sent the day before."""
    n = 0
    with connection() as c:
        s = get_settings(c)
        if s.get('reminders_enabled') != '1':
            return 0
        now = now_local()
        hi = (now + timedelta(hours=30)).strftime('%Y-%m-%dT%H:%M')
        lo = (now + timedelta(hours=12)).strftime('%Y-%m-%dT%H:%M')
        for r in c.execute("SELECT * FROM appointments WHERE status='confirmed' AND reminder_sent=0 AND start_local BETWEEN ? AND ?", (lo, hi)).fetchall():
            a = appointment_view(r)
            queue(c, a['email'], f"Reminder: your detail is {a['day_text']} at {a['time_text']}",
                  f"Hi {a['name'].split(' ')[0]},\n\nA reminder for tomorrow:\n\n{_summary(a)}\n\n"
                  f"Need to change it? {link('/booking/' + a['manage_token'])}\n\nGEM Autoworks, {s['phone']}")
            c.execute('UPDATE appointments SET reminder_sent=1 WHERE id=?', (r['id'],))
            n += 1
    return n


def housekeeping() -> None:
    with connection() as c:
        fill_all_plans(c)
    queue_reminders()
    send_pending()


async def worker() -> None:
    while True:
        try:
            await asyncio.to_thread(housekeeping)
        except Exception:  # noqa: BLE001
            log.exception('housekeeping failed')
        await asyncio.sleep(120)
