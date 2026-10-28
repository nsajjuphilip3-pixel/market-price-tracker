"""minikit.py - a tiny web toolkit built only on Python's standard library.

It gives every app in this collection the same four things:
  1. routing        @site.route("/item/(?P<id>\\d+)")
  2. a database     req.all(...), req.one(...), req.run(...)  (SQLite)
  3. HTML helpers   esc(), table(), form(), link(), badge(), bar(), ugx()
  4. a test helper  AppTestCase  (test pages without starting a server)
"""
import argparse
import html
import os
import re
import sqlite3
import sys
import tempfile
import traceback
import unittest
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


# ---------------------------------------------------------------- HTML helpers
class Safe(str):
    """Text that is already safe HTML. esc() will not escape it again."""


def esc(value):
    """Escape text so it can never run as HTML (prevents XSS)."""
    if isinstance(value, Safe):
        return str(value)
    return html.escape("" if value is None else str(value))


def num(text, default=0.0):
    """Parse '12,500' or '3.5' into a float; return default if it is not a number."""
    try:
        return float(str(text).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def ugx(amount):
    return f"UGX {round(amount or 0):,}"


def today():
    return date.today().isoformat()


def normalize_phone(text):
    """'0772 123 456' or '256772123456' -> '+256772123456'. Returns None if it is not a Ugandan mobile number."""
    digits = re.sub(r"[^\d+]", "", str(text or ""))
    if digits.startswith("+"):
        digits = digits[1:]
    if digits.startswith("0") and len(digits) == 10:
        digits = "256" + digits[1:]
    return "+" + digits if re.fullmatch(r"256[37]\d{8}", digits) else None


def link(href, text):
    return Safe(f'<a href="{esc(href)}">{esc(text)}</a>')


def badge(text, kind=""):
    return Safe(f'<span class="badge {esc(kind)}">{esc(text)}</span>')


def bar(percent):
    pct = max(0, min(100, percent))
    return Safe(f'<div class="bar"><div style="width:{pct:.0f}%"></div></div>')


def table(headers, rows):
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    rows = list(rows)
    if rows:
        body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows)
    else:
        body = f'<tr><td colspan="{len(headers)}"><em>Nothing here yet.</em></td></tr>'
    return Safe(f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')


def form(action, fields, button="Save", method="post"):
    """Build an HTML form. fields = [(name, label, kind, options_or_default, required), ...]
    kind: text, number, date, tel, email, textarea, select, hidden. Only name is required."""
    out = [f'<form method="{method}" action="{esc(action)}">']
    for f in fields:
        name, label = f[0], (f[1] if len(f) > 1 else f[0])
        kind = f[2] if len(f) > 2 else "text"
        opt = f[3] if len(f) > 3 else None
        required = " required" if (f[4] if len(f) > 4 else True) else ""
        n = esc(name)
        if kind == "hidden":
            out.append(f'<input type="hidden" name="{n}" value="{esc(opt)}">')
            continue
        if kind == "select":
            opts = ""
            for o in opt or []:
                value, text = (o if isinstance(o, (tuple, list)) else (o, o))
                opts += f'<option value="{esc(value)}">{esc(text)}</option>'
            control = f'<select name="{n}"{required}>{opts}</select>'
        elif kind == "textarea":
            control = f'<textarea name="{n}" rows="3"{required}>{esc(opt)}</textarea>'
        else:
            step = ' step="any"' if kind == "number" else ""
            control = f'<input type="{esc(kind)}" name="{n}" value="{esc(opt)}"{step}{required}>'
        out.append(f"<label>{esc(label)}{control}</label>")
    out.append(f"<button>{esc(button)}</button></form>")
    return Safe("".join(out))


CSS = """
:root{--bg:#f7f8fa;--fg:#1d2433;--muted:#667085;--brand:#0b6e4f;--card:#fff;--line:#e4e7ec;--warn:#b42318}
@media(prefers-color-scheme:dark){:root{--bg:#10141c;--fg:#e6e9ef;--muted:#9aa4b2;--brand:#3ecf8e;--card:#1a2030;--line:#2b3345;--warn:#f97066}}
*{box-sizing:border-box}body{margin:0;font:16px/1.55 system-ui,sans-serif;background:var(--bg);color:var(--fg)}
header{background:var(--card);border-bottom:1px solid var(--line);padding:.6rem 1rem}
header b{color:var(--brand)}nav{display:flex;flex-wrap:wrap;gap:.25rem 1rem;margin-top:.3rem}
main{max-width:900px;margin:0 auto;padding:1rem}a{color:var(--brand)}
form{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:1rem;margin:1rem 0}
label{display:block;margin:.5rem 0;font-size:.9rem;color:var(--muted)}
input,select,textarea{display:block;width:100%;padding:.5rem;margin-top:.2rem;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);font:inherit}
button{padding:.55rem 1.1rem;border:0;border-radius:8px;background:var(--brand);color:#fff;font:inherit;cursor:pointer;margin-top:.5rem}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;background:var(--card)}
th,td{padding:.45rem .6rem;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}th{font-size:.8rem;color:var(--muted)}
.badge{display:inline-block;padding:.05rem .5rem;border-radius:999px;background:var(--line);font-size:.8rem}
.badge.ok{background:#d1fadf;color:#05603a}.badge.bad{background:#fee4e2;color:var(--warn)}.badge.warn{background:#fef0c7;color:#93370d}
.bar{height:8px;background:var(--line);border-radius:4px;overflow:hidden;min-width:80px}.bar div{height:100%;background:var(--brand)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.75rem;margin:1rem 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:.8rem}.card small{color:var(--muted)}.card b{display:block;font-size:1.3rem}
.note{background:var(--card);border-left:4px solid var(--brand);padding:.5rem 1rem;color:var(--muted);margin:1rem 0}
footer{text-align:center;color:var(--muted);font-size:.8rem;padding:1.5rem}
@media print{header,footer,form,.noprint{display:none}body{background:#fff;color:#000}}
"""


# ---------------------------------------------------------------- request/response
class Request:
    def __init__(self, method, path, query, form, params, conn):
        self.method, self.path, self.query, self.form, self.params = method, path, query, form, params
        self.conn = conn

    def int(self, name):
        return int(self.params[name])

    def all(self, sql, *args):
        return self.conn.execute(sql, args).fetchall()

    def one(self, sql, *args):
        return self.conn.execute(sql, args).fetchone()

    def run(self, sql, *args):
        return self.conn.execute(sql, args).lastrowid


class Redirect:
    def __init__(self, to):
        assert to.startswith("/"), "only local redirects are allowed"
        self.to = to


class Download:
    def __init__(self, body, filename, content_type="text/csv; charset=utf-8"):
        self.body, self.filename, self.content_type = body, filename, content_type


class Page:
    def __init__(self, body, title=None, status=200, bare=False):
        self.body, self.title, self.status, self.bare = body, title, status, bare


# ---------------------------------------------------------------- the app
class App:
    def __init__(self, title, schema, db_name="data.db", nav=()):
        self.title, self.schema, self.nav = title, schema, list(nav)
        self.routes, self.seed = [], None
        default = Path(sys.argv[0]).resolve().parent / db_name
        self.db_path = os.environ.get("APP_DB") or str(default)

    # decorators
    def route(self, pattern, methods=("GET",)):
        def wrap(fn):
            self.routes.append((re.compile(pattern), methods, fn))
            return fn
        return wrap

    def seed_data(self, fn):
        self.seed = fn
        return fn

    # database
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self):
        conn = self.connect()
        try:
            conn.executescript(self.schema)
            conn.execute("CREATE TABLE IF NOT EXISTS _meta (k TEXT PRIMARY KEY, v TEXT)")
            if self.seed and not conn.execute("SELECT 1 FROM _meta WHERE k='seeded'").fetchone():
                self.seed(conn)
                conn.execute("INSERT INTO _meta VALUES ('seeded', '1')")
            conn.commit()
        finally:
            conn.close()

    # page layout
    def layout(self, title, body):
        links = "".join(f'<a href="{esc(h)}">{esc(t)}</a>' for h, t in self.nav)
        return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{esc(title)} - {esc(self.title)}</title><style>{CSS}</style></head><body>'
                f'<header><b>{esc(self.title)}</b><nav>{links}</nav></header>'
                f'<main><h1>{esc(title)}</h1>{body}</main>'
                f'<footer>Runs offline on your own computer.</footer></body></html>')

    # request handling (no sockets needed, so it is easy to test)
    def handle(self, method, raw_path, form=None):
        url = urlparse(raw_path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        for pattern, methods, fn in self.routes:
            m = pattern.fullmatch(unquote(url.path))
            if not (m and method in methods):
                continue
            conn = self.connect()
            try:
                result = fn(Request(method, url.path, query, form or {}, m.groupdict(), conn))
                conn.commit()
            except Exception:
                conn.rollback()
                traceback.print_exc()
                return self._page(Page("<p>Something went wrong. Check the terminal.</p>", "Error", 500))
            finally:
                conn.close()
            return self._respond(result)
        return self._page(Page("<p>That page does not exist.</p>", "Not found", 404))

    def _respond(self, result):
        if isinstance(result, Redirect):
            return 303, {"Location": result.to}, b""
        if isinstance(result, Download):
            headers = {"Content-Type": result.content_type,
                       "Content-Disposition": f'attachment; filename="{result.filename}"'}
            return 200, headers, result.body.encode("utf-8")
        if not isinstance(result, Page):
            result = Page(str(result))
        return self._page(result)

    def _page(self, page):
        title = page.title or self.title
        text = page.body if page.bare else self.layout(title, page.body)
        return page.status, {"Content-Type": "text/html; charset=utf-8"}, text.encode("utf-8")

    # server
    def run(self):
        parser = argparse.ArgumentParser(description=self.title)
        parser.add_argument("--host", default="127.0.0.1", help="0.0.0.0 shares it on your LAN")
        parser.add_argument("--port", type=int, default=8000)
        args = parser.parse_args()
        self.init_db()
        site = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, status, headers, body):
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._send(*site.handle("GET", self.path))

            def do_POST(self):
                size = int(self.headers.get("Content-Length", 0))
                data = parse_qs(self.rfile.read(size).decode("utf-8"))
                self._send(*site.handle("POST", self.path, {k: v[0] for k, v in data.items()}))

            def log_message(self, fmt, *a):
                print(fmt % a)

        print(f"{self.title}: open http://{args.host}:{args.port}  (Ctrl+C to stop)")
        ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


# ---------------------------------------------------------------- testing
class AppTestCase(unittest.TestCase):
    """Subclass and set `site = your_module.site`. Each test gets a fresh temporary database."""
    site = None

    def setUp(self):
        fd, self.db_file = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.site.db_path = self.db_file
        self.site.init_db()

    def tearDown(self):
        os.unlink(self.db_file)

    def get(self, path):
        status, _, body = self.site.handle("GET", path)
        return status, body.decode("utf-8")

    def post(self, path, **form):
        status, headers, body = self.site.handle("POST", path, form)
        return status, headers.get("Location"), body.decode("utf-8")

    def db(self):
        return self.site.connect()

    def test_nav_pages_load(self):
        if self.site is None:
            self.skipTest("base class")
        for href, _ in self.site.nav:
            status, _ = self.get(href)
            self.assertEqual(status, 200, href)

    def test_unknown_page_is_404(self):
        if self.site is None:
            self.skipTest("base class")
        self.assertEqual(self.get("/definitely-not-here")[0], 404)
