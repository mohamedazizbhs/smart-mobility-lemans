
import csv
import io
import math
import os
import zipfile
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

    raise RuntimeError(
        f"Could not download GTFS after {retries} attempts"
    ) from last_error


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

    # Keep GTFS identifiers as strings
    routes = pd.read_csv(zf.open("routes.txt"), dtype=str)
    stops = pd.read_csv(zf.open("stops.txt"), dtype=str)
    trips = pd.read_csv(zf.open("trips.txt"), dtype=str)
    calendar = pd.read_csv(zf.open("calendar.txt"), dtype=str)

    stop_times = pd.read_csv(
        zf.open("stop_times.txt"),
        usecols=["trip_id", "stop_id"],
        dtype=str
    )

    stops["stop_lat"] = stops["stop_lat"].astype(float)
    stops["stop_lon"] = stops["stop_lon"].astype(float)

    print(
        f"Loaded {len(routes)} routes, {len(stops)} stops, "
        f"{len(trips)} trips, {len(stop_times)} stop_times"
    )

    # Select representative Tuesday schedule
    calendar["date_span"] = (
        pd.to_datetime(calendar["end_date"], format="%Y%m%d")
        - pd.to_datetime(calendar["start_date"], format="%Y%m%d")
    )

    tue_services = calendar[
        calendar["tuesday"] == "1"
    ].sort_values("date_span", ascending=False)

    if tue_services.empty:
        raise RuntimeError("No Tuesday service found in calendar.txt")

    service_id = tue_services.iloc[0]["service_id"]

    print(f"Using service_id={service_id}")

    weekday_trip_ids = set(
        trips[trips["service_id"] == service_id]["trip_id"]
    )

    weekday_stop_times = stop_times[
        stop_times["trip_id"].isin(weekday_trip_ids)
    ]

    # Calculate scheduled stop visits
    freq = (
        weekday_stop_times.groupby("stop_id")
        .size()
        .reset_index(name="daily_trip_count")
    )

    freq = freq.merge(
        stops[
            [
                "stop_id",
                "stop_name",
                "stop_lat",
                "stop_lon",
                "wheelchair_boarding"
            ]
        ],
        on="stop_id",
        how="left"
    ).dropna(subset=["stop_lat"])

    # Assign each stop to the nearest commune centre
    print(f"Assigning {len(freq)} stops to communes...")

    freq["nearest_commune"] = freq.apply(
        lambda row: nearest_commune(
            row["stop_lat"],
            row["stop_lon"],
            communes
        ),
        axis=1
    )

    freq = freq.sort_values(
        "daily_trip_count",
        ascending=False
    )

    os.makedirs("data/gtfs_static", exist_ok=True)

    freq.to_csv(
        "data/gtfs_static/stops_frequency.csv",
        index=False
    )

    routes[
        ["route_id", "route_short_name", "route_long_name", "route_type"]
    ].to_csv(
        "data/gtfs_static/routes.csv",
        index=False
    )

    print("Static reference files generated successfully.")

    print("Top 5 busiest stops:")
    print(
        freq[
            ["stop_name", "daily_trip_count", "nearest_commune"]
        ].head(5).to_string(index=False)
    )

    # ==========================================
    # SUPPLY VS POPULATION ANALYSIS
    # ==========================================

    supply = (
        freq.groupby("nearest_commune", as_index=False)["daily_trip_count"]
        .sum()
    )

    supply = supply.rename(
        columns={
            "nearest_commune": "commune",
            "daily_trip_count": "daily_supply"
        }
    )

    comparison = communes_df[
        ["commune", "population"]
    ].merge(
        supply,
        on="commune",
        how="left"
    )

    comparison["daily_supply"] = (
        comparison["daily_supply"].fillna(0)
    )

    comparison["supply_per_1000"] = (
        comparison["daily_supply"]
        / comparison["population"]
        * 1000
    ).round(2)

    comparison = comparison.sort_values(
        "supply_per_1000",
        ascending=False
    )

    # Save CSV for analysis
    comparison.to_csv(
        "data/gtfs_static/supply_population.csv",
        index=False
    )

    print("\nSUPPLY VS POPULATION RANKING:")
    print(comparison.to_string(index=False))

    # ==========================================
    # NEW: EXPORT JSON FOR GITHUB PAGES
    # ==========================================

    os.makedirs("docs/data", exist_ok=True)

    comparison.to_json(
        "docs/data/supply_population.json",
        orient="records",
        indent=2,
        force_ascii=False
    )

    print("\nCreated docs/data/supply_population.json")
    print(f"Number of communes: {len(comparison)}")


if __name__ == "__main__":
    main()
