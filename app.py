"""GEM Autoworks website and booking CMS. SQLite, FastAPI, server-side templates."""
from __future__ import annotations

import asyncio
import csv
import hmac
import io
import json
import logging
import os
import re
import secrets
import smtplib
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import FastAPI, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, UnidentifiedImageError
from starlette.middleware.sessions import SessionMiddleware
import customer_portal

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get('DATA_DIR', str(ROOT / 'data')))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / 'gem.sqlite3'
UPLOAD_DIR = DATA_DIR / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
SECRET_KEY = os.environ.get('SECRET_KEY', '')
if len(SECRET_KEY) < 32:
    raise RuntimeError('Set SECRET_KEY to a random value of at least 32 characters (see README).')
COOKIE_SECURE = os.environ.get('COOKIE_SECURE', 'true').lower() == 'true'
BUSINESS_TZ = os.environ.get('BUSINESS_TIMEZONE', 'America/New_York')
TZ = ZoneInfo(BUSINESS_TZ)
PH = PasswordHasher()
log = logging.getLogger('gem')
logging.basicConfig(level=logging.INFO)
RATE = {}

DEFAULTS = {
    'business_name': 'GEM Autoworks',
    'headline': 'Crafted for the drive.',
    'hero_eyebrow': 'GEM AUTOWORKS  /  APPOINTMENT-BASED',
    'hero_subtitle': 'Thoughtful automotive care, unmistakable attention to detail. Discover the GEM experience and reserve your next appointment.',
    'about_title': 'A higher standard of automotive care.',
    'about_text': 'At GEM Autoworks, every vehicle deserves thoughtful attention. Reach out to discuss your goals, explore our work, and book time with our team.',
    'phone': '(774) 291-1596',
    'email': 'gemautoworksllc@gmail.com',
    'instagram': 'https://www.instagram.com/gemautoworksllc/',
    'facebook': '',
    'location': 'Location shared when booking',
    'contact_note': 'Have a unique project in mind? Send us a message and we will help you plan the next step.',
    'booking_intro': 'Find a time that works for you. Select your appointment type, choose an available slot, and send us the details.',
    'booking_requires_approval': '0',
    'customer_accounts_enabled': '0',
    'booking_lead_hours': '2',
    'booking_window_days': '90',
    'slot_step_minutes': '30',
    'footer_caption': 'Attention to detail. Built into everything.',
    'seo_description': 'GEM Autoworks. Automotive appointments, consultations, projects, and customer reviews. Book a visit online.',
    'hero_image_path': '/static/img/showcase.webp',
    'feature_image_path': '/static/img/showcase.webp',
}

