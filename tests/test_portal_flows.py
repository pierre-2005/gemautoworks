"""End-to-end customer account, garage, booking and reminder regression tests.

Every test uses a fresh temporary SQLite database. No real emails are sent.
"""
import re
from datetime import timedelta

from fastapi.testclient import TestClient

import app as core
import customer_portal


def csrf(html):
    match=re.search(r'name="csrf" value="([^"]+)"', html)
    assert match, "Missing CSRF field"
    return match.group(1)


def first_open_slot(client, after=3):
    for offset in range(after,28):
        date=(core.now()+timedelta(days=offset)).date().isoformat()
        slots=client.get("/api/availability", params={"service_id":1,"day":date}).json()["slots"]
        if slots:return date,slots[0]
    raise AssertionError("Could not find an appointment in the test calendar")


def test_customer_registration_vehicle_booking_lifecycle(tmp_path,monkeypatch):
    dbfile=tmp_path/"test-gem.sqlite3"
    monkeypatch.setattr(core,"DB_PATH",dbfile)
    monkeypatch.setattr(core,"send_pending",lambda:0)
    monkeypatch.setattr(core,"email_configured",lambda:True)
    with TestClient(core.app) as client:
        with core.connection() as c:
            c.execute("UPDATE settings SET value='1' WHERE key='customer_accounts_enabled'")
            c.execute("INSERT INTO care_plans(service_id,name,description,interval_months,active) VALUES(1,'Annual cleaning','Yearly care',12,1)")
        page=client.get("/account/register")
        assert page.status_code==200
        response=client.post("/account/register",data={
            "csrf":csrf(page.text),"name":"Test Customer","phone":"5558675309",
            "email":"flow.customer@example.com","password":"LongAndSafeTestPassword!123",
            "vehicle_year":"2023","vehicle_make":"Honda","vehicle_model":"Civic"
        },follow_redirects=False)
        assert response.status_code==200
        with core.connection() as c:
            user=c.execute("SELECT * FROM customer_users WHERE email='flow.customer@example.com'").fetchone()
            assert user and not user["verified"]
            vehicle=c.execute("SELECT * FROM customer_vehicles WHERE user_id=?",(user["id"],)).fetchone()
            assert (vehicle["make"],vehicle["model"])==("Honda","Civic")
            token_email=c.execute("SELECT body FROM email_outbox WHERE recipient=? ORDER BY id DESC LIMIT 1",(user["email"],)).fetchone()["body"]
        token=re.search(r'/account/verify\?token=([A-Za-z0-9_-]+)',token_email).group(1)
        response=client.get("/account/verify",params={"token":token},follow_redirects=False)
        assert response.status_code==303
        assert response.headers["location"]=="/account"
        assert client.get("/account").status_code==200
        assert "Honda" in client.get("/account").text

        # Customer independently opts in to annual care.
        page=client.get("/account")
        response=client.post("/account/plan",data={"csrf":csrf(page.text),
                              "vehicle_id":vehicle["id"],"plan_id":1},follow_redirects=False)
        assert response.status_code==303
        with core.connection() as c:
            e=c.execute("SELECT * FROM care_enrollments WHERE user_id=?",(user["id"],)).fetchone()
            assert e and e["active"]==1

        day,time=first_open_slot(client)
        form=client.get("/book")
        response=client.post("/book",data={
            "csrf":csrf(form.text),"service_id":1,"day":day,"at_time":time,
            "name":"Different Name","email":"different@example.com","phone":"0000000000",
            "vehicle_id":str(vehicle["id"]), "vehicle":"","notes":"Testing"
        },follow_redirects=False)
        assert response.status_code==303
        with core.connection() as c:
            ap=c.execute("SELECT * FROM appointments WHERE customer_id=?",(user["id"],)).fetchone()
            assert ap and ap["vehicle_id"]==vehicle["id"]
            assert ap["name"]=="Test Customer" and ap["email"]==user["email"]
            appointment_id=ap["id"]

        next_day,next_time=first_open_slot(client,after=10)
        response=client.post("/account/appointment/reschedule",data={
            "csrf":csrf(client.get("/account").text),
            "appointment_id":appointment_id,"day":next_day,"at_time":next_time
        },follow_redirects=False)
        assert response.status_code==303
        with core.connection() as c:
            ap=c.execute("SELECT * FROM appointments WHERE id=?",(appointment_id,)).fetchone()
            assert (ap["day"],ap["at_time"])==(next_day,next_time)

        response=client.post("/account/appointment/cancel",data={
            "csrf":csrf(client.get("/account").text),"appointment_id":appointment_id
        },follow_redirects=False)
        assert response.status_code==303
        with core.connection() as c:
            assert c.execute("SELECT status FROM appointments WHERE id=?",(appointment_id,)).fetchone()[0]=="cancelled"

        # A stranger cannot modify another customer's appointment.
        with TestClient(core.app) as guest:
            guest_csrf=csrf(guest.get("/account/login").text)
            denied=guest.post("/account/appointment/cancel",data={"csrf":guest_csrf,"appointment_id":appointment_id},follow_redirects=False)
            assert denied.status_code==401

        # Existing anonymous bookings can be claimed only with a matching verified email.
        with TestClient(core.app) as visitor:
            anon_day,anon_time=first_open_slot(visitor,after=18)
            token=csrf(visitor.get("/book").text)
            anon_response=visitor.post("/book",data={
                "csrf":token,"service_id":1,"day":anon_day,"at_time":anon_time,
                "name":"Test Customer","email":"flow.customer@example.com","phone":"5558675309",
                "vehicle":"An older vehicle"
            },follow_redirects=False)
            assert anon_response.status_code==303
            reference=re.search(r'ref=(GEM-[A-F0-9]{8})',anon_response.headers["location"]).group(1)
        claim=client.post("/account/appointment/claim",data={"csrf":csrf(client.get("/account").text),
                            "reference":reference},follow_redirects=False)
        assert claim.status_code==303
        with core.connection() as c:
            assert c.execute("SELECT customer_id FROM appointments WHERE reference=?",(reference,)).fetchone()[0]==user["id"]
        assert "An older vehicle" in client.get("/account").text or reference in client.get("/account").text

        # Due reminders are idempotent for each window.
        with core.connection() as c:
            due=(core.now().date()+timedelta(days=7)).isoformat()
            c.execute("UPDATE care_enrollments SET next_due=? WHERE id=?",(due,e["id"]))
        assert customer_portal.queue_care_reminders()==1
        assert customer_portal.queue_care_reminders()==0

        # Disabled feature prevents private account access without deleting records.
        with core.connection() as c:c.execute("UPDATE settings SET value='0' WHERE key='customer_accounts_enabled'")
        assert client.get("/account").status_code==404


