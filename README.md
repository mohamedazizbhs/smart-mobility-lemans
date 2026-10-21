# Student manual — Smart Mobility Le Mans

*Companion to `TD_2_DELIVERY_MANUAL_smart_mobility_lemans.md` (the full technical
reference, with verification evidence and troubleshooting) and
`project3_smart_mobility_lemans.md` (the open project brief this TD prepares you
for). This document has the same code, reorganized around what you're actually
practicing — and it asks you real questions along the way. It is not a programming
exercise: every code block is given to you to paste as-is. What you're being asked to
think about is the data engineering and BI judgment around that code — what to
collect, how to clean it, what to store and why, how to define a KPI, and how to turn
numbers into something that supports a real decision.*

**Before you start:** create a file called `REFLECTIONS.md` at the root of your repo.
Every "Reflection" box in this document asks a short, concrete question (2-4
sentences is enough) — answer it there, as you go, not all at once at the end. A
consolidated list of every question is at the end of this document so you can check
you've answered them all.

**Everything below happens in a web browser on github.com. No local install
required.** Estimated time: 60-90 minutes for the guided build, plus open-ended time
for the final "on your own" section.

---

## Before you build anything

The real business question behind this TD, taken from `project3_smart_mobility_lemans.md`:

> If Le Mans Métropole had limited resources to improve its public transport network,
> where and when should it prioritize interventions?

This is a CM1-style decision-support question, not a "visualize some transit data"
exercise — everything below exists to help someone actually answer it. Two honest
limits are worth knowing before you build anything, not after: **no transit agency
publishes real ridership data**, so any "supply vs. demand" answer here is built on a
proxy, not real demand; and **GTFS-RT has no historical archive**, so "recurring
patterns" and "prediction" are only answerable once your own pipeline has been
running for weeks, not on day one.

> **Reflection 1.** Look at the business question's sub-questions in
> `project3_smart_mobility_lemans.md` (the section "The system should help answer").
> Before building anything: which one or two of these do you think today's guided
> build will already answer well, and which do you suspect will need real judgment
> calls from you later? You'll revisit this after the final section.

## What you're building

Two independent automated pipelines feeding one dashboard:

1. **Static reference pipeline** (runs occasionally): downloads SETRAM's official
   GTFS feed (routes, stops, scheduled trips), computes how many scheduled trips
   serve each stop on a representative weekday, and assigns each stop to its nearest
   Le Mans Métropole commune.
2. **Real-time snapshot pipeline** (runs every 15 minutes, all day, every day): reads
   SETRAM's live GTFS-RT feeds (actual vs. scheduled arrival times, service alerts),
   computes a compact per-route delay summary, appends it to a growing historical
   log, and updates the live dashboard.

```
smart-mobility-lemans/
  .github/workflows/
    build_static_reference.yml    # occasional: rebuild the schedule-based reference
    collect_snapshot.yml           # every 15 minutes: live delay/alert snapshot
  data/
    reference/
      communes.csv                 # Le Mans Métropole's 20 communes: name, lat, lon, population
    gtfs_static/
      stops_frequency.csv          # generated: scheduled trips/day per stop + nearest commune
      routes.csv                   # generated: route reference (id, short name, long name)
    history/
      route_delays_YYYY-MM.csv     # generated, appended every 15 min, monthly files
      alerts_log.csv                # generated, appended whenever an alert is active
  scripts/
    build_static_reference.py
    collect_snapshot.py
  docs/                            # GitHub Pages source
    index.html
    data/
      current_state.json           # generated, overwritten every snapshot
  README.md
```

---

## Stage 1 — Acquisition, twice over

*Connects to CM3 — acquisition patterns, and the question CM3 keeps asking of any
source: how fresh is this, how reliable is this, and what breaks if the source
changes?*

This project genuinely contrasts two acquisition cadences against the same kind of
source (official, key-free, government open data): a **static** feed you pull
occasionally, and a **live** feed you pull constantly. Both are real:

- **Static GTFS** (routes, stops, scheduled trips):
  `https://www.data.gouv.fr/api/1/datasets/r/5339d96c-6d20-4a01-939a-40f7b56d6cc1` —
  66 routes, 1,799 stops, 9,715 trips, 214,507 scheduled stop-times. The feed has a
  validity window (a few months) and gets periodically replaced by SETRAM — the URL
  is the stable part, its contents update on their own schedule.
