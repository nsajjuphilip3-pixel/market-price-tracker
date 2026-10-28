"""Market Price Tracker - crowd-sourced prices of food and produce across markets."""
from datetime import date, timedelta

from minikit import App, Page, Redirect, badge, bar, esc, form, link, num, table, today, ugx

# === STEP 1: Database and sample markets ===
SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, district TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY, market_id INTEGER NOT NULL REFERENCES markets(id),
    commodity TEXT NOT NULL, unit TEXT NOT NULL, price REAL NOT NULL CHECK (price > 0),
    reported_on TEXT NOT NULL, suspicious INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_prices_commodity ON prices(commodity, reported_on);
"""
site = App("Market Prices", SCHEMA, "prices.db",
           nav=[("/", "Today's prices"), ("/report", "Report a price"), ("/markets", "Markets")])
COMMODITIES = ["Matooke", "Maize flour", "Beans", "Rice", "Cassava", "Irish potatoes", "Tomatoes", "Onions", "Cooking oil"]
UNITS = ["kg", "bunch", "litre", "heap", "sack"]


@site.seed_data
def seed(conn):
    conn.executemany("INSERT INTO markets (name, district) VALUES (?, ?)", [
        ("Owino", "Kampala"), ("Nakasero", "Kampala"), ("Masaka Central", "Masaka"), ("Mbarara Municipal", "Mbarara"),
        ("Gulu Main", "Gulu"), ("Mbale Main", "Mbale"), ("Jinja Central", "Jinja")])


# === STEP 2: Statistics that resist bad data ===
def median(values):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return None
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def is_suspicious(new_price, recent_prices):
    """Flag a price that is 3x higher or lower than the recent median (likely a typing mistake)."""
    m = median(recent_prices)
    return m is not None and (new_price > 3 * m or new_price < m / 3)


def trend(this_week, last_week):
    """Percentage change between two median prices, or None if we have no comparison."""
    if not this_week or not last_week:
        return None
    return 100 * (this_week - last_week) / last_week


# === STEP 3: Reporting a price ===
@site.route("/report", ("GET", "POST"))
def report(req):
    note = ""
    if req.method == "POST":
        price, commodity = num(req.form["price"]), req.form["commodity"]
        if price <= 0:
            note = '<p class="note">Price must be more than zero.</p>'
        else:
            recent = [r["price"] for r in req.all(
                "SELECT price FROM prices WHERE commodity=? AND unit=? ORDER BY id DESC LIMIT 20", commodity, req.form["unit"])]
            flag = int(is_suspicious(price, recent))
            req.run("INSERT INTO prices (market_id, commodity, unit, price, reported_on, suspicious) VALUES (?,?,?,?,?,?)",
                    int(req.form["market_id"]), commodity, req.form["unit"], price, req.form.get("reported_on") or today(), flag)
            note = '<p class="note">Thank you! ' + ("That price looks unusual, so it is hidden from averages until checked." if flag else "Price saved.") + "</p>"
    markets = [(m["id"], f"{m['name']} ({m['district']})") for m in req.all("SELECT * FROM markets ORDER BY name")]
    return note + form("/report", [("market_id", "Market", "select", markets), ("commodity", "Commodity", "select", COMMODITIES),
                                   ("unit", "Unit", "select", UNITS), ("price", "Price (UGX)", "number"),
                                   ("reported_on", "Date", "date", today())], "Submit price")


# === STEP 4: The price board ===
def window_prices(req, commodity, start, end):
    return [r["price"] for r in req.all(
        "SELECT price FROM prices WHERE commodity=? AND suspicious=0 AND reported_on > ? AND reported_on <= ?",
        commodity, start, end)]


@site.route("/")
def board(req):
    now = date.fromisoformat(req.query.get("today", today()))
    d7, d14 = (now - timedelta(days=7)).isoformat(), (now - timedelta(days=14)).isoformat()
    rows = []
    for c in COMMODITIES:
        this_w, last_w = window_prices(req, c, d7, now.isoformat()), window_prices(req, c, d14, d7)
        if not this_w:
            continue
        t = trend(median(this_w), median(last_w))
        arrow = "" if t is None else badge(f"{t:+.0f}%", "bad" if t > 5 else "ok" if t < -5 else "")
        rows.append((link(f"/commodity/{c}", c), ugx(median(this_w)), f"{ugx(min(this_w))} - {ugx(max(this_w))}", len(this_w), arrow))
    return '<p class="note">Median of reports in the last 7 days. Click a commodity to compare markets.</p>' + \
        table(["Commodity", "Typical price", "Range", "Reports", "vs last week"], rows)


@site.route(r"/commodity/(?P<name>[^/]+)")
def commodity_page(req):
    name = req.params["name"].replace("%20", " ")
    rows = req.all("SELECT m.name, m.district, p.price, p.unit, p.reported_on FROM prices p JOIN markets m ON m.id=p.market_id "
                   "WHERE p.commodity=? AND p.suspicious=0 ORDER BY p.reported_on DESC, p.id DESC LIMIT 30", name)
    top = max([r["price"] for r in rows], default=1)
    shown = [(r["name"], r["district"], f"{ugx(r['price'])} / {r['unit']}", r["reported_on"], bar(100 * r["price"] / top)) for r in rows]
    return Page(f'<p>{link("/", "Back to the price board")}</p>' + table(["Market", "District", "Price", "Date", ""], shown), name)


# === STEP 5: Managing markets ===
@site.route("/markets", ("GET", "POST"))
def markets(req):
    if req.method == "POST":
        req.run("INSERT OR IGNORE INTO markets (name, district) VALUES (?,?)", req.form["name"].strip(), req.form["district"].strip())
        return Redirect("/markets")
    rows = [(m["name"], m["district"]) for m in req.all("SELECT * FROM markets ORDER BY district, name")]
    return form("/markets", [("name", "Market name"), ("district", "District")], "Add market") + table(["Market", "District"], rows)


if __name__ == "__main__":
    site.run()
