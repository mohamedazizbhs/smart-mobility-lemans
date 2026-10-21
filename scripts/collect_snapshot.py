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
