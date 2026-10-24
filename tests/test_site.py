"""Functional smoke and integrity checks on an isolated database."""
import os
import re
import tempfile
from datetime import timedelta
from pathlib import Path

os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='gem-test-')
os.environ['SECRET_KEY']='this-is-only-a-test-key-that-is-at-least-32-characters-long'
os.environ['ADMIN_EMAIL']='owner@example.com'
os.environ['ADMIN_PASSWORD']='A-Very-Strong-Test-Password-2026'
os.environ['COOKIE_SECURE']='false'

from fastapi.testclient import TestClient
from app import app, now, connection, appointment_slots


def token(html):
    return re.search(r'name="csrf" value="([^"]+)',html).group(1)


def next_open_date():
    for offset in range(3,10):
        day=(now()+timedelta(days=offset)).date().isoformat()
        with connection() as c:
            service=c.execute('SELECT * FROM services WHERE id=1').fetchone()
            slots=appointment_slots(c,service,day)
            if slots: return day,slots[0]
    raise AssertionError('No open date found')


def test_redesign_assets_and_navigation():
    with TestClient(app) as client:
        page=client.get('/').text
        assert 'brand-logo-only' in page
        assert '/static/css/redesign.css?v=6' in page
        assert 'class="brand-word"' not in page
        assert client.get('/static/css/redesign.css').status_code == 200
        response=client.get('/admin/login')
        assert response.status_code == 200


def test_every_public_page_and_assets():
    with TestClient(app) as client:
        for uri in ['/','/services','/gallery','/reviews','/contact','/book','/privacy','/terms','/admin/login','/health','/static/img/gem-logo.png','/static/css/site.css','/static/js/site.js']:
            assert client.get(uri).status_code==200,uri
        assert client.get('/admin',follow_redirects=False).status_code==303
        assert client.get('/api/availability',params={'day':'2020-01-01','service_id':1}).json()['slots']==[]


def test_bookings_conflicts_admin_and_reviews():
    with TestClient(app) as client:
        csrf=token(client.get('/book').text)
        day,time=next_open_date()
        body={'csrf':csrf,'service_id':'1','day':day,'at_time':time,'name':'Sample Customer','email':'customer@example.com','phone':'555-555-5555','vehicle':'Test car','notes':'Contact first'}
        r=client.post('/book',data=body,follow_redirects=False)
        assert r.status_code==303
        assert r.headers['location'].startswith('/book?success=1&ref=GEM-')
        with connection() as c:
            booking=c.execute('SELECT * FROM appointments ORDER BY id DESC LIMIT 1').fetchone()
            assert booking['status']=='confirmed'
            assert c.execute('SELECT COUNT(*) FROM email_outbox').fetchone()[0]==2
        assert client.post('/book',data=body,follow_redirects=False).status_code==409
        csrf=token(client.get('/reviews').text)
        body={'csrf':csrf,'name':'A Customer','rating':'5','message':'A helpful team and a great experience.'}
        assert client.post('/reviews',data=body,follow_redirects=False).status_code==303
        assert 'A helpful team' not in client.get('/reviews').text
        csrf=token(client.get('/admin/login').text)
        login=client.post('/admin/login',data={'csrf':csrf,'email':'owner@example.com','password':'A-Very-Strong-Test-Password-2026'},follow_redirects=False)
        assert login.status_code==303
        dashboard=client.get('/admin')
        assert dashboard.status_code==200
        csrf=token(dashboard.text)
        assert client.post('/admin/review',data={'csrf':csrf,'review_id':1,'status':'approved'},follow_redirects=False).status_code==303
        assert 'A helpful team' in client.get('/reviews').text
        assert client.post('/admin/settings',data={'csrf':csrf,'headline':'Made for performance','booking_requires_approval':'on'},follow_redirects=False).status_code==303
        assert 'Made for performance' in client.get('/').text
        with connection() as c:
            assert c.execute("SELECT value FROM settings WHERE key='booking_requires_approval'").fetchone()[0]=='1'
        assert client.post('/admin/appointment',data={'csrf':csrf,'appointment_id':booking['id'],'status':'cancelled'},follow_redirects=False).status_code==303
        assert time in client.get('/api/availability',params={'day':day,'service_id':1}).json()['slots']
        # Blocks must remove open times.
        assert client.post('/admin/block',data={'csrf':csrf,'day':day,'start_at':time,'end_at':'17:00','note':'Private job'},follow_redirects=False).status_code==303
        assert time not in client.get('/api/availability',params={'day':day,'service_id':1}).json()['slots']
        # No unsecured settings edits.
        assert client.post('/admin/settings',data={'csrf':'wrong','headline':'Spoofed'},follow_redirects=False).status_code!=303
