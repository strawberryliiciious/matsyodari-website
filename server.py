#!/usr/bin/env python3
"""
Matsyodari Renewables - website server and enquiry backend.

Uses only the Python standard library (Python 3.8 or newer). Nothing to install.

  python server.py          then open  http://127.0.0.1:8000
  Admin panel:              http://127.0.0.1:8000/admin

What it does
  * serves the website (index.html, css/, js/, images/, admin/)
  * POST /api/enquiries  - saves a customer enquiry in SQLite (data/enquiries.db)
                           and e-mails it to the company (if SMTP is set up in .env)
  * /api/admin/...       - password-protected admin API used by the admin panel
"""
import base64
import csv
import hashlib
import hmac
import io
import json
import mimetypes
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
import sys
import threading
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

# ----------------------------------------------------------------------------
# configuration (.env file or real environment variables)
# ----------------------------------------------------------------------------
def load_config():
    cfg = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in os.environ.items():
        if k.startswith(("SMTP_", "MAIL_", "ADMIN_", "ALLOWED_", "TRUST_", "COOKIE_")) or k in ("HOST", "PORT"):
            cfg[k] = v
    return cfg


CFG = load_config()
HOST = CFG.get("HOST", "127.0.0.1")
PORT = int(CFG.get("PORT", "8000"))
MAIL_TO = CFG.get("MAIL_TO", "matsyodaripvtltd@rediffmail.com")
ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in CFG.get(
    "ALLOWED_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500").split(",") if o.strip()]
TRUST_PROXY = CFG.get("TRUST_PROXY", "0") == "1"
COOKIE_SECURE = CFG.get("COOKIE_SECURE", "0") == "1"
SESSION_SECONDS = 12 * 3600

SERVICES = [
    "Transmission line installation", "Substation equipment installation", "Solar EPC / rooftop solar",
    "Operations and maintenance", "Project consultancy", "Material supply support", "Other",
]
STATUSES = ("new", "contacted", "closed")