def test_admin_email_test_and_customer_plan_controls(tmp_path,monkeypatch):
    monkeypatch.setattr(core,"DB_PATH",tmp_path/"admin-gem.sqlite3")
    monkeypatch.setattr(core,"send_pending",lambda:0)
    monkeypatch.setattr(core,"email_configured",lambda:True)
    monkeypatch.setenv("ADMIN_EMAIL","owner@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD","A-Very-Strong-Test-Password-2026")
    with TestClient(core.app) as client:
        login=client.get("/admin/login")
        response=client.post("/admin/login",data={
            "csrf":csrf(login.text),
            "email":"owner@example.com",
            "password":"A-Very-Strong-Test-Password-2026"
        },follow_redirects=False)
        assert response.status_code==303
        admin_page=client.get("/admin")
        assert admin_page.status_code==200
        assert "Send test email" in admin_page.text
        assert "Customers & care plans" in admin_page.text
        assert client.post("/admin/email/test",data={"csrf":csrf(admin_page.text)},follow_redirects=False).status_code==303
        with core.connection() as c:
            assert c.execute("SELECT COUNT(*) FROM email_outbox WHERE subject LIKE '%SMTP test%'").fetchone()[0]==1
        # No untrusted request can queue a test email.
        with TestClient(core.app) as guest:
            token=csrf(guest.get("/admin/login").text)
            response=guest.post("/admin/email/test",data={"csrf":token},follow_redirects=False)
            assert response.status_code==303 and response.headers["location"]=="/admin/login"
