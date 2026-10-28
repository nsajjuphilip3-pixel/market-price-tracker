# Market Price Tracker: build it step by step

*App 05 of 26 in the Uganda Apps series. Needs only Python 3.8+ (no internet, no pip).*

## The problem

Farmers often sell to the first middleman who offers a price because they do not know what produce fetches in the next town. Buyers and families have the same problem. A shared price board, filled in by anyone who visits a market, gives everybody the same information.

## What you will learn

- Designing for crowd-sourced (untrusted) data
- Medians versus averages, and why the median is better when data has mistakes
- Detecting outliers and quarantining them
- Time-window queries and trends
- Database indexes

## Before you start

1. Read `../MINIKIT-GUIDE.md` once (10 minutes). It explains the small toolkit this app uses.
2. Make an empty folder, copy `minikit.py` into it, and create an empty `app.py` and a `tests/` folder.
3. Type each step below into `app.py` **in order** (steps are separated by `# === STEP n ===` comment lines).
4. This folder also contains the finished `app.py` and tests to compare against when something breaks.
5. Tip: you can add the last two lines (`if __name__ == "__main__": site.run()`) to the bottom early and run the app after any step to see progress.

## Data design

`prices` has one row per report. `CHECK (price > 0)` blocks nonsense values at the database level and `suspicious` marks values that look like typing errors. An index on `(commodity, reported_on)` speeds up the board query when there are thousands of reports.

## Build it

### Step 1: Database and sample markets

Create the tables, a list of commodities and units, and seed some well-known markets. Add your own district's markets from the Markets page.

**`app.py`** (top of the file)

```python
"""Market Price Tracker - crowd-sourced prices of food and produce across markets."""
from datetime import date, timedelta

from minikit import App, Page, Redirect, badge, bar, esc, form, link, num, table, today, ugx

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
```

### Step 2: Statistics that resist bad data

Three small pure functions. `median()` ignores extreme values, so one person typing 90000 instead of 900 cannot wreck the board the way they would with an average. `is_suspicious()` flags prices more than 3 times above or below the recent median. `trend()` gives the percentage change between two weeks.

**`app.py`** (add below the previous step)

```python
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
```

### Step 3: Reporting a price

The report form validates the price, checks it against recent prices, and saves it with a suspicious flag where needed. The user is told what happened rather than silently dropped.

**`app.py`** (add below the previous step)

```python
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
```

### Step 4: The price board

The price board loops over commodities and, for each, calculates the median for the last 7 days and the week before. The `?today=` query parameter lets tests (and you) look at any date. Each commodity links to a page comparing markets, with a bar for quick visual comparison.

**`app.py`** (add below the previous step)

```python
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
```

### Step 5: Managing markets

A page for adding markets so the app grows with its community.

**`app.py`** (add below the previous step)

```python
@site.route("/markets", ("GET", "POST"))
def markets(req):
    if req.method == "POST":
        req.run("INSERT OR IGNORE INTO markets (name, district) VALUES (?,?)", req.form["name"].strip(), req.form["district"].strip())
        return Redirect("/markets")
    rows = [(m["name"], m["district"]) for m in req.all("SELECT * FROM markets ORDER BY district, name")]
    return form("/markets", [("name", "Market name"), ("district", "District")], "Add market") + table(["Market", "District"], rows)


if __name__ == "__main__":
    site.run()
```

## Run it

```bash
python app.py
```

Open **http://127.0.0.1:8000**. Stop with `Ctrl+C`. To share on your LAN or phone hotspot use `python app.py --host 0.0.0.0`.

## Test it

The tests in `tests/test_app.py` check the pure functions and the web pages (without starting a server). Read them: they show how every feature is supposed to behave.

```bash
python -m unittest discover -s tests
```

## Exercises

- Add a "cheapest market for this commodity" line on the commodity page.
- Add a `reporter` field and show how many reports each person made.
- Make the 3x outlier rule a setting.

## Ideas to extend

- Collect prices by SMS or USSD so farmers without smartphones can contribute
- Draw a small price-history line chart
- Let a trusted moderator approve suspicious prices

## Responsible use

This app only becomes useful when real people use it. Start with one market and a few commodities, and share it with a farmers' group.

## Publish it

See the GitHub section of `../MINIKIT-GUIDE.md`. Describe where your data came from, and never commit `.db` files (already in `.gitignore`).