def db():
    conn = sqlite3.connect(str(DB_PATH), timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=15000')
    return conn

@contextmanager
def connection():
    conn = db()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with connection() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS admin_users (id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            duration INTEGER NOT NULL DEFAULT 30, price_note TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1, sort_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS hours (
            weekday INTEGER PRIMARY KEY, open_at TEXT NOT NULL, close_at TEXT NOT NULL,
            closed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS exceptions (
            day TEXT PRIMARY KEY, closed INTEGER NOT NULL DEFAULT 1,
            open_at TEXT, close_at TEXT, note TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS blocks (
            id INTEGER PRIMARY KEY, day TEXT NOT NULL, start_at TEXT NOT NULL, end_at TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY, reference TEXT UNIQUE NOT NULL, service_id INTEGER NOT NULL REFERENCES services(id),
            day TEXT NOT NULL, at_time TEXT NOT NULL, duration INTEGER NOT NULL,
            name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL,
            vehicle TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'confirmed', created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_appointments_day ON appointments(day,status);
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, rating INTEGER NOT NULL,
            message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS gallery (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, alt TEXT NOT NULL,
            image_path TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS email_outbox (
            id INTEGER PRIMARY KEY, recipient TEXT NOT NULL, subject TEXT NOT NULL,
            body TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        ''')
        c.executemany('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', DEFAULTS.items())
        customer_portal.init_customer_db(c)
        if not c.execute('SELECT 1 FROM services LIMIT 1').fetchone():
            c.executemany('INSERT INTO services(title,description,duration,price_note,sort_order) VALUES(?,?,?,?,?)', [
                ('Vehicle Consultation', 'Tell us about your vehicle and what you have in mind.', 30, 'Consultation', 1),
                ('Project Estimate', 'Discuss the scope, options, and next steps for a project.', 45, 'By quote', 2),
                ('General Appointment', 'Book a dedicated time to connect with the GEM Autoworks team.', 60, 'Contact for details', 3),
            ])
        if not c.execute('SELECT 1 FROM hours LIMIT 1').fetchone():
            for i in range(7):
                c.execute('INSERT INTO hours(weekday,open_at,close_at,closed) VALUES(?,?,?,?)', (i,'09:00','17:00',int(i==6)))
        if not c.execute('SELECT 1 FROM gallery LIMIT 1').fetchone():
            c.execute('INSERT INTO gallery(title,alt,image_path) VALUES(?,?,?)', ('Inspired by exceptional automotive design','Black and red supercar on display', '/static/img/showcase.webp'))
        if not c.execute('SELECT 1 FROM admin_users LIMIT 1').fetchone():
            admin_email = os.environ.get('ADMIN_EMAIL','').strip().lower()
            admin_pass = os.environ.get('ADMIN_PASSWORD','')
            if not admin_email or len(admin_pass) < 14:
                raise RuntimeError('First boot requires ADMIN_EMAIL and ADMIN_PASSWORD (at least 14 characters).')
            c.execute('INSERT INTO admin_users(email,password_hash) VALUES(?,?)',(admin_email,PH.hash(admin_pass)))
            log.warning('First admin account initialized. Remove ADMIN_PASSWORD from the environment after first successful boot if desired.')


def settings(c):
    return {r['key']:r['value'] for r in c.execute('SELECT key,value FROM settings')}

def now():
    return datetime.now(TZ)

def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def csrf_token(request):
    if 'csrf' not in request.session:
        request.session['csrf'] = secrets.token_urlsafe(32)
    return request.session['csrf']

def check_csrf(request, token):
    if not token or not hmac.compare_digest(str(request.session.get('csrf','')),str(token)):
        raise HTTPException(403,'Invalid form security token. Reload the page and try again.')

def admin_id(request):
    return request.session.get('admin_id')

def admin_only(request):
    if not admin_id(request):
        raise HTTPException(403,'Admin login required')

def safe_text(value,limit=300):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(value or '')).strip()[:limit]

def email_valid(value):
    return bool(re.fullmatch(r'[^\s@]{1,64}@[^\s@]{1,250}\.[^\s@]{2,30}',value))

def throttle(request, purpose, max_count=8, seconds=3600):
    # Per-process throttle. Place Cloudflare WAF / Turnstile in front for abuse at scale.
    # CF-Connecting-IP is trustworthy when the origin is bound to localhost and only tunnel-accessible.
    origin = request.headers.get('cf-connecting-ip','') or (request.client.host if request.client else 'unknown')
    key = (origin,purpose)
    t = datetime.now(timezone.utc).timestamp()
    hits = [x for x in RATE.get(key,[]) if x > t-seconds]
    if len(hits) >= max_count:
        raise HTTPException(429,'Too many attempts. Please try again later.')
    hits.append(t)
    RATE[key] = hits
    if len(RATE)>25000:
        RATE.clear()

def text_time(value):
    if not re.fullmatch(r'\d\d:\d\d',value or ''): raise ValueError('Invalid time')
    tm=datetime.strptime(value,'%H:%M').time()
    return tm.hour*60+tm.minute

def minutes_to_time(value):
    return f'{value//60:02}:{value%60:02}'

def appointment_slots(c,service,day,conf=None):
    config=conf or settings(c)
    try:
        day_date=date.fromisoformat(day)
        if day_date.isoformat()!=day: return []
    except ValueError:
        return []
    today=now().date()
    window=max(1,min(365,int(config.get('booking_window_days','90'))))
    if day_date < today or day_date > today+timedelta(days=window): return []
    row=c.execute('SELECT * FROM hours WHERE weekday=?',(day_date.weekday(),)).fetchone()
    exc=c.execute('SELECT * FROM exceptions WHERE day=?',(day,)).fetchone()
    if exc:
        if exc['closed']: return []
        begin,end=exc['open_at'],exc['close_at']
    else:
        if not row or row['closed']: return []
        begin,end=row['open_at'],row['close_at']
    try: start,finish=text_time(begin),text_time(end)
    except ValueError: return []
    step=max(15,min(120,int(config.get('slot_step_minutes','30'))))
    lead=max(0,min(168,int(config.get('booking_lead_hours','2'))))
    busy=c.execute("SELECT at_time,duration FROM appointments WHERE day=? AND status IN ('confirmed','pending')",(day,)).fetchall()
    blocked=c.execute('SELECT start_at,end_at FROM blocks WHERE day=?',(day,)).fetchall()
    result=[]
    for n in range(start,finish-service['duration']+1,step):
        candidate=datetime(day_date.year,day_date.month,day_date.day,n//60,n%60,tzinfo=TZ)
        if candidate < now()+timedelta(hours=lead): continue
        if any(n < text_time(r['at_time'])+r['duration'] and n+service['duration'] > text_time(r['at_time']) for r in busy): continue
        if any(n < text_time(r['end_at']) and n+service['duration'] > text_time(r['start_at']) for r in blocked): continue
        result.append(minutes_to_time(n))
    return result


def queue_email(c,recipient,subject,body):
    if email_valid(recipient):
        c.execute('INSERT INTO email_outbox(recipient,subject,body,created_at) VALUES(?,?,?,?)',(recipient,subject,body,stamp()))

def email_configured():
    return all(os.environ.get(k) for k in ('SMTP_HOST','SMTP_FROM','SMTP_USER','SMTP_PASSWORD'))

def send_pending():
    if not email_configured(): return 0
    delivered=0
    with connection() as c:
        unsent=c.execute("SELECT * FROM email_outbox WHERE state IN ('pending','failed') AND attempts<6 ORDER BY id LIMIT 15").fetchall()
        for msg in unsent:
            try:
                mail=EmailMessage()
                mail['From']=os.environ['SMTP_FROM']
                mail['To']=msg['recipient']
                mail['Subject']=msg['subject']
                mail.set_content(msg['body'])
                host=os.environ['SMTP_HOST']
                port=int(os.environ.get('SMTP_PORT','465'))
                if os.environ.get('SMTP_SECURITY','ssl').lower()=='ssl':
                    smtp=smtplib.SMTP_SSL(host,port,timeout=15)
                else:
                    smtp=smtplib.SMTP(host,port,timeout=15)
                with smtp:
                    if os.environ.get('SMTP_SECURITY','ssl').lower()=='starttls': smtp.starttls()
                    smtp.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD'])
                    smtp.send_message(mail)
                c.execute("UPDATE email_outbox SET state='sent',attempts=attempts+1,last_error='' WHERE id=?",(msg['id'],))
                delivered+=1
            except Exception as e:
                log.error('Email delivery failure, item #%s: %s',msg['id'],type(e).__name__)
                c.execute("UPDATE email_outbox SET state='failed',attempts=attempts+1,last_error=? WHERE id=?",(safe_text(type(e).__name__+': '+str(e),200),msg['id']))
    return delivered

async def email_worker():
    while True:
        try:
            await asyncio.to_thread(send_pending)
        except Exception:
            log.exception('Outbox worker failure')
        await asyncio.sleep(90)

async def care_reminder_worker():
    while True:
        try:
            await asyncio.to_thread(customer_portal.queue_care_reminders)
        except Exception:
            log.exception('Care reminders failed')
        await asyncio.sleep(3600)

@asynccontextmanager
async def lifespan(app:FastAPI):
    init_db()
    task=asyncio.create_task(email_worker())
    care_task=asyncio.create_task(care_reminder_worker())
    yield
    task.cancel()
    care_task.cancel()
    for job in (task,care_task):
        try: await job
        except asyncio.CancelledError: pass

app=FastAPI(title='GEM Autoworks',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
app.add_middleware(SessionMiddleware,secret_key=SECRET_KEY,session_cookie='gem_session',same_site='lax',https_only=COOKIE_SECURE,max_age=8*60*60)
app.include_router(customer_portal.router)
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
app.mount('/uploads',StaticFiles(directory=UPLOAD_DIR),name='uploads')
templates=Jinja2Templates(directory=str(ROOT/'templates'))

@app.middleware('http')
async def security_headers(request,call_next):
    try: content_length=int(request.headers.get('content-length','0') or 0)
    except (TypeError,ValueError): content_length=0
    if content_length>6_000_000:
        return JSONResponse({'error':'Request too large'},status_code=413)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; script-src 'self'; connect-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    if request.url.path.startswith('/admin') or request.url.path.startswith('/api') or request.url.path.startswith('/book'):
        response.headers['Cache-Control']='no-store'
    return response

@app.exception_handler(HTTPException)
async def friendly_http(request,exc):
    if request.url.path.startswith('/api'):
        return JSONResponse({'error':exc.detail},status_code=exc.status_code)
    if exc.status_code==403 and request.url.path.startswith('/admin') and not admin_id(request):
        return RedirectResponse('/admin/login',status_code=303)
    with connection() as c:
        return render(request,'error.html',c,status_code=exc.status_code,message=str(exc.detail),status=exc.status_code)

def render(request,template,c,status=200,**context):
    current=settings(c)
    customer=customer_portal.current_customer(__import__(__name__),request,c)
    customer_vehicles=(c.execute("SELECT * FROM customer_vehicles WHERE user_id=? ORDER BY id",(customer["id"],)).fetchall() if customer else [])
    values={'request':request,'site':current,'csrf':csrf_token(request),'admin_logged_in':bool(admin_id(request)),'customer_logged_in':bool(customer),'customer_vehicles':customer_vehicles,'current_year':now().year,'timezone':BUSINESS_TZ,**context}
    return templates.TemplateResponse(request,template,values,status_code=status)

@app.get('/',response_class=HTMLResponse)
def home(request:Request):
    with connection() as c:
        return render(request,'home.html',c,services=c.execute('SELECT * FROM services WHERE active=1 ORDER BY sort_order,id LIMIT 6').fetchall(),gallery=c.execute('SELECT * FROM gallery ORDER BY sort_order,id LIMIT 6').fetchall(),reviews=c.execute("SELECT * FROM reviews WHERE status='approved' ORDER BY id DESC LIMIT 3").fetchall())

@app.get('/services',response_class=HTMLResponse)
def services(request:Request):
    with connection() as c:
        return render(request,'services.html',c,services=c.execute('SELECT * FROM services WHERE active=1 ORDER BY sort_order,id').fetchall())

@app.get('/gallery',response_class=HTMLResponse)
def gallery(request:Request):
    with connection() as c:
        return render(request,'gallery.html',c,gallery=c.execute('SELECT * FROM gallery ORDER BY sort_order,id').fetchall())

@app.get('/reviews',response_class=HTMLResponse)
def reviews(request:Request):
    with connection() as c:
        return render(request,'reviews.html',c,reviews=c.execute("SELECT * FROM reviews WHERE status='approved' ORDER BY id DESC LIMIT 100").fetchall(),thank_you=request.query_params.get('thanks')=='1')

@app.post('/reviews')
def add_review(request:Request,name:str=Form(...),rating:int=Form(...),message:str=Form(...),csrf:str=Form(...),website:str=Form('')):
    check_csrf(request,csrf)
    if website: return RedirectResponse('/reviews?thanks=1',303)
    throttle(request,'reviews',4,3600)
    name=safe_text(name,80); message=safe_text(message,1200)
    if len(name)<2 or len(message)<15 or not 1<=rating<=5: raise HTTPException(400,'Please enter a name, rating, and review of at least 15 characters.')
    with connection() as c:
        c.execute('INSERT INTO reviews(name,rating,message,created_at) VALUES(?,?,?,?)',(name,rating,message,stamp()))
    return RedirectResponse('/reviews?thanks=1',303)

@app.get('/contact',response_class=HTMLResponse)
def contact(request:Request):
    with connection() as c: return render(request,'contact.html',c)

@app.get('/book',response_class=HTMLResponse)
def book(request:Request):
    with connection() as c:
        return render(request,'book.html',c,services=c.execute('SELECT * FROM services WHERE active=1 ORDER BY sort_order,id').fetchall(),today=now().date().isoformat(),max_day=(now().date()+timedelta(days=int(settings(c)['booking_window_days']))).isoformat(),success=request.query_params.get('success'),reference=request.query_params.get('ref'))

@app.get('/api/availability')
def availability(day:str,service_id:int):
    with connection() as c:
        service=c.execute('SELECT * FROM services WHERE id=? AND active=1',(service_id,)).fetchone()
        if not service: raise HTTPException(404,'Service not found')
        return {'slots':appointment_slots(c,service,day),'timezone':BUSINESS_TZ}

@app.post('/book')
def create_booking(request:Request,service_id:int=Form(...),day:str=Form(...),at_time:str=Form(...),name:str=Form(...),email:str=Form(...),phone:str=Form(...),vehicle:str=Form(''),notes:str=Form(''),csrf:str=Form(...),website:str=Form(''),vehicle_id:str=Form('')):
    check_csrf(request,csrf)
    if website: return RedirectResponse('/book?success=1',303)
    throttle(request,'bookings',6,3600)
    name=safe_text(name,100); email=safe_text(email,255).lower(); phone=safe_text(phone,50); vehicle=safe_text(vehicle,160); notes=safe_text(notes,1200)
    if len(name)<2 or not email_valid(email) or len(phone)<7: raise HTTPException(400,'Please enter a valid name, email, and phone number.')
    try: text_time(at_time)
    except ValueError: raise HTTPException(400,'Invalid appointment time.')
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')  # Serialize bookings to prevent two customers reserving same slot.
        try:
            service=c.execute('SELECT * FROM services WHERE id=? AND active=1',(service_id,)).fetchone()
            if not service: raise HTTPException(400,'Select a valid appointment type.')
            if at_time not in appointment_slots(c,service,day): raise HTTPException(409,'That time is no longer available. Please choose another slot.')
            cfg=settings(c)
            status='pending' if cfg.get('booking_requires_approval')=='1' else 'confirmed'
            reference='GEM-'+secrets.token_hex(4).upper()
            customer=customer_portal.current_customer(__import__(__name__),request,c)
            customer_id=customer['id'] if customer else None
            saved_vehicle_id=None
            if vehicle_id:
                if not customer or not vehicle_id.isdecimal():
                    raise HTTPException(400,'Sign in to use a saved vehicle.')
                owned=c.execute("SELECT * FROM customer_vehicles WHERE id=? AND user_id=?",(int(vehicle_id),customer_id)).fetchone()
                if not owned:
                    raise HTTPException(403,'That vehicle is not in your garage.')
                saved_vehicle_id=owned['id']
                vehicle=(' '.join(str(p) for p in (owned['year'],owned['make'],owned['model']) if p)).strip()
            c.execute('''INSERT INTO appointments(reference,service_id,day,at_time,duration,name,email,phone,vehicle,notes,status,created_at,updated_at,customer_id,vehicle_id)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(reference,service_id,day,at_time,service['duration'],name,email,phone,vehicle,notes,status,stamp(),stamp(),customer_id,saved_vehicle_id))
            summary=f'Reference: {reference}\nStatus: {status.title()}\nAppointment: {service["title"]}\nDate: {day}\nTime: {at_time} ({BUSINESS_TZ})\nDuration: {service["duration"]} minutes\nName: {name}\nEmail: {email}\nPhone: {phone}\nVehicle: {vehicle or "Not provided"}\nNotes: {notes or "None"}'
            queue_email(c,cfg['email'],f'New GEM booking: {reference}',f'A customer submitted a booking.\n\n{summary}\n\nManage it in your admin dashboard.')
            queue_email(c,email,f'Your GEM Autoworks booking {reference}',f'Hello {name},\n\nThank you for booking with GEM Autoworks. Your appointment is {status}.\n\n{summary}\n\nQuestions? Reply to {cfg["email"]} or call {cfg["phone"]}.')
            c.execute('COMMIT')
        except Exception:
            c.execute('ROLLBACK')
            raise
    return RedirectResponse('/book?success=1&ref='+reference,303)

@app.get('/privacy')
def privacy(request:Request):
    with connection() as c: return render(request,'legal.html',c,kind='privacy')

@app.get('/terms')
def terms(request:Request):
    with connection() as c: return render(request,'legal.html',c,kind='terms')

@app.get('/robots.txt')
def robots():
    return StreamingResponse(iter(['User-agent: *\nDisallow: /admin\nDisallow: /api\n']),media_type='text/plain')

@app.get('/health')
def health():
    with connection() as c: c.execute('SELECT 1').fetchone()
    return {'ok':True}

@app.get('/admin/login')
def login(request:Request):
    with connection() as c: return render(request,'login.html',c,error=request.query_params.get('error'))

@app.post('/admin/login')
def do_login(request:Request,email:str=Form(...),password:str=Form(...),csrf:str=Form(...)):
    check_csrf(request,csrf)
    throttle(request,'admin-login',12,3600)
    with connection() as c:
        user=c.execute('SELECT * FROM admin_users WHERE email=?',(email.strip().lower(),)).fetchone()
        valid=False
        if user:
            try: valid=PH.verify(user['password_hash'],password)
            except (VerifyMismatchError,VerificationError): pass
        if not valid: return RedirectResponse('/admin/login?error=1',303)
        request.session.clear()
        request.session['admin_id']=user['id']
        request.session['csrf']=secrets.token_urlsafe(32)
        return RedirectResponse('/admin',303)

@app.post('/admin/logout')
def logout(request:Request,csrf:str=Form(...)):
    check_csrf(request,csrf);request.session.clear()
    return RedirectResponse('/admin/login',303)

@app.get('/admin',response_class=HTMLResponse)
def dashboard(request:Request):
    admin_only(request)
    with connection() as c:
        appts=c.execute('SELECT a.*,s.title AS service_title FROM appointments a JOIN services s ON s.id=a.service_id ORDER BY a.day DESC,a.at_time DESC LIMIT 150').fetchall()
        return render(request,'admin.html',c,
            appointments=appts,
            services=c.execute('SELECT * FROM services ORDER BY sort_order,id').fetchall(),
            hours=c.execute('SELECT * FROM hours ORDER BY weekday').fetchall(),
            exceptions=c.execute('SELECT * FROM exceptions ORDER BY day DESC LIMIT 100').fetchall(),
            blocks=c.execute('SELECT * FROM blocks ORDER BY day DESC,start_at LIMIT 150').fetchall(),
            all_reviews=c.execute('SELECT * FROM reviews ORDER BY id DESC LIMIT 150').fetchall(),
            gallery=c.execute('SELECT * FROM gallery ORDER BY sort_order,id').fetchall(),
            outbox=c.execute('SELECT * FROM email_outbox ORDER BY id DESC LIMIT 30').fetchall(),
            counts=dict(c.execute("SELECT status,COUNT(*) FROM appointments GROUP BY status").fetchall()),
            flash=request.query_params.get('saved')=='1',email_ready=email_configured(),days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'])

def save_redirect(section): return RedirectResponse('/admin?saved=1#'+section,303)

@app.post('/admin/settings')
async def update_settings(request:Request,csrf:str=Form(...)):
    admin_only(request);check_csrf(request,csrf)
    ALLOWED={*DEFAULTS.keys()}-{'booking_requires_approval'}
    form=await request.form()
    with connection() as c:
        for key in ALLOWED:
            if key in form:
                val=safe_text(form[key],2000)
                if key in ('booking_lead_hours','booking_window_days','slot_step_minutes'):
                    bounds={'booking_lead_hours':(0,168),'booking_window_days':(1,365),'slot_step_minutes':(15,120)}[key]
                    try: number=int(val)
                    except ValueError: raise HTTPException(400,'Invalid scheduling number')
                    if not bounds[0]<=number<=bounds[1]: raise HTTPException(400,'Scheduling number out of range')
                    val=str(number)
                if key in ('instagram','facebook') and val and not val.startswith('https://'):
                    raise HTTPException(400,'Social links must begin with https://')
                if key in ('hero_image_path','feature_image_path'):
                    available={row['image_path'] for row in c.execute('SELECT image_path FROM gallery')}
                    available.add('/static/img/showcase.webp')
                    if val not in available: raise HTTPException(400,'Please select an existing gallery photo.')
                if key=='email' and not email_valid(val): raise HTTPException(400,'Invalid business email.')
                c.execute('UPDATE settings SET value=? WHERE key=?',(val,key))
        c.execute('UPDATE settings SET value=? WHERE key=?',('1' if form.get('booking_requires_approval') else '0','booking_requires_approval'))
        c.execute('UPDATE settings SET value=? WHERE key=?',('1' if form.get('customer_accounts_enabled') else '0','customer_accounts_enabled'))
    return save_redirect('settings')

@app.post('/admin/services')
def update_service(request:Request,csrf:str=Form(...),service_id:int=Form(0),title:str=Form(...),description:str=Form(''),duration:int=Form(30),price_note:str=Form(''),active:str=Form(''),sort_order:int=Form(0)):
    admin_only(request);check_csrf(request,csrf)
    title=safe_text(title,100)
    if len(title)<3 or duration not in (15,30,45,60,75,90,120,150,180,240): raise HTTPException(400,'Invalid service title or duration.')
    with connection() as c:
        args=(title,safe_text(description,400),duration,safe_text(price_note,80),int(active=='on'),sort_order)
        if service_id:
            c.execute('UPDATE services SET title=?,description=?,duration=?,price_note=?,active=?,sort_order=? WHERE id=?',(*args,service_id))
        else: c.execute('INSERT INTO services(title,description,duration,price_note,active,sort_order) VALUES(?,?,?,?,?,?)',args)
    return save_redirect('services')

@app.post('/admin/service/delete')
def delete_service(request:Request,csrf:str=Form(...),service_id:int=Form(...)):
    admin_only(request);check_csrf(request,csrf)
    with connection() as c:
        if c.execute('SELECT 1 FROM appointments WHERE service_id=? LIMIT 1',(service_id,)).fetchone():
            c.execute('UPDATE services SET active=0 WHERE id=?',(service_id,))
        else: c.execute('DELETE FROM services WHERE id=?',(service_id,))
    return save_redirect('services')

@app.post('/admin/hours')
async def update_hours(request:Request,csrf:str=Form(...)):
    admin_only(request);check_csrf(request,csrf)
    form=await request.form()
    with connection() as c:
        for i in range(7):
            opening=safe_text(form.get(f'open_{i}','09:00'),10)
            closing=safe_text(form.get(f'close_{i}','17:00'),10)
            if text_time(opening)>=text_time(closing): raise HTTPException(400,'Closing time must follow opening time.')
            c.execute('UPDATE hours SET open_at=?,close_at=?,closed=? WHERE weekday=?',(opening,closing,int(form.get(f'closed_{i}')=='on'),i))
    return save_redirect('hours')

@app.post('/admin/exceptions')
def add_exception(request:Request,csrf:str=Form(...),day:str=Form(...),closed:str=Form(''),open_at:str=Form('09:00'),close_at:str=Form('17:00'),note:str=Form('')):
    admin_only(request);check_csrf(request,csrf)
    try: date.fromisoformat(day)
    except ValueError: raise HTTPException(400,'Invalid calendar date.')
    if not closed and text_time(open_at)>=text_time(close_at): raise HTTPException(400,'Invalid hours')
    with connection() as c:
        c.execute('INSERT OR REPLACE INTO exceptions(day,closed,open_at,close_at,note) VALUES(?,?,?,?,?)',(day,int(closed=='on'),open_at,close_at,safe_text(note,160)))
    return save_redirect('hours')

@app.post('/admin/exception/delete')
def delete_exception(request:Request,csrf:str=Form(...),day:str=Form(...)):
    admin_only(request);check_csrf(request,csrf)
    with connection() as c: c.execute('DELETE FROM exceptions WHERE day=?',(day,))
    return save_redirect('hours')

@app.post('/admin/appointment')
def change_appointment(request:Request,csrf:str=Form(...),appointment_id:int=Form(...),status:str=Form(...)):
    admin_only(request);check_csrf(request,csrf)
    if status not in ('pending','confirmed','cancelled','completed'): raise HTTPException(400,'Invalid status')
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            ap=c.execute('SELECT a.*,s.title AS service_title FROM appointments a JOIN services s ON a.service_id=s.id WHERE a.id=?',(appointment_id,)).fetchone()
            if not ap: raise HTTPException(404,'Appointment not found')
            if status in ('pending','confirmed') and ap['status'] in ('cancelled','completed'):
                svc=c.execute('SELECT * FROM services WHERE id=?',(ap['service_id'],)).fetchone()
                # Reopening must not conflict with another existing booking.
                collision=c.execute("SELECT at_time,duration FROM appointments WHERE day=? AND status IN ('confirmed','pending') AND id<>?",(ap['day'],appointment_id)).fetchall()
                start=text_time(ap['at_time'])
                if any(start<text_time(x['at_time'])+x['duration'] and start+ap['duration']>text_time(x['at_time']) for x in collision):
                    raise HTTPException(409,'Cannot reopen this appointment; time is now occupied.')
            c.execute('UPDATE appointments SET status=?,updated_at=? WHERE id=?',(status,stamp(),appointment_id))
            if status!=ap['status']:
                queue_email(c,ap['email'],f'GEM Autoworks booking {ap["reference"]}: {status.title()}',f'Hello {ap["name"]},\n\nYour appointment {ap["reference"]} for {ap["service_title"]} on {ap["day"]} at {ap["at_time"]} ({BUSINESS_TZ}) is now {status}.\n\nQuestions? Contact {settings(c)["email"]}.')
            c.execute('COMMIT')
        except Exception:
            c.execute('ROLLBACK');raise
    return save_redirect('appointments')

@app.post('/admin/review')
def review_moderation(request:Request,csrf:str=Form(...),review_id:int=Form(...),status:str=Form(...)):
    admin_only(request);check_csrf(request,csrf)
    if status not in ('pending','approved','rejected'): raise HTTPException(400,'Invalid review status')
    with connection() as c: c.execute('UPDATE reviews SET status=? WHERE id=?',(status,review_id))
    return save_redirect('reviews')

@app.post('/admin/gallery')
async def add_gallery(request:Request,csrf:str=Form(...),title:str=Form(...),alt:str=Form(...),photo:UploadFile=File(...)):
    admin_only(request);check_csrf(request,csrf)
    payload=await photo.read(5_000_001)
    if len(payload)>5_000_000: raise HTTPException(413,'Image exceeds 5 MB.')
    try:
        with Image.open(io.BytesIO(payload)) as opened:
            if opened.format not in ('JPEG','PNG','WEBP'): raise ValueError('Not a supported image format')
            if opened.width*opened.height>30_000_000: raise ValueError('Image too large in pixels')
            im=opened.convert('RGB')
            im.thumbnail((2200,2200))
            filename=secrets.token_hex(16)+'.webp'
            im.save(UPLOAD_DIR/filename,format='WEBP',quality=83,method=5)
    except (UnidentifiedImageError,ValueError,OSError,Image.DecompressionBombError) as e:
        raise HTTPException(400,'Please upload a valid JPG, PNG, or WEBP photo.') from e
    with connection() as c:
        c.execute('INSERT INTO gallery(title,alt,image_path) VALUES(?,?,?)',(safe_text(title,120),safe_text(alt,180),'/uploads/'+filename))
    return save_redirect('gallery')

@app.post('/admin/gallery/delete')
def remove_gallery(request:Request,csrf:str=Form(...),gallery_id:int=Form(...)):
    admin_only(request);check_csrf(request,csrf)
    with connection() as c:
        photo=c.execute('SELECT image_path FROM gallery WHERE id=?',(gallery_id,)).fetchone()
        if photo:
            c.execute('DELETE FROM gallery WHERE id=?',(gallery_id,))
            if photo['image_path'].startswith('/uploads/'):
                (UPLOAD_DIR / Path(photo['image_path']).name).unlink(missing_ok=True)
    return save_redirect('gallery')

@app.post('/admin/password')
def change_password(request:Request,csrf:str=Form(...),current_password:str=Form(...),new_password:str=Form(...)):
    admin_only(request);check_csrf(request,csrf)
    if len(new_password)<14: raise HTTPException(400,'New password must have at least 14 characters')
    with connection() as c:
        current=c.execute('SELECT * FROM admin_users WHERE id=?',(admin_id(request),)).fetchone()
        try: PH.verify(current['password_hash'],current_password)
        except (VerifyMismatchError,VerificationError): raise HTTPException(400,'Current password incorrect')
        c.execute('UPDATE admin_users SET password_hash=? WHERE id=?',(PH.hash(new_password),admin_id(request)))
    return save_redirect('security')

@app.post('/admin/outbox/retry')
def retry_email(request:Request,csrf:str=Form(...)):
    admin_only(request);check_csrf(request,csrf)
    with connection() as c: c.execute("UPDATE email_outbox SET attempts=0,state='pending',last_error='' WHERE state='failed'")
    return save_redirect('emails')

@app.get('/admin/export/bookings.csv')
def export_bookings(request:Request):
    admin_only(request)
    with connection() as c:
        rows=c.execute('SELECT reference,day,at_time,name,email,phone,vehicle,notes,status,created_at FROM appointments ORDER BY day DESC').fetchall()
    output=io.StringIO(); writer=csv.writer(output)
    writer.writerow(['Reference','Date','Time','Name','Email','Phone','Vehicle','Notes','Status','Created'])
    for row in rows:
        writer.writerow(["'"+str(v) if str(v).startswith(('=','+','-','@')) else v for v in row])
    return StreamingResponse(iter([output.getvalue()]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="gem-bookings.csv"'})

@app.post('/admin/block')
def block_time(request:Request,csrf:str=Form(...),day:str=Form(...),start_at:str=Form(...),end_at:str=Form(...),note:str=Form('')):
    admin_only(request);check_csrf(request,csrf)
    try: date.fromisoformat(day)
    except ValueError: raise HTTPException(400,'Invalid date.')
    if text_time(start_at)>=text_time(end_at): raise HTTPException(400,'End time must follow start time.')
    with connection() as c:
        c.execute('INSERT INTO blocks(day,start_at,end_at,note,created_at) VALUES(?,?,?,?,?)',(day,start_at,end_at,safe_text(note,160),stamp()))
    return save_redirect('hours')

@app.post('/admin/block/delete')
def unblock_time(request:Request,csrf:str=Form(...),block_id:int=Form(...)):
    admin_only(request);check_csrf(request,csrf)
    with connection() as c: c.execute('DELETE FROM blocks WHERE id=?',(block_id,))
    return save_redirect('hours')

@app.post('/admin/appointment/reschedule')
def reschedule_appointment(request:Request,csrf:str=Form(...),appointment_id:int=Form(...),day:str=Form(...),at_time:str=Form(...)):
    admin_only(request);check_csrf(request,csrf)
    try: date.fromisoformat(day); text_time(at_time)
    except ValueError: raise HTTPException(400,'Invalid date or time')
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            appointment=c.execute('SELECT a.*,s.title AS service_title FROM appointments a JOIN services s ON a.service_id=s.id WHERE a.id=?',(appointment_id,)).fetchone()
            if not appointment: raise HTTPException(404,'Appointment not found')
            busy=c.execute("SELECT at_time,duration FROM appointments WHERE day=? AND status IN ('confirmed','pending') AND id<>?",(day,appointment_id)).fetchall()
            start=text_time(at_time)
            if any(start<text_time(r['at_time'])+r['duration'] and start+appointment['duration']>text_time(r['at_time']) for r in busy):
                raise HTTPException(409,'This time overlaps another appointment.')
            c.execute('UPDATE appointments SET day=?,at_time=?,updated_at=? WHERE id=?',(day,at_time,stamp(),appointment_id))
            cfg=settings(c)
            queue_email(c,appointment['email'],f'GEM Autoworks booking {appointment["reference"]} rescheduled',f'Hello {appointment["name"]},\n\nYour {appointment["service_title"]} appointment ({appointment["reference"]}) has been rescheduled to {day} at {at_time} ({BUSINESS_TZ}).\n\nFor questions, contact {cfg["email"]} or {cfg["phone"]}.')
            c.execute('COMMIT')
        except Exception:
            c.execute('ROLLBACK');raise
    return save_redirect('appointments')

@app.post('/admin/appointment/manual')
def manual_appointment(request:Request,csrf:str=Form(...),service_id:int=Form(...),day:str=Form(...),at_time:str=Form(...),name:str=Form(...),email:str=Form(...),phone:str=Form(...),vehicle:str=Form(''),notes:str=Form('')):
    admin_only(request);check_csrf(request,csrf)
    try: date.fromisoformat(day);start=text_time(at_time)
    except ValueError: raise HTTPException(400,'Invalid date or time')
    email=safe_text(email,255).lower(); name=safe_text(name,100);phone=safe_text(phone,50)
    if not email_valid(email) or len(name)<2 or len(phone)<7: raise HTTPException(400,'Provide a valid customer name, email and phone number.')
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            service=c.execute('SELECT * FROM services WHERE id=?',(service_id,)).fetchone()
            if not service: raise HTTPException(400,'Unknown service')
            busy=c.execute("SELECT at_time,duration FROM appointments WHERE day=? AND status IN ('confirmed','pending')",(day,)).fetchall()
            if any(start<text_time(r['at_time'])+r['duration'] and start+service['duration']>text_time(r['at_time']) for r in busy):
                raise HTTPException(409,'This time overlaps another booking.')
            ref='GEM-'+secrets.token_hex(4).upper()
            c.execute('INSERT INTO appointments(reference,service_id,day,at_time,duration,name,email,phone,vehicle,notes,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (ref,service_id,day,at_time,service['duration'],name,email,phone,safe_text(vehicle,160),safe_text(notes,1200),'confirmed',stamp(),stamp()))
            queue_email(c,email,f'Your GEM Autoworks booking {ref}',f'Hello {name},\n\nYour appointment {ref} for {service["title"]} is confirmed for {day} at {at_time} ({BUSINESS_TZ}).\n\nQuestions? Contact {settings(c)["email"]}.')
            c.execute('COMMIT')
        except Exception:
            c.execute('ROLLBACK');raise
    return save_redirect('appointments')