- **GTFS-RT TripUpdate** (live vs. scheduled arrival times):
  `https://proxy.transport.data.gouv.fr/resource/setram-lemans-gtfs-rt-trip-update` —
  protobuf binary, no key. 27 active routes reporting, 5,000+ individual stop-time
  updates per snapshot in normal conditions.
- **GTFS-RT Alert** (active service disruptions):
  `https://proxy.transport.data.gouv.fr/resource/setram-lemans-gtfs-rt-service-alert`
  — protobuf binary, no key. Don't be alarmed if the one active alert you see is a
  literal test message rather than a real disruption; the pipeline parses and
  displays it identically either way, since a test alert has the same structure as a
  real one.
- **Commune population** — the demand-side **proxy** used later (transit agencies
  don't publish real ridership, so this stands in for it): INSEE's legal population
  figures for Le Mans Métropole's 20 communes. Commune center coordinates were
  geocoded via France's official address API, not estimated. This is your
  **enrichment** data (per the project brief's pipeline table) — it doesn't come from
  SETRAM at all, it's joined in later to give the schedule data geographic and
  demographic meaning.

> **Reflection 2.** Before reading the workflow steps later in this document: the
> static feed will run on a monthly schedule, the real-time feed every 15 minutes.
> Both *could* technically run every 15 minutes. Write your own guess now for why the
> static one doesn't — you'll check it against Stage 5's reasoning.

### Step 1 — Create the repository

Public repository (GitHub Pages on a free account requires it), name it
`smart-mobility-lemans` or your choice.

### Step 2 — Allow workflows to write to the repo

**Settings → Actions → General → Workflow permissions → "Read and write
permissions" → Save.** Both workflows in this project commit their own output back
to the repo; without this, every run fails on `git push`.

### Step 3 — Add the communes reference data (`data/reference/communes.csv`)

**Add file → Create new file** → `data/reference/communes.csv` → paste:

```csv
commune,lat,lon,population
Le Mans,47.993335,0.191169,148876
Allonnes,47.960493,0.150194,10846
Coulaines,48.030875,0.208443,8226
Arnage,47.930086,0.195402,5548
Sarge-les-le-Mans,48.040678,0.249355,3941
Yvre-l-Eveque,48.026286,0.271411,4269
Champagne,48.014163,0.331368,3728
Ruaudin,47.945001,0.261633,3542
Mulsanne,47.918943,0.248322,5352
Saint-Saturnin,48.054627,0.164448,2864
Rouillon,47.995585,0.141409,2666
La-Milesse,48.06312,0.132381,2650
La-Chapelle-Saint-Aubin,48.035132,0.156778,2319
Saint-Georges-du-Bois,47.972349,0.102337,2308
Trange,48.03046,0.111992,1678
Aigne,48.066061,0.111904,1724
Pruille-le-Chetif,47.990274,0.114073,1357
Chaufour-Notre-Dame,48.024716,0.079083,1187
Fatines,48.047884,0.332902,937
Fay,48.008039,0.074566,770
```

Commit directly to `main`.

---

## Stage 2 — Cleaning & structuring

*Connects to CM3's acquisition-to-structuring handoff, and a real, common data-quality
trap: letting a tool silently guess a column's type.*

Real GTFS files mix numeric-looking IDs (`"1001"`) with non-numeric ones
(`"FLEX-381"`) in what's nominally the "same" ID column, across different files that
later need to be joined together.

> **Reflection 3.** Before running anything: if a tool infers each file's column
> types automatically and independently (so one file's `stop_id` column becomes
> numbers, another file's `stop_id` column stays text, just because of what values
> happened to appear in each file), what goes wrong when you try to join those two
> files on `stop_id`? Write your prediction, then compare it to the comment in the
> script below explaining why every GTFS file is read with `dtype=str`.

### Step 4 — Add the static reference builder (`scripts/build_static_reference.py`)

**Add file → Create new file** → `scripts/build_static_reference.py` → paste:

```python
import csv, io, math, os, zipfile
import requests
import pandas as pd

GTFS_URL = "https://www.data.gouv.fr/api/1/datasets/r/5339d96c-6d20-4a01-939a-40f7b56d6cc1"

def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))

def fetch_gtfs_zip(retries=4, backoff=5):
    import time
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(GTFS_URL, timeout=(15, 60))
            resp.raise_for_status()
            return zipfile.ZipFile(io.BytesIO(resp.content))
        except requests.exceptions.RequestException as e:
            last_error = e
            print(f"  GTFS download attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(backoff * attempt)
    raise RuntimeError(f"Could not download GTFS after {retries} attempts") from last_error

def nearest_commune(lat, lon, communes):
    best_name, best_dist = None, None
    for c in communes:
        d = haversine_km(lat, lon, c["lat"], c["lon"])
        if best_dist is None or d < best_dist:
            best_dist, best_name = d, c["commune"]
    return best_name

def main():
    communes_df = pd.read_csv("data/reference/communes.csv")
    communes = communes_df.to_dict("records")

    print("Downloading SETRAM static GTFS feed...")
    zf = fetch_gtfs_zip()

    # dtype=str throughout: stop_id/route_id/trip_id mix numeric-looking and
    # non-numeric values (e.g. "FLEX-381") across GTFS files -- letting pandas
    # infer dtypes per-file causes silent int64-vs-object merge failures.
    routes = pd.read_csv(zf.open("routes.txt"), dtype=str)
    stops = pd.read_csv(zf.open("stops.txt"), dtype=str)
    trips = pd.read_csv(zf.open("trips.txt"), dtype=str)
    calendar = pd.read_csv(zf.open("calendar.txt"), dtype=str)
    stop_times = pd.read_csv(zf.open("stop_times.txt"), usecols=["trip_id", "stop_id"], dtype=str)
    stops["stop_lat"] = stops["stop_lat"].astype(float)
    stops["stop_lon"] = stops["stop_lon"].astype(float)
    print(f"Loaded {len(routes)} routes, {len(stops)} stops, {len(trips)} trips, {len(stop_times)} stop_times")

    # Pick a representative weekday: the Tuesday service pattern with the
    # longest validity window (avoids picking a one-off exception date).
    calendar["date_span"] = (
        pd.to_datetime(calendar["end_date"], format="%Y%m%d")
        - pd.to_datetime(calendar["start_date"], format="%Y%m%d")
    )
    tue_services = calendar[calendar["tuesday"] == "1"].sort_values("date_span", ascending=False)
    if tue_services.empty:
        raise RuntimeError("No Tuesday service found in calendar.txt -- feed structure may have changed")
    service_id = tue_services.iloc[0]["service_id"]
    print(f"Using service_id={service_id} as the representative weekday")

    weekday_trip_ids = set(trips[trips["service_id"] == service_id]["trip_id"])
    weekday_stop_times = stop_times[stop_times["trip_id"].isin(weekday_trip_ids)]

    freq = weekday_stop_times.groupby("stop_id").size().reset_index(name="daily_trip_count")
    freq = freq.merge(
        stops[["stop_id", "stop_name", "stop_lat", "stop_lon", "wheelchair_boarding"]],
        on="stop_id", how="left",
    ).dropna(subset=["stop_lat"])

    print(f"Assigning {len(freq)} stops to nearest of {len(communes)} communes...")
    freq["nearest_commune"] = freq.apply(
        lambda row: nearest_commune(row["stop_lat"], row["stop_lon"], communes), axis=1
    )

    freq = freq.sort_values("daily_trip_count", ascending=False)
    os.makedirs("data/gtfs_static", exist_ok=True)
    freq.to_csv("data/gtfs_static/stops_frequency.csv", index=False)
    routes[["route_id", "route_short_name", "route_long_name", "route_type"]].to_csv(
        "data/gtfs_static/routes.csv", index=False
    )
    print(f"Wrote data/gtfs_static/stops_frequency.csv ({len(freq)} rows)")
    print(f"Wrote data/gtfs_static/routes.csv ({len(routes)} rows)")
    print("Top 5 busiest stops:")
    print(freq[["stop_name", "daily_trip_count", "nearest_commune"]].head(5).to_string(index=False))

if __name__ == "__main__":
    main()
```

**How you'll know this worked**, once you run it in Stage 6: the "Top 5 busiest
stops" the script prints should be genuinely central Le Mans hubs (a main station, a
town hall) — not random suburbs. That's not a coincidence you should ignore; it's
the same "does this number make sense" sanity habit this whole course keeps
returning to. If your busiest stops look implausible, the join logic is worth
re-checking before you trust anything downstream of it.

Also notice the "representative weekday" logic: rather than picking an arbitrary
date, it picks the Tuesday service pattern with the *longest validity window* — a
deliberate choice to avoid a one-off calendar exception skewing the whole reference
dataset.

---

## Stage 3 — Storage & versioning

*Connects to CM4 — a pipeline stage isn't just "compute a number," it's a durable
decision about what to keep, at what granularity, for how long.*

A single snapshot of the real-time feed contains 5,000+ individual stop-time
updates. This project needs that snapshot every 15 minutes, all day, for the life of
the course.

> **Reflection 4.** Before reading further: roughly how many individual stop-time
> update rows would a 12-week semester of 15-minute snapshots produce, if you logged
> every one of them? (Order of magnitude is the point, not exact math.) Now compare
> that to logging one row **per route** per snapshot instead (there are only 27-40
> routes). What real analytical question — something a transport planner might
> actually ask — becomes harder to answer with the per-route version? Keep your
> answer; you'll need it again in the final section.

### Step 5 — Add the real-time snapshot collector (`scripts/collect_snapshot.py`)

**Add file → Create new file** → `scripts/collect_snapshot.py` → paste:

```python
import csv, json, os, time
from collections import defaultdict
import requests
import pandas as pd
from google.transit import gtfs_realtime_pb2

TRIP_UPDATE_URL = "https://proxy.transport.data.gouv.fr/resource/setram-lemans-gtfs-rt-trip-update"
ALERT_URL = "https://proxy.transport.data.gouv.fr/resource/setram-lemans-gtfs-rt-service-alert"

def fetch_feed(url, retries=4, backoff=5):
    """Same retry pattern as the EU capitals project's fetch_weather_batch, for
    the same reason: a single slow TLS handshake on a shared runner shouldn't
    fail an otherwise-healthy scheduled run."""
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=(15, 30))
            resp.raise_for_status()
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(resp.content)
            return feed
        except Exception as e:
            last_error = e
            print(f"  fetch attempt {attempt}/{retries} failed for {url}: {e}")
            if attempt < retries:
                time.sleep(backoff * attempt)
    raise RuntimeError(f"Unreachable after {retries} attempts: {url}") from last_error

def load_route_names():
    path = "data/gtfs_static/routes.csv"
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path, dtype=str)
    return {
        row["route_id"]: (row["route_short_name"] or row["route_id"])
        for _, row in df.iterrows()
    }

def compute_route_aggregates(trip_update_feed):
    per_route = defaultdict(lambda: {"delays": [], "n_skipped": 0, "n_trips": 0})
    for entity in trip_update_feed.entity:
        tu = entity.trip_update
        route_id = tu.trip.route_id or "UNKNOWN"
        per_route[route_id]["n_trips"] += 1
        for stu in tu.stop_time_update:
            if stu.schedule_relationship == 1:  # SKIPPED
                per_route[route_id]["n_skipped"] += 1
            delay = None
            if stu.HasField("arrival"):
                delay = stu.arrival.delay
            elif stu.HasField("departure"):
                delay = stu.departure.delay
            if delay is not None:
                per_route[route_id]["delays"].append(delay)
    rows = []
    for route_id, d in per_route.items():
        delays = d["delays"]
        rows.append({
            "route_id": route_id,
            "n_trips_observed": d["n_trips"],
            "n_stop_updates": len(delays),
            "n_skipped": d["n_skipped"],
            "avg_delay_s": round(sum(delays) / len(delays), 1) if delays else 0.0,
            "max_delay_s": max(delays) if delays else 0,
        })
    return rows

def extract_alerts(alert_feed):
    alerts = []
    for e in alert_feed.entity:
        a = e.alert
        routes_affected = [ie.route_id for ie in a.informed_entity if ie.route_id]
        header = a.header_text.translation[0].text if a.header_text.translation else ""
        alerts.append({"alert_id": e.id, "routes": ",".join(routes_affected), "header": header})
    return alerts

def append_csv(path, rows, fieldnames):
    file_exists = os.path.exists(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

def main():
    route_names = load_route_names()

    print("Fetching TripUpdate feed...")
    tu_feed = fetch_feed(TRIP_UPDATE_URL)
    snapshot_ts = tu_feed.header.timestamp
    route_rows = compute_route_aggregates(tu_feed)
    for r in route_rows:
        r["snapshot_ts"] = snapshot_ts
    print(f"Computed aggregates for {len(route_rows)} routes")

    print("Fetching Alert feed...")
    alert_feed = fetch_feed(ALERT_URL)
    alerts = extract_alerts(alert_feed)
    for a in alerts:
        a["snapshot_ts"] = snapshot_ts
    print(f"Found {len(alerts)} active alerts")

    month_key = time.strftime("%Y-%m", time.gmtime(snapshot_ts))
    append_csv(
        f"data/history/route_delays_{month_key}.csv", route_rows,
        ["snapshot_ts", "route_id", "n_trips_observed", "n_stop_updates", "n_skipped", "avg_delay_s", "max_delay_s"],
    )
    if alerts:
        append_csv(
            "data/history/alerts_log.csv", alerts,
            ["snapshot_ts", "alert_id", "routes", "header"],
        )

    # current_state.json for the live dashboard
    for r in route_rows:
        r["route_name"] = route_names.get(r["route_id"], r["route_id"])
    route_rows.sort(key=lambda r: r["avg_delay_s"], reverse=True)
    all_delays = [r["avg_delay_s"] for r in route_rows]
    network_avg_delay = round(sum(all_delays) / len(all_delays), 1) if all_delays else 0.0

    current_state = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(snapshot_ts)),
        "network_avg_delay_s": network_avg_delay,
        "n_routes_reporting": len(route_rows),
        "routes": route_rows,
        "alerts": alerts,
    }
    os.makedirs("docs/data", exist_ok=True)
    with open("docs/data/current_state.json", "w") as f:
        json.dump(current_state, f, indent=2)
    print(f"Wrote docs/data/current_state.json (network avg delay = {network_avg_delay}s)")

if __name__ == "__main__":
    main()
```

**How you'll know this worked:** each run should append (never overwrite) to the
monthly history file — the header line should appear exactly once no matter how many
times the script has run. Real transit data is messy in informative ways: a past run
of this exact script found one route averaging over two minutes of delay, with a
single trip 43 minutes late — a genuine, real disruption. Don't be surprised if your
own run turns up something similarly extreme; that's a sign the pipeline is
capturing real operational reality, not a bug to distrust.

### Step 6 — Add a placeholder for the live dashboard's data (`docs/data/current_state.json`)

**Add file → Create new file** → `docs/data/current_state.json` → paste:

```json
{
  "generated_at": "not yet generated",
  "network_avg_delay_s": 0,
  "n_routes_reporting": 0,
  "routes": [],
  "alerts": []
}
```

---

## Stage 4 — KPI definition & visualization for decision support

*Connects to CM2 (a KPI is a construct you choose, not a neutral fact) and CM1
(a dashboard exists to support a specific decision, for a specific audience).*

`collect_snapshot.py` already computed the raw ingredients: average delay, skipped
stops, active alerts. The dashboard below turns those into KPI cards and a colored
chart — but the coloring rule embeds a real, debatable choice: a bus running *very
early* is rendered as good (green), no matter how early; a bus running *very late* is
rendered as bad (red), scaling with lateness. A single green-to-red spectrum, one
axis, one story.

> **Reflection 5.** Is that the right way to encode this KPI? A bus arriving very
> early can strand a waiting passenger just as effectively as a very late one — from
> a passenger's perspective, both extremes might be "bad." Propose an alternative
> color/encoding rule for this same chart, and explain what decision or conclusion a
> viewer would reach *differently* under your rule versus the one below.

### Step 7 — Add the dashboard (`docs/index.html`)

**Add file → Create new file** → `docs/index.html` → paste:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Smart Mobility Le Mans — SETRAM network status</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  body { font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; }
  .kpis { display: flex; gap: 1rem; flex-wrap: wrap; margin: 1rem 0; }
  .kpi { flex: 1; min-width: 180px; padding: 0.8rem 1rem; border: 1px solid #ccc; border-radius: 8px; }
  .kpi .value { font-size: 1.6rem; font-weight: bold; color: #0d7c9e; }
  .kpi .label { font-size: 0.8rem; color: #666; }
  #alerts { padding: 0.8rem 1rem; border: 2px solid #c46e0a; border-radius: 8px; background: #faf3e8; }
  #alerts.none { border-color: #2c9c4a; background: #f0f8f2; }
  canvas { margin-top: 2rem; }
  #updated { color: #666; font-size: 0.85rem; }
</style>
</head>
<body>
  <h1>SETRAM network — current status</h1>
  <p>Real-time delay and disruption snapshot for Le Mans Métropole's bus and tram network.</p>
  <div class="kpis" id="kpis">Loading...</div>
  <div id="alerts">Loading alerts...</div>
  <canvas id="delayChart" height="320"></canvas>
  <p id="updated"></p>

<script>
fetch('data/current_state.json')
  .then(r => r.json())
  .then(data => {
    const routes = data.routes || [];

    document.getElementById('kpis').innerHTML = `
      <div class="kpi"><div class="value">${data.network_avg_delay_s.toFixed(1)}s</div><div class="label">Network average delay</div></div>
      <div class="kpi"><div class="value">${data.n_routes_reporting}</div><div class="label">Routes reporting</div></div>
      <div class="kpi"><div class="value">${data.alerts.length}</div><div class="label">Active alerts</div></div>
    `;

    document.getElementById('updated').textContent = `Data last updated ${data.generated_at}`;

    const alertsEl = document.getElementById('alerts');
    if (!data.alerts || data.alerts.length === 0) {
      alertsEl.classList.add('none');
      alertsEl.innerHTML = '<strong>No active alerts.</strong>';
    } else {
      alertsEl.innerHTML = '<strong>Active alerts:</strong><ul>' +
        data.alerts.map(a => `<li>[Route ${a.routes || '?'}] ${a.header}</li>`).join('') +
        '</ul>';
    }

    if (routes.length === 0) {
      document.getElementById('delayChart').outerHTML =
        '<p>No route data yet -- trigger the collect_snapshot workflow from the Actions tab.</p>';
      return;
    }

    function scoreToColor(t) {
      const clamped = Math.max(0, Math.min(1, t));
      const hue = 120 * clamped; // 0 = red (worst), 120 = green (best)
      return `hsl(${hue.toFixed(0)}, 70%, 45%)`;
    }
    function normalizeForColor(values, invert) {
      const lo = Math.min(...values);
      const hi = Math.max(...values);
      if (hi === lo) return values.map(() => 0.5);
      const scaled = values.map(v => (v - lo) / (hi - lo));
      return invert ? scaled.map(s => 1 - s) : scaled;
    }
    // lower delay = greener, higher delay = redder
    const colorNorm = normalizeForColor(routes.map(r => r.avg_delay_s), true);
    const barColors = colorNorm.map(t => scoreToColor(t));

    new Chart(document.getElementById('delayChart'), {
      type: 'bar',
      data: {
        labels: routes.map(r => r.route_name),
        datasets: [{
          label: 'Average delay (s)',
          data: routes.map(r => r.avg_delay_s),
          backgroundColor: barColors
        }]
      },
      options: {
        plugins: {
          legend: { display: false },
          title: { display: true, text: 'Average delay by route, this snapshot (green = on time/early, red = most delayed)' },
          tooltip: {
            callbacks: {
              title: (items) => {
                const r = routes[items[0].dataIndex];
                return `Route ${r.route_name}`;
              },
              label: (item) => {
                const r = routes[item.dataIndex];
                return [`Avg delay: ${r.avg_delay_s}s`, `Trips observed: ${r.n_trips_observed}`, `Skipped stops: ${r.n_skipped}`];
              }
            }
          }
        },
        scales: { y: { title: { display: true, text: 'Average delay (seconds)' } } }
      }
    });
  })
  .catch(err => {
    document.getElementById('kpis').innerHTML =
      '<p>Could not load network status (' + err + '). Check that ' +
      '<code>docs/data/current_state.json</code> exists in the repo.</p>';
  });
</script>
</body>
</html>
```

Three KPI cards, an alert banner, one chart — deliberately not more than that. Per
CM1's own rubric: every element here should be traceable to "what decision does this
help someone make," not "what could we compute from this data."

---

## Stage 5 — Automation & monitoring

*This is the course's primary CM4 case study — orchestration and scheduling as a
first-class design decision, not a technical default.*

### Step 8 — Add the static reference workflow (`.github/workflows/build_static_reference.yml`)

**Add file → Create new file** → `.github/workflows/build_static_reference.yml` → paste:

```yaml
name: Build static reference

"on":
  workflow_dispatch: {}
  schedule:
    - cron: "0 4 1 * *"

permissions:
  contents: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - run: pip install requests pandas
      - run: python scripts/build_static_reference.py
      - name: Commit updated reference data
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/gtfs_static/
          git commit -m "Update static GTFS reference [automated]" || echo "Nothing to commit"
          git push
```

Runs on demand, plus automatically at 04:00 UTC on the 1st of each month.

### Step 9 — Add the snapshot collection workflow (`.github/workflows/collect_snapshot.yml`)

**Add file → Create new file** → `.github/workflows/collect_snapshot.yml` → paste:

```yaml
name: Collect realtime snapshot

"on":
  workflow_dispatch: {}
  schedule:
    - cron: "*/15 * * * *"

permissions:
  contents: write

jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - run: pip install requests pandas gtfs-realtime-bindings
      - run: python scripts/collect_snapshot.py
      - name: Commit updated snapshot data
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/history/ docs/data/current_state.json
          git commit -m "Update realtime snapshot [automated]" || echo "Nothing to commit"
          git push
```

`*/15 * * * *` runs 24/7 rather than being restricted to SETRAM's actual service
hours, for simplicity — GitHub Actions minutes are unmetered for public
repositories, so the only real cost of the extra overnight runs is a slightly
noisier history file, not money or quota.

> **Reflection 6.** Now check your Reflection 2 guess against the real answer: why
> would a 15-minute schedule for the *static* GTFS reference be wasteful, and why
> would a monthly schedule for the *real-time* delay snapshots make the whole
> real-time picture useless? Answer both halves — the mismatch runs in both
> directions.

---

## Running it for real

### Step 10 — Turn on GitHub Pages

**Settings → Pages → Source: "Deploy from a branch" → Branch: `main`, folder:
`/docs` → Save.**

### Step 11 — Run the static reference workflow for the first time

**Actions tab → "Build static reference" → Run workflow → Run workflow.** Expect
30-60 seconds (it's downloading and processing a ~2.4MB GTFS zip with over 200,000
scheduled stop-times). Confirm a green checkmark, then check
`data/gtfs_static/stops_frequency.csv` and `routes.csv` exist with real content.

### Step 12 — Run the snapshot collector for the first time

**Actions tab → "Collect realtime snapshot" → Run workflow → Run workflow.** Confirm
green, then check `docs/data/current_state.json` shows real route data (not the
Step 6 placeholder).

### Step 13 — Open the live dashboard

Visit your Pages URL (`https://<username>.github.io/smart-mobility-lemans/`).

### Step 14 — Confirm the automation is actually running unattended

Wait at least 15-20 minutes (or trigger "Collect realtime snapshot" manually two or
three times a few minutes apart, to simulate it), then reload the dashboard and
confirm the `generated_at` timestamp has advanced and the history CSV has grown.
This — not the first manual run — is the actual deliverable: a pipeline that keeps
itself current without you.

### Step 15 — Sanity-check the numbers against reality

> **Reflection 7.** Pick one route currently showing a large delay on your
> dashboard. Compare it against
> [SETRAM's own live departure information](https://www.setram.fr/) or plain common
> sense (is there a known local event, roadwork, rush hour?). Did the number match
> what you'd expect? If not, what's your best guess for the discrepancy — a real
> disruption, a data artifact, or something else? This is the same "does this number
> make sense" habit this whole course keeps returning to; write what you actually
> found, not what you expected to find.

*If something breaks and you can't figure out why, check the Troubleshooting section
of `TD_2_DELIVERY_MANUAL_smart_mobility_lemans.md` or ask your instructor.*

---

## On your own: turn the supply reference into a supply-vs-demand answer

Everything so far gets you a live dashboard and a static reference dataset — but it
stops short of the brief's central "where are there gaps between transport supply
and demand" question. That synthesis is yours to build.

> **Reflection 8.** Before writing any code: you're about to use commune
> **population** as a stand-in for real transport **demand**, because real ridership
> data doesn't exist as open data. Name one concrete, realistic way a commune could
> have *low* population but genuinely *high* transport demand (or the reverse) — so
> you go into this exercise already knowing the proxy's failure mode, not just its
> formula.

**What "done" looks like:**

- [ ] A new view (a table or chart on the dashboard, or a separate generated file —
      your call) ranking Le Mans Métropole's 20 communes by scheduled transport
      supply relative to population.
- [ ] You can explain your chosen metric in one sentence (e.g. "scheduled
      stop-visits per 1,000 residents").
- [ ] You've found, in your own actual output, at least one commune where the
      metric misleads — for instance, a commune whose one stop happens to be a depot
      or interchange with an unusually high scheduled-trip count will look extremely
      well-served by this measure without necessarily reflecting real accessibility
      for residents there.

**Hints, not answers:**

- Everything you need is already in `data/gtfs_static/stops_frequency.csv` (each
  stop's `daily_trip_count` and `nearest_commune`) and `data/reference/communes.csv`
  (each commune's `population`) — the join and rollup is pandas `groupby` + `merge`,
  the same operations `build_static_reference.py` already uses.
- Decide for yourself whether this belongs in `build_static_reference.py` (computed
  once a month alongside the rest of the static reference) or as a new script —
  think about which is more honest given how often the underlying numbers actually
  change.
- If you want this on the live dashboard, it needs to end up in a JSON file
  `docs/index.html` can `fetch()` — you've now seen this pattern
  (`current_state.json`) done twice.

> **Reflection 9.** State your chosen supply metric in one sentence. Then, using
> your own actual output (not a hypothetical), name one commune where the ranking
> looks wrong to you, and explain why — using what you actually know about that
> commune, not just the formula.

> **Reflection 10.** Go back to Reflection 4's answer about per-route vs. per-stop
> logging. If you wanted "which *stops* are affected by repeated delays" answered
> from real-time data (not the static schedule), you'd hit that same data-volume
> problem again. You don't have to build this — but describe, in a few sentences, one
> concrete approach you'd take to aggregate stop-level events so a semester of
> 15-minute snapshots stays a reasonably-sized, git-tracked file.

> **Reflection 11 (closing).** Return to Reflection 1. Which of the business
> question's sub-questions turned out to be answerable today, which needed real
> judgment calls from you, and which genuinely need weeks of accumulated history
> before they're answerable at all? Compare this to what you originally guessed.

---

## Reflection checklist

Make sure `REFLECTIONS.md` in your repo has an answer to each of these:

1. Which sub-questions of the central business question did you expect to be
   easy vs. hard, before building anything?
2. Your prediction for why the static GTFS feed doesn't also refresh every 15
   minutes.
3. Your prediction for what breaks when two files' "same" ID column gets
   auto-typed independently and then joined.
4. Order-of-magnitude row-count comparison: per-route vs. per-stop logging over a
   semester, and what question the per-route choice makes harder.
5. Your proposed alternative to the delay chart's early-good/late-bad color
   encoding, and what decision it would change.
6. The real reasoning for both halves of the static-vs-real-time scheduling
   mismatch.
7. What you actually found when you sanity-checked one delayed route against
   reality.
8. A concrete case where population would mislead as a demand proxy.
9. Your chosen supply-vs-population metric, and a real commune where it misleads.
10. Your proposed approach to aggregating stop-level delay events without
    blowing up the history file.
11. How your Reflection 1 predictions compared to what you actually found.

## Final delivery checklist

- [ ] Repository public, workflow permissions read/write.
- [ ] All files present: `data/reference/communes.csv`,
      `scripts/build_static_reference.py`, `scripts/collect_snapshot.py`,
      `docs/data/current_state.json`, `docs/index.html`,
      `.github/workflows/build_static_reference.yml`,
      `.github/workflows/collect_snapshot.yml`.
- [ ] At least one green run of **each** workflow visible in the Actions tab.
- [ ] `data/gtfs_static/stops_frequency.csv` and `routes.csv` exist with real
      content.
- [ ] `data/history/route_delays_<month>.csv` has grown across at least two
      separate runs.
- [ ] GitHub Pages live, dashboard shows real KPIs, a colored bar chart, and
      correct alert status.
- [ ] Supply-vs-population view completed.
- [ ] `REFLECTIONS.md` answers all 11 reflection questions.

Submit: the repository URL, the live Pages URL, and `REFLECTIONS.md`.