# ----------------------------------------------------------------------------
# secrets and admin password
# ----------------------------------------------------------------------------
def _read_or_create(path, factory):
    if not path.exists():
        path.write_text(factory(), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


SECRET = _read_or_create(DATA / "secret.key", lambda: secrets.token_hex(32)).encode()


def admin_password():
    pw = CFG.get("ADMIN_PASSWORD")
    if pw:
        return pw
    first = not (DATA / "admin_password.txt").exists()
    pw = _read_or_create(DATA / "admin_password.txt", lambda: secrets.token_urlsafe(9))
    if first:
        print("\n  Admin password created (saved in data/admin_password.txt):  %s" % pw)
        print("  Set ADMIN_PASSWORD in the .env file to choose your own.\n")
    return pw


ADMIN_PASSWORD = admin_password()


def _sign(payload):
    return hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()


REVOKED = set()


def make_token():
    payload = "%d.%s" % (int(time.time()) + SESSION_SECONDS, secrets.token_hex(8))
    return payload + "." + _sign(payload)


def valid_token(token):
    try:
        exp, nonce, sig = token.split(".")
        if not hmac.compare_digest(sig, _sign(exp + "." + nonce)):
            return False
        return int(exp) > time.time() and token not in REVOKED
    except Exception:
        return False


# ----------------------------------------------------------------------------
# rate limiting (in memory)
# ----------------------------------------------------------------------------
class Limiter:
    def __init__(self):
        self.hits = {}
        self.lock = threading.Lock()

    def _recent(self, key, window):
        now = time.time()
        q = [t for t in self.hits.get(key, []) if now - t < window]
        self.hits[key] = q
        return q

    def allow(self, key, limit, window):
        """Count a hit; return False when over the limit."""
        with self.lock:
            q = self._recent(key, window)
            if len(q) >= limit:
                return False
            q.append(time.time())
            return True

    def blocked(self, key, limit, window):
        with self.lock:
            return len(self._recent(key, window)) >= limit

    def add(self, key, window):
        with self.lock:
            self._recent(key, window).append(time.time())


LIMITER = Limiter()

# ----------------------------------------------------------------------------
# database
# ----------------------------------------------------------------------------
DB_PATH = DATA / "enquiries.db"
DB_LOCK = threading.Lock()


def query(sql, args=(), one=False, commit=False):
    with DB_LOCK:
        con = sqlite3.connect(str(DB_PATH), timeout=10)
        con.row_factory = sqlite3.Row
        try:
            cur = con.execute(sql, args)
            rows = cur.fetchone() if one else cur.fetchall()
            if commit:
                con.commit()
            return rows if not commit else (cur.lastrowid, cur.rowcount)
        finally:
            con.close()


def init_db():
    query("""CREATE TABLE IF NOT EXISTS enquiries(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ref TEXT DEFAULT '', name TEXT NOT NULL, phone TEXT NOT NULL,
        email TEXT DEFAULT '', service TEXT DEFAULT '', message TEXT NOT NULL, status TEXT DEFAULT 'new',
        note TEXT DEFAULT '', mail TEXT DEFAULT '', created_at TEXT NOT NULL, ip TEXT DEFAULT '')""", commit=True)


init_db()

# ----------------------------------------------------------------------------
# e-mail
# ----------------------------------------------------------------------------
def smtp_ready():
    return bool(CFG.get("SMTP_HOST"))


def _smtp_send(msg):
    host = CFG["SMTP_HOST"]
    port = int(CFG.get("SMTP_PORT", "587"))
    mode = CFG.get("SMTP_SECURE", "starttls").lower()
    ctx = ssl.create_default_context()
    if mode == "ssl":
        server = smtplib.SMTP_SSL(host, port, timeout=20, context=ctx)
    else:
        server = smtplib.SMTP(host, port, timeout=20)
        server.ehlo()
        if mode == "starttls":
            server.starttls(context=ctx)
            server.ehlo()
    try:
        if CFG.get("SMTP_USER"):
            server.login(CFG["SMTP_USER"], CFG.get("SMTP_PASS", ""))
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def _mail_from():
    return CFG.get("MAIL_FROM") or CFG.get("SMTP_USER") or "website@localhost"


def notify_async(enq_id):
    """Send the company notification (and a receipt to the customer) in a background thread."""
    def work():
        row = query("SELECT * FROM enquiries WHERE id=?", (enq_id,), one=True)
        if not row:
            return
        status = "sent"
        try:
            m = EmailMessage()
            m["Subject"] = "New enquiry %s - %s" % (row["ref"], row["service"] or "General")
            m["From"] = _mail_from()
            m["To"] = MAIL_TO
            m["Date"] = formatdate(localtime=True)
            m["Message-ID"] = make_msgid()
            if row["email"]:
                m["Reply-To"] = row["email"]
            m.set_content(
                "A new enquiry was received on the website.\n\n"
                "Reference : %s\nName      : %s\nPhone     : %s\nEmail     : %s\nService   : %s\nReceived  : %s (UTC)\n\n"
                "Message:\n%s\n" % (row["ref"], row["name"], row["phone"], row["email"] or "-", row["service"] or "-",
                                    row["created_at"], row["message"]))
            _smtp_send(m)
            if row["email"]:
                r = EmailMessage()
                r["Subject"] = "We received your enquiry (%s)" % row["ref"]
                r["From"] = _mail_from()
                r["To"] = row["email"]
                r["Date"] = formatdate(localtime=True)
                r["Message-ID"] = make_msgid()
                r.set_content(
                    "Dear %s,\n\nThank you for contacting Matsyodari Renewables. We have received your enquiry "
                    "(reference %s) and our team will get back to you soon.\n\nFor urgent matters call +91 94237 12487.\n\n"
                    "Regards,\nMatsyodari Renewables Private Limited\nJalna, Maharashtra\n" % (row["name"], row["ref"]))
                _smtp_send(r)
        except Exception as exc:  # keep the enquiry; just record that mail failed
            status = ("failed: %s" % exc)[:200]
            sys.stderr.write("[mail] %s\n" % status)
        query("UPDATE enquiries SET mail=? WHERE id=?", (status, enq_id), commit=True)

    threading.Thread(target=work, daemon=True).start()


# ----------------------------------------------------------------------------
# validation
# ----------------------------------------------------------------------------
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
PHONE_RE = re.compile(r"^[+\d][\d\s\-]{7,17}$")
EMAIL_RE = re.compile(r"^[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+$")


def clean(value, limit):
    return CTRL.sub("", str(value if value is not None else "")).strip()[:limit]


def validate_enquiry(data):
    d = {
        "name": clean(data.get("name"), 80), "phone": clean(data.get("phone"), 20),
        "email": clean(data.get("email"), 120), "service": clean(data.get("service"), 80),
        "message": clean(data.get("message"), 2000),
    }
    errors = {}
    if len(d["name"]) < 2:
        errors["name"] = "Please enter your name."
    if not PHONE_RE.match(d["phone"]):
        errors["phone"] = "Enter a valid phone number."
    if d["email"] and not EMAIL_RE.match(d["email"]):
        errors["email"] = "Enter a valid email address."
    if d["service"] not in SERVICES:
        errors["service"] = "Please choose a service."
    if len(d["message"]) < 10:
        errors["message"] = "Please add a few details (at least 10 characters)."
    return d, errors


# ----------------------------------------------------------------------------
# HTTP handler
# ----------------------------------------------------------------------------
STATIC_DIRS = ("css", "js", "images", "admin")
CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


class Handler(BaseHTTPRequestHandler):
    server_version = "MatsyodariServer"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))

    # ---- helpers -------------------------------------------------------
    def client_ip(self):
        if TRUST_PROXY:
            fwd = self.headers.get("X-Forwarded-For", "")
            if fwd:
                return fwd.split(",")[0].strip()
        return self.client_address[0]

    def send_bytes(self, code, body, ctype, headers=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", CSP)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, code, obj, headers=None):
        h = {"Cache-Control": "no-store"}
        h.update(headers or {})
        self.send_bytes(code, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8", h)

    def cors(self):
        origin = self.headers.get("Origin", "").rstrip("/")
        if origin and origin in ALLOWED_ORIGINS:
            return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
        return {}

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > 20000:
            self.send_json(413, {"ok": False, "error": "Request too large."})
            return None
        if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            self.send_json(415, {"ok": False, "error": "Send JSON."})
            return None
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            if not isinstance(data, dict):
                raise ValueError
            return data
        except Exception:
            self.send_json(400, {"ok": False, "error": "Invalid JSON."})
            return None

    # ---- admin auth ----------------------------------------------------
    def cookie_token(self):
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "mr_admin":
                return v
        return ""

    def is_admin(self):
        return valid_token(self.cookie_token())

    def same_origin(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return urlparse(origin).netloc == self.headers.get("Host", "")

    def require_admin(self, write=False):
        if not self.is_admin():
            self.send_json(401, {"ok": False, "error": "Please sign in."})
            return False
        if write and (not self.same_origin() or self.headers.get("X-Requested-With") != "fetch"):
            self.send_json(403, {"ok": False, "error": "Request blocked."})
            return False
        return True

    # ---- routing -------------------------------------------------------
    def do_OPTIONS(self):
        path = urlparse(self.path).path
        if path in ("/api/enquiries", "/api/health"):
            h = self.cors()
            h.update({"Access-Control-Allow-Methods": "POST, GET, OPTIONS", "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "600"})
            self.send_bytes(204, b"", "text/plain", h)
        else:
            self.send_bytes(404, b"", "text/plain")

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        if path == "/api/health":
            return self.send_json(200, {"ok": True, "mail": smtp_ready()}, self.cors())
        if path == "/api/admin/me":
            return self.send_json(200, {"ok": self.is_admin(), "mail": smtp_ready()})
        if path == "/api/admin/enquiries":
            return self.admin_list(parse_qs(url.query))
        if path == "/api/admin/export.csv":
            return self.admin_export()
        if path.startswith("/api/"):
            return self.send_json(404, {"ok": False, "error": "Not found."})
        return self.serve_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/enquiries":
            return self.create_enquiry()
        if path == "/api/admin/login":
            return self.admin_login()
        if path == "/api/admin/logout":
            if self.same_origin():
                REVOKED.add(self.cookie_token())
            return self.send_json(200, {"ok": True}, {"Set-Cookie": "mr_admin=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"})
        self.send_json(404, {"ok": False, "error": "Not found."})

    def do_PATCH(self):
        m = re.match(r"^/api/admin/enquiries/(\d+)$", urlparse(self.path).path)
        if not m:
            return self.send_json(404, {"ok": False, "error": "Not found."})
        if not self.require_admin(write=True):
            return
        data = self.read_json()
        if data is None:
            return
        sets, args = [], []
        if "status" in data:
            if data["status"] not in STATUSES:
                return self.send_json(400, {"ok": False, "error": "Bad status."})
            sets.append("status=?")
            args.append(data["status"])
        if "note" in data:
            sets.append("note=?")
            args.append(clean(data["note"], 1000))
        if not sets:
            return self.send_json(400, {"ok": False, "error": "Nothing to update."})
        args.append(int(m.group(1)))
        _, n = query("UPDATE enquiries SET %s WHERE id=?" % ", ".join(sets), tuple(args), commit=True)
        self.send_json(200 if n else 404, {"ok": bool(n)})

    def do_DELETE(self):
        m = re.match(r"^/api/admin/enquiries/(\d+)$", urlparse(self.path).path)
        if not m:
            return self.send_json(404, {"ok": False, "error": "Not found."})
        if not self.require_admin(write=True):
            return
        _, n = query("DELETE FROM enquiries WHERE id=?", (int(m.group(1)),), commit=True)
        self.send_json(200 if n else 404, {"ok": bool(n)})

    # ---- public API ----------------------------------------------------
    def create_enquiry(self):
        cors = self.cors()
        ip = self.client_ip()
        # at most 30 requests a minute (any kind) and 5 saved enquiries an hour from one connection
        if not LIMITER.allow("req:" + ip, 30, 60) or LIMITER.blocked("enq:" + ip, 5, 3600):
            return self.send_json(429, {"ok": False, "error": "Too many enquiries from your connection. Please call us on +91 94237 12487."}, cors)
        data = self.read_json()
        if data is None:
            return
        if clean(data.get("website"), 50):  # honeypot field filled in: a bot
            LIMITER.add("enq:" + ip, 3600)
            return self.send_json(200, {"ok": True, "ref": "MR-00000"}, cors)
        d, errors = validate_enquiry(data)
        if errors:
            return self.send_json(422, {"ok": False, "errors": errors}, cors)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        enq_id, _ = query(
            "INSERT INTO enquiries(name,phone,email,service,message,created_at,ip,mail) VALUES(?,?,?,?,?,?,?,?)",
            (d["name"], d["phone"], d["email"], d["service"], d["message"], now, ip, "pending" if smtp_ready() else "not configured"),
            commit=True)
        ref = "MR-%05d" % enq_id
        query("UPDATE enquiries SET ref=? WHERE id=?", (ref, enq_id), commit=True)
        LIMITER.add("enq:" + ip, 3600)
        if smtp_ready():
            notify_async(enq_id)
        self.send_json(201, {"ok": True, "ref": ref}, cors)

    # ---- admin API -----------------------------------------------------
    def admin_login(self):
        ip = self.client_ip()
        if LIMITER.blocked("login:" + ip, 8, 900):
            return self.send_json(429, {"ok": False, "error": "Too many attempts. Try again in 15 minutes."})
        if not self.same_origin():
            return self.send_json(403, {"ok": False, "error": "Request blocked."})
        data = self.read_json()
        if data is None:
            return
        given = hashlib.sha256(str(data.get("password", "")).encode()).digest()
        real = hashlib.sha256(ADMIN_PASSWORD.encode()).digest()
        if not hmac.compare_digest(given, real):
            LIMITER.add("login:" + ip, 900)
            return self.send_json(401, {"ok": False, "error": "Wrong password."})
        cookie = "mr_admin=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Strict%s" % (make_token(), SESSION_SECONDS, "; Secure" if COOKIE_SECURE else "")
        self.send_json(200, {"ok": True}, {"Set-Cookie": cookie})

    def _filters(self, qs):
        where, args = [], []
        status = (qs.get("status") or [""])[0]
        if status in STATUSES:
            where.append("status=?")
            args.append(status)
        text = (qs.get("q") or [""])[0].strip()[:80]
        if text:
            like = "%" + text.replace("%", "").replace("_", "") + "%"
            where.append("(name LIKE ? OR phone LIKE ? OR email LIKE ? OR message LIKE ? OR ref LIKE ?)")
            args += [like] * 5
        return (" WHERE " + " AND ".join(where)) if where else "", args

    def admin_list(self, qs):
        if not self.require_admin():
            return
        clause, args = self._filters(qs)
        try:
            limit = max(1, min(500, int((qs.get("limit") or ["200"])[0])))
        except ValueError:
            limit = 200
        rows = query("SELECT id,ref,name,phone,email,service,message,status,note,mail,created_at FROM enquiries%s ORDER BY id DESC LIMIT ?" % clause, tuple(args) + (limit,))
        counts = {s: 0 for s in STATUSES}
        for r in query("SELECT status, COUNT(*) c FROM enquiries GROUP BY status"):
            counts[r["status"]] = r["c"]
        self.send_json(200, {"ok": True, "enquiries": [dict(r) for r in rows], "counts": counts, "mail": smtp_ready()})

    def admin_export(self):
        if not self.require_admin():
            return
        rows = query("SELECT ref,created_at,name,phone,email,service,message,status,note FROM enquiries ORDER BY id DESC")
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Reference", "Received (UTC)", "Name", "Phone", "Email", "Service", "Message", "Status", "Note"])
        def safe(v):
            v = "" if v is None else str(v)
            # a leading = + - @ can run as a formula in Excel, so neutralise it
            return ("'" + v) if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v
        for r in rows:
            r = list(r)
            # phone numbers were checked on entry (digits, spaces, + and - only) so they are shown as text safely
            r[3] = '="%s"' % r[3] if PHONE_RE.match(str(r[3])) else safe(r[3])
            w.writerow([r[i] if i == 3 else safe(r[i]) for i in range(len(r))])
        body = ("\ufeff" + buf.getvalue()).encode("utf-8")
        self.send_bytes(200, body, "text/csv; charset=utf-8", {"Content-Disposition": 'attachment; filename="enquiries.csv"', "Cache-Control": "no-store"})

    # ---- static files --------------------------------------------------
    def serve_static(self, path):
        if path in ("/", "/index.html"):
            target = ROOT / "index.html"
        elif path in ("/admin", "/admin/"):
            target = ROOT / "admin" / "index.html"
        else:
            rel = unquote(path).lstrip("/")
            top = rel.split("/")[0]
            if top not in STATIC_DIRS or "\x00" in rel:
                return self.send_bytes(404, b"Not found", "text/plain; charset=utf-8")
            target = (ROOT / rel).resolve()
            if not str(target).startswith(str(ROOT / top) + os.sep):
                return self.send_bytes(404, b"Not found", "text/plain; charset=utf-8")
        if not target.is_file():
            return self.send_bytes(404, b"Not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.suffix == ".js":
            ctype = "text/javascript"
        if ctype.startswith("text/") or ctype in ("application/json",):
            ctype += "; charset=utf-8"
        cache = "no-cache" if target.suffix == ".html" else "public, max-age=300"
        self.send_bytes(200, target.read_bytes(), ctype, {"Cache-Control": cache})


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    shown = "127.0.0.1" if HOST in ("0.0.0.0", "") else HOST
    print("Matsyodari Renewables server running")
    print("  Website : http://%s:%d" % (shown, PORT))
    print("  Admin   : http://%s:%d/admin" % (shown, PORT))
    print("  E-mail  : %s" % ("sending to " + MAIL_TO if smtp_ready() else "not set up (enquiries are still saved) - see .env.example"))
    print("  Stop with Ctrl+C\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
