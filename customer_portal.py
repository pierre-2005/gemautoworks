"""Optional verified customer accounts, garages, and recurring care plans.

A strictly additive SQLite migration keeps existing GEM appointments intact.
No subscription charges or appointments are created automatically.
"""
from __future__ import annotations

import calendar
import hashlib
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

router = APIRouter()
DATE_FMT = "%Y-%m-%d"


def init_customer_db(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS customer_users (
          id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
          phone TEXT NOT NULL, password_hash TEXT NOT NULL,
          verified INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS customer_tokens (
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES customer_users(id) ON DELETE CASCADE,
          token_hash TEXT NOT NULL UNIQUE, purpose TEXT NOT NULL,
          expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tokens_user ON customer_tokens(user_id);
        CREATE TABLE IF NOT EXISTS customer_vehicles (
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES customer_users(id) ON DELETE CASCADE,
          year INTEGER, make TEXT NOT NULL, model TEXT NOT NULL, trim TEXT NOT NULL DEFAULT '',
          nickname TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_vehicles_user ON customer_vehicles(user_id);
        CREATE TABLE IF NOT EXISTS care_plans (
          id INTEGER PRIMARY KEY, service_id INTEGER NOT NULL REFERENCES services(id),
          name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          interval_months INTEGER NOT NULL DEFAULT 12,
          active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS care_enrollments (
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES customer_users(id),
          vehicle_id INTEGER NOT NULL REFERENCES customer_vehicles(id),
          plan_id INTEGER NOT NULL REFERENCES care_plans(id),
          next_due TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_enrollment_due ON care_enrollments(next_due,active);
        CREATE TABLE IF NOT EXISTS care_reminders (
          enrollment_id INTEGER NOT NULL REFERENCES care_enrollments(id),
          due_date TEXT NOT NULL, reminder_band INTEGER NOT NULL,
          PRIMARY KEY(enrollment_id,due_date,reminder_band)
        );
    """)
    existing = {r["name"] for r in c.execute("PRAGMA table_info(appointments)").fetchall()}
    if "customer_id" not in existing:
        c.execute("ALTER TABLE appointments ADD COLUMN customer_id INTEGER REFERENCES customer_users(id)")
    if "vehicle_id" not in existing:
        c.execute("ALTER TABLE appointments ADD COLUMN vehicle_id INTEGER REFERENCES customer_vehicles(id)")


def feature_on(core, c):
    return core.settings(c).get("customer_accounts_enabled", "0") == "1"


def require_feature(core, c):
    if not feature_on(core, c):
        raise HTTPException(404, "Customer accounts are not currently available.")


def current_customer(core, request, c):
    if not feature_on(core, c):
        return None
    user_id = request.session.get("customer_id")
    if not isinstance(user_id, int):
        return None
    return c.execute("SELECT * FROM customer_users WHERE id=? AND verified=1", (user_id,)).fetchone()


def require_customer(core, request, c):
    require_feature(core, c)
    user = current_customer(core, request, c)
    if user is None:
        raise HTTPException(401, "Sign in to manage your garage.")
    return user


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def base_url():
    import os
    return os.environ.get("PUBLIC_BASE_URL", "https://gemautoworks.overvault.ca").rstrip("/")


def make_token(core, c, user_id, purpose):
    token = secrets.token_urlsafe(32)
    expiry = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    c.execute("DELETE FROM customer_tokens WHERE user_id=? AND purpose=?", (user_id, purpose))
    c.execute("INSERT INTO customer_tokens(user_id,token_hash,purpose,expires_at) VALUES(?,?,?,?)",
              (user_id, hash_token(token), purpose, expiry))
    url = base_url() + "/account/" + ("verify" if purpose == "verify" else "reset") + "?token=" + token
    return url


def consume_token(c, token, purpose):
    if len(token) > 180:
        return None
    record = c.execute("""SELECT t.id AS token_id,t.expires_at,u.* FROM customer_tokens t
                          JOIN customer_users u ON u.id=t.user_id
                          WHERE t.token_hash=? AND t.purpose=?""", (hash_token(token), purpose)).fetchone()
    if not record or datetime.fromisoformat(record["expires_at"]) < datetime.now(timezone.utc):
        return None
    c.execute("DELETE FROM customer_tokens WHERE id=?", (record["token_id"],))
    return record


def plus_months(value, months):
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def queue_care_reminders():
    """Idempotent 30-day, 7-day, and due-date reminders, without auto-booking."""
    import app as core
    if not core.email_configured():
        return 0
    today = core.now().date()
    count = 0
    with core.connection() as c:
        if not feature_on(core, c):
            return 0
        rows = c.execute("""SELECT e.id,e.next_due,u.email,u.name,v.year,v.make,v.model,
                          p.name AS plan_name,s.title AS service_name
                          FROM care_enrollments e
                          JOIN customer_users u ON u.id=e.user_id
                          JOIN customer_vehicles v ON v.id=e.vehicle_id
                          JOIN care_plans p ON p.id=e.plan_id
                          JOIN services s ON s.id=p.service_id
                          WHERE e.active=1 AND u.verified=1 AND p.active=1""").fetchall()
        for r in rows:
            days = (date.fromisoformat(r["next_due"]) - today).days
            if not 0 <= days <= 30:
                continue
            band = 30 if days > 7 else (7 if days > 0 else 0)
            sent = c.execute("""INSERT OR IGNORE INTO care_reminders(enrollment_id,due_date,reminder_band)
                                VALUES(?,?,?)""", (r["id"],r["next_due"],band))
            if not sent.rowcount:
                continue
            core.queue_email(c, r["email"], f"GEM care reminder: {r['plan_name']}",
                f"Hello {r['name']},\n\nYour {r['plan_name']} for your {r['year'] or ''} {r['make']} {r['model']} "
                f"is coming due on {r['next_due']}.\n\nPlease book a time at {base_url()}/book. "
                "This reminder does not reserve an appointment or charge you automatically.")
            count += 1
    return count


def _format_vehicle(r):
    return " ".join(x for x in (str(r["year"] or ""), r["make"], r["model"], r["trim"]) if x).strip()


def _vehicle_from_form(core, form, index):
    years = form.getlist("vehicle_year")
    makes = form.getlist("vehicle_make")
    models = form.getlist("vehicle_model")
    if index >= len(makes) or index >= len(models):
        return None
    make = core.safe_text(makes[index], 60)
    model = core.safe_text(models[index], 60)
    if not make and not model:
        return None
    if len(make) < 2 or len(model) < 1:
        raise HTTPException(400, "Enter a make and model for each vehicle.")
    year_value = str(years[index]).strip() if index < len(years) else ""
    if year_value:
        if not year_value.isdecimal() or not 1900 <= int(year_value) <= date.today().year + 2:
            raise HTTPException(400, "Please enter a valid vehicle year.")
        year_value = int(year_value)
    else:
        year_value = None
    return (year_value, make, model)


@router.get("/account")
def account(request: Request):
    import app as core
    with core.connection() as c:
        user = require_customer(core, request, c)
        vehicles = c.execute("SELECT * FROM customer_vehicles WHERE user_id=? ORDER BY id", (user["id"],)).fetchall()
        plans = c.execute("""SELECT e.*,p.name AS plan_name,p.interval_months,s.title AS service_title,
                                    v.year,v.make,v.model
                             FROM care_enrollments e JOIN care_plans p ON e.plan_id=p.id
                             JOIN services s ON p.service_id=s.id
                             JOIN customer_vehicles v ON e.vehicle_id=v.id
                             WHERE e.user_id=? ORDER BY e.active DESC,e.next_due""",(user["id"],)).fetchall()
        types = c.execute("""SELECT p.*,s.title AS service_title FROM care_plans p
                            JOIN services s ON s.id=p.service_id WHERE p.active=1
                            ORDER BY p.id""").fetchall()
        appointments = c.execute("""SELECT a.*,s.title AS service_title FROM appointments a
                                    JOIN services s ON a.service_id=s.id
                                    WHERE a.customer_id=? ORDER BY a.day DESC LIMIT 60""",(user["id"],)).fetchall()
        return core.render(request, "account.html", c, customer=user, vehicles=vehicles,
                           enrollments=plans, plan_types=types, appointments=appointments,
                           saved=request.query_params.get("saved")=="1",today=core.now().date().isoformat())


@router.get("/account/login")
def customer_login(request: Request):
    import app as core
    with core.connection() as c:
        require_feature(core, c)
        if current_customer(core, request, c):
            return RedirectResponse("/account",303)
        return core.render(request, "account_auth.html", c, mode="login",
                           error=request.query_params.get("error"))


@router.post("/account/login")
def customer_login_post(request: Request, csrf: str=Form(...), email: str=Form(...), password: str=Form(...)):
    import app as core
    core.check_csrf(request,csrf)
    core.throttle(request,"customer-login",10,3600)
    with core.connection() as c:
        require_feature(core,c)
        user = c.execute("SELECT * FROM customer_users WHERE email=?", (email.strip().lower(),)).fetchone()
        valid = False
        if user:
            try:
                valid = core.PH.verify(user["password_hash"],password)
            except (core.VerifyMismatchError,core.VerificationError):
                pass
        if not valid or not user["verified"]:
            return RedirectResponse("/account/login?error=1",303)
        request.session.clear()
        request.session["customer_id"] = user["id"]
        request.session["csrf"] = secrets.token_urlsafe(32)
    return RedirectResponse("/account",303)


@router.get("/account/register")
def register(request: Request):
    import app as core
    with core.connection() as c:
        require_feature(core,c)
        return core.render(request, "account_auth.html", c, mode="register")


@router.post("/account/register")
async def register_post(request: Request, csrf: str=Form(...)):
    import app as core
    core.check_csrf(request, csrf)
    core.throttle(request,"customer-register",5,3600)
    form = await request.form()
    email = core.safe_text(form.get("email"),255).lower()
    name = core.safe_text(form.get("name"),100)
    phone = core.safe_text(form.get("phone"),50)
    password = str(form.get("password",""))
    if not core.email_valid(email) or len(name)<2 or len(phone)<7 or len(password)<12 or len(password)>128:
        raise HTTPException(400,"Please enter a valid name, email, phone, and password (12 or more characters).")
    vehicle_count = len(form.getlist("vehicle_make"))
    if vehicle_count>6:
        raise HTTPException(400,"You can add up to six vehicles during registration.")
    vehicles = [v for i in range(vehicle_count) if (v := _vehicle_from_form(core,form,i))]
    with core.connection() as c:
        require_feature(core,c)
        if not core.email_configured():
            raise HTTPException(503, "Account registration requires email verification. Please contact GEM Autoworks while email is unavailable.")
        c.execute("BEGIN IMMEDIATE")
        try:
            exists = c.execute("SELECT id FROM customer_users WHERE email=?", (email,)).fetchone()
            if exists:
                original=c.execute("SELECT * FROM customer_users WHERE id=?",(exists["id"],)).fetchone()
                if not original["verified"]:
                    url=make_token(core,c,original["id"],"verify")
                    core.queue_email(c,email,"Verify your GEM Autoworks account",f"Hello,\n\nConfirm your email within two hours:\n{url}\n\nIgnore this if you did not register.")
            else:
                cur = c.execute("""INSERT INTO customer_users(email,name,phone,password_hash,created_at)
                                   VALUES(?,?,?,?,?)""",(email,name,phone,core.PH.hash(password),core.stamp()))
                for year,make,model in vehicles:
                    c.execute("""INSERT INTO customer_vehicles(user_id,year,make,model,created_at)
                                 VALUES(?,?,?,?,?)""",(cur.lastrowid,year,make,model,core.stamp()))
                link = make_token(core,c,cur.lastrowid,"verify")
                core.queue_email(c,email,"Verify your GEM Autoworks account",
                    f"Hello {name},\n\nConfirm your email address using this link (valid 2 hours):\n{link}\n\n"
                    "If you did not request an account, ignore this message.")
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
        return core.render(request,"account_auth.html",c,mode="check")


@router.get("/account/verify")
def verify_account(request: Request, token: str=""):
    import app as core
    with core.connection() as c:
        require_feature(core,c)
        record = consume_token(c, token, "verify")
        if not record:
            raise HTTPException(400,"Verification link expired or invalid. Contact GEM Autoworks for assistance.")
        c.execute("UPDATE customer_users SET verified=1 WHERE id=?",(record["id"],))
        request.session.clear()
        request.session["customer_id"] = record["id"]
        request.session["csrf"] = secrets.token_urlsafe(32)
    return RedirectResponse("/account",303)


@router.get("/account/forgot")
def forgot(request: Request):
    import app as core
    with core.connection() as c:
        require_feature(core,c)
        return core.render(request,"account_auth.html",c,mode="forgot")


@router.post("/account/forgot")
def forgot_post(request: Request,csrf: str=Form(...),email: str=Form(...)):
    import app as core
    core.check_csrf(request,csrf)
    core.throttle(request,"customer-reset",5,3600)
    with core.connection() as c:
        require_feature(core,c)
        user = c.execute("SELECT * FROM customer_users WHERE email=? AND verified=1",(email.strip().lower(),)).fetchone()
        if user and core.email_configured():
            url = make_token(core,c,user["id"],"reset")
            core.queue_email(c,user["email"],"Reset your GEM Autoworks password",
                             f"Use this link to reset your password (valid 2 hours):\n{url}\n\n"
                             "If you did not request it, ignore this message.")
        return core.render(request,"account_auth.html",c,mode="check")


@router.get("/account/reset")
def reset(request: Request, token: str=""):
    import app as core
    with core.connection() as c:
        require_feature(core,c)
        if not token or not c.execute("SELECT 1 FROM customer_tokens WHERE token_hash=? AND purpose='reset' AND expires_at>?",(hash_token(token),(datetime.now(timezone.utc)).isoformat())).fetchone():
            raise HTTPException(400,"Password reset link expired or invalid.")
        return core.render(request,"account_auth.html",c,mode="reset",reset_token=token)


@router.post("/account/reset")
def reset_post(request: Request,csrf: str=Form(...),token: str=Form(...),password: str=Form(...)):
    import app as core
    core.check_csrf(request,csrf)
    core.throttle(request,"customer-reset-submit",5,3600)
    if not 12<=len(password)<=128:
        raise HTTPException(400,"New password must be between 12 and 128 characters.")
    with core.connection() as c:
        require_feature(core,c)
        user = consume_token(c,token,"reset")
        if not user:
            raise HTTPException(400,"Reset link expired or invalid.")
        c.execute("UPDATE customer_users SET password_hash=? WHERE id=?",(core.PH.hash(password),user["id"]))
        request.session.clear()
    return RedirectResponse("/account/login",303)


@router.post("/account/logout")
def customer_logout(request: Request,csrf: str=Form(...)):
    import app as core
    core.check_csrf(request,csrf)
    request.session.clear()
    return RedirectResponse("/",303)


@router.post("/account/vehicle")
def add_vehicle(request: Request,csrf: str=Form(...), year: str=Form(""),make: str=Form(...),
                model: str=Form(...),trim: str=Form(""),nickname: str=Form("")):
    import app as core
    core.check_csrf(request,csrf)
    with core.connection() as c:
        user = require_customer(core,request,c)
        count = c.execute("SELECT COUNT(*) FROM customer_vehicles WHERE user_id=?",(user["id"],)).fetchone()[0]
        if count>=20:
            raise HTTPException(400,"Maximum 20 vehicles per account.")
        values = {"vehicle_year":[year],"vehicle_make":[make],"vehicle_model":[model]}
        # A small getlist adapter reuses the same validation rules as registration.
        class Adapter:
            def getlist(self,key): return values.get(key,[])
        parsed = _vehicle_from_form(core,Adapter(),0)
        if not parsed:
            raise HTTPException(400,"Enter a vehicle make and model.")
        c.execute("""INSERT INTO customer_vehicles(user_id,year,make,model,trim,nickname,created_at)
                     VALUES(?,?,?,?,?,?,?)""",(*[user["id"],*parsed],core.safe_text(trim,60),core.safe_text(nickname,60),core.stamp()))
    return RedirectResponse("/account?saved=1#garage",303)


@router.post("/account/vehicle/delete")
def delete_vehicle(request: Request,csrf: str=Form(...),vehicle_id: int=Form(...)):
    import app as core
    core.check_csrf(request,csrf)
    with core.connection() as c:
        user = require_customer(core,request,c)
        uses = c.execute("SELECT 1 FROM care_enrollments WHERE vehicle_id=? AND user_id=? AND active=1 LIMIT 1",(vehicle_id,user["id"])).fetchone()
        bookings = c.execute("SELECT 1 FROM appointments WHERE vehicle_id=? AND customer_id=? LIMIT 1",(vehicle_id,user["id"])).fetchone()
        if uses or bookings:
            raise HTTPException(409,"This vehicle has associated bookings or plans. Contact GEM Autoworks for help.")
        c.execute("DELETE FROM customer_vehicles WHERE id=? AND user_id=?",(vehicle_id,user["id"]))
    return RedirectResponse("/account?saved=1#garage",303)


@router.post("/account/plan")
def enroll_plan(request: Request,csrf: str=Form(...),plan_id: int=Form(...),vehicle_id: int=Form(...)):
    import app as core
    core.check_csrf(request,csrf)
    with core.connection() as c:
        user = require_customer(core,request,c)
        vehicle = c.execute("SELECT * FROM customer_vehicles WHERE id=? AND user_id=?",(vehicle_id,user["id"])).fetchone()
        plan = c.execute("SELECT * FROM care_plans WHERE id=? AND active=1",(plan_id,)).fetchone()
        if not vehicle or not plan:
            raise HTTPException(400,"Select a valid plan and one of your vehicles.")
        exists = c.execute("SELECT 1 FROM care_enrollments WHERE user_id=? AND vehicle_id=? AND plan_id=? AND active=1",(user["id"],vehicle_id,plan_id)).fetchone()
        if exists:
            raise HTTPException(409,"This vehicle is already enrolled in that care plan.")
        due = plus_months(core.now().date(),plan["interval_months"]).isoformat()
        c.execute("INSERT INTO care_enrollments(user_id,vehicle_id,plan_id,next_due,created_at) VALUES(?,?,?,?,?)",(user["id"],vehicle_id,plan_id,due,core.stamp()))
        cfg=core.settings(c)
        body=f"{user['name']} enrolled {_format_vehicle(vehicle)} in {plan['name']}. Next reminder date: {due}."
        core.queue_email(c,user["email"],"Your GEM Autoworks care plan",body+"\n\nNo appointment or payment is taken automatically.")
        core.queue_email(c,cfg["email"],"New GEM care-plan enrollment",body)
    return RedirectResponse("/account?saved=1#plans",303)


@router.post("/account/plan/cancel")
def cancel_plan(request: Request,csrf: str=Form(...),enrollment_id: int=Form(...)):
    import app as core
    core.check_csrf(request,csrf)
    with core.connection() as c:
        user = require_customer(core,request,c)
        c.execute("UPDATE care_enrollments SET active=0 WHERE id=? AND user_id=?",(enrollment_id,user["id"]))
    return RedirectResponse("/account?saved=1#plans",303)


@router.post("/admin/care-plan")
def admin_care_plan(request: Request,csrf: str=Form(...),plan_id: int=Form(0),service_id: int=Form(...),
                    name: str=Form(...),description: str=Form(""),interval_months: int=Form(12),
                    active: str=Form("")):
    import app as core
    core.admin_only(request); core.check_csrf(request,csrf)
    if not 1<=interval_months<=60 or len(core.safe_text(name,90))<3:
        raise HTTPException(400,"Invalid plan name or interval (1 to 60 months).")
    with core.connection() as c:
        if not c.execute("SELECT 1 FROM services WHERE id=?",(service_id,)).fetchone():
            raise HTTPException(400,"Choose an existing service.")
        args=(service_id,core.safe_text(name,90),core.safe_text(description,350),interval_months,int(active=="on"))
        if plan_id:
            c.execute("""UPDATE care_plans SET service_id=?,name=?,description=?,interval_months=?,active=?
                         WHERE id=?""",(*args,plan_id))
        else:
            c.execute("INSERT INTO care_plans(service_id,name,description,interval_months,active) VALUES(?,?,?,?,?)",args)
    return RedirectResponse("/admin?saved=1#customers",303)


@router.post("/admin/care-plan/complete")
def admin_complete_plan(request: Request,csrf: str=Form(...),enrollment_id: int=Form(...)):
    """Owner records completed service and advances due date; never auto-charges or books."""
    import app as core
    core.admin_only(request); core.check_csrf(request,csrf)
    with core.connection() as c:
        row=c.execute("""SELECT e.*,p.interval_months,u.email,u.name,p.name AS plan_name
                         FROM care_enrollments e JOIN care_plans p ON p.id=e.plan_id
                         JOIN customer_users u ON u.id=e.user_id
                         WHERE e.id=? AND e.active=1""",(enrollment_id,)).fetchone()
        if not row:
            raise HTTPException(404,"Enrollment not found.")
        next_due=plus_months(max(date.fromisoformat(row["next_due"]),core.now().date()),row["interval_months"]).isoformat()
        c.execute("UPDATE care_enrollments SET next_due=? WHERE id=?",(next_due,enrollment_id))
        core.queue_email(c,row["email"],f"GEM care schedule updated: {row['plan_name']}",
                         f"Hello {row['name']},\n\nYour next {row['plan_name']} service reminder is scheduled for {next_due}.\n\nPlease contact GEM if this date is incorrect.")
    return RedirectResponse("/admin?saved=1#customers",303)


@router.post("/account/profile")
def update_profile(request: Request, csrf: str=Form(...),name: str=Form(...),phone: str=Form(...)):
    import app as core
    core.check_csrf(request,csrf)
    name=core.safe_text(name,100)
    phone=core.safe_text(phone,50)
    if len(name)<2 or len(phone)<7:
        raise HTTPException(400,"Please enter a valid name and phone number.")
    with core.connection() as c:
        user=require_customer(core,request,c)
        c.execute("UPDATE customer_users SET name=?,phone=? WHERE id=?",(name,phone,user["id"]))
    return RedirectResponse("/account?saved=1#profile",303)


@router.post("/account/appointment/cancel")
def customer_cancel_booking(request: Request,csrf: str=Form(...),appointment_id: int=Form(...)):
    import app as core
    core.check_csrf(request,csrf)
    with core.connection() as c:
        user=require_customer(core,request,c)
        c.execute("BEGIN IMMEDIATE")
        try:
            booking=c.execute("""SELECT a.*,s.title AS service_title FROM appointments a
                                 JOIN services s ON s.id=a.service_id
                                 WHERE a.id=? AND a.customer_id=?""",(appointment_id,user["id"])).fetchone()
            if not booking:
                raise HTTPException(404,"Appointment not found.")
            if booking["status"] not in ("confirmed","pending"):
                raise HTTPException(409,"This appointment cannot be cancelled online.")
            # Restrict self-service cancellation to at least 24 hours before the appointment.
            starts=datetime.fromisoformat(f"{booking['day']}T{booking['at_time']}").replace(tzinfo=core.TZ)
            if starts < core.now()+timedelta(hours=24):
                raise HTTPException(409,"Please contact GEM directly to change an appointment within 24 hours.")
            c.execute("UPDATE appointments SET status='cancelled',updated_at=? WHERE id=?",(core.stamp(),appointment_id))
            config=core.settings(c)
            core.queue_email(c,user["email"],f"GEM booking {booking['reference']} cancelled",
                             f"Hello {user['name']},\n\nYour appointment {booking['reference']} on {booking['day']} has been cancelled.\n\nQuestions? Contact {config['email']}.")
            core.queue_email(c,config["email"],f"Customer cancellation: {booking['reference']}",
                             f"{user['name']} ({user['email']}) cancelled {booking['service_title']} on {booking['day']} at {booking['at_time']}.")
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
    return RedirectResponse("/account?saved=1#bookings",303)


@router.post("/account/appointment/reschedule")
def customer_reschedule_booking(request: Request,csrf: str=Form(...),
                                appointment_id: int=Form(...),day: str=Form(...),at_time: str=Form(...)):
    import app as core
    core.check_csrf(request,csrf)
    with core.connection() as c:
        user=require_customer(core,request,c)
        c.execute("BEGIN IMMEDIATE")
        try:
            booking=c.execute("""SELECT a.*,s.title AS service_title FROM appointments a
                                 JOIN services s ON s.id=a.service_id
                                 WHERE a.id=? AND a.customer_id=?""",(appointment_id,user["id"])).fetchone()
            if not booking:
                raise HTTPException(404,"Appointment not found.")
            if booking["status"] not in ("confirmed","pending"):
                raise HTTPException(409,"This booking cannot be rescheduled online.")
            original=datetime.fromisoformat(f"{booking['day']}T{booking['at_time']}").replace(tzinfo=core.TZ)
            if original < core.now()+timedelta(hours=24):
                raise HTTPException(409,"Please contact GEM to change an appointment within 24 hours.")
            service=c.execute("SELECT * FROM services WHERE id=?",(booking["service_id"],)).fetchone()
            if not service:
                raise HTTPException(400,"Associated service is unavailable.")
            # Temporarily exclude this booking from conflicts, then restore its original status.
            c.execute("UPDATE appointments SET status='rescheduling' WHERE id=?",(appointment_id,))
            valid=at_time in core.appointment_slots(c,service,day)
            c.execute("UPDATE appointments SET status=? WHERE id=?",(booking["status"],appointment_id))
            if not valid:
                raise HTTPException(409,"That time is not available. Please select another slot.")
            c.execute("UPDATE appointments SET day=?,at_time=?,updated_at=? WHERE id=?",
                      (day,at_time,core.stamp(),appointment_id))
            config=core.settings(c)
            summary=f"{booking['service_title']} on {day} at {at_time} ({core.BUSINESS_TZ})"
            core.queue_email(c,user["email"],f"Your GEM booking {booking['reference']} changed",
                             f"Hello {user['name']},\n\nYour appointment {booking['reference']} is now scheduled for {summary}.\n\nQuestions? Contact {config['email']}.")
            core.queue_email(c,config["email"],f"Customer rescheduled: {booking['reference']}",
                             f"{user['name']} ({user['email']}) changed their appointment to {summary}.")
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
    return RedirectResponse("/account?saved=1#bookings",303)


@router.post("/admin/customer/plan")
def admin_update_enrollment(request: Request,csrf: str=Form(...),enrollment_id: int=Form(...),
                            next_due: str=Form(...),active: str=Form("")):
    import app as core
    core.admin_only(request);core.check_csrf(request,csrf)
    try:
        when=date.fromisoformat(next_due)
        if not date(2000,1,1)<=when<=date(2100,1,1): raise ValueError()
    except ValueError:
        raise HTTPException(400,"Invalid due date.")
    with core.connection() as c:
        c.execute("UPDATE care_enrollments SET next_due=?,active=? WHERE id=?",
                  (when.isoformat(),int(active=="on"),enrollment_id))
    return RedirectResponse("/admin?saved=1#customers",303)
