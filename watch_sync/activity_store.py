"""Append-only JSON activity store with Intervals.icu sync.

Stores activities and wellness data at running_data/activity_log.json.
Each sync pulls new data and appends it, deduplicating by activity ID.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

from . import intervals_api

DEFAULT_STORE_PATH = "running_data/activity_log.json"


def load_store(path: str = DEFAULT_STORE_PATH) -> dict:
    """Load the activity store from disk, or return an empty one."""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"activities": [], "wellness": [], "last_sync": None}


def save_store(store: dict, path: str = DEFAULT_STORE_PATH) -> None:
    """Write the store back to JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)


def _existing_ids(store: dict) -> set[str]:
    """Get set of activity IDs already in the store."""
    return {a["id"] for a in store["activities"]}


def _build_activity_record(activity: dict, streams: dict | None) -> dict:
    """Build a normalized activity record from Intervals.icu data."""
    # Basic fields from activity summary
    record = {
        "id": activity.get("id", ""),
        "date": activity.get("start_date_local", "")[:10],
        "sport": activity.get("type", "Run"),
        "name": activity.get("name", ""),
        "distance_km": round(activity.get("distance", 0) / 1000, 2),
        "duration_sec": activity.get("moving_time", 0),
        "elapsed_sec": activity.get("elapsed_time", 0),
        "avg_hr": activity.get("average_heartrate"),
        "max_hr": activity.get("max_heartrate"),
        "avg_cadence": _halve_cadence(activity.get("average_cadence")),
        "total_ascent": activity.get("total_elevation_gain"),
        "calories": activity.get("calories"),
        "avg_watts": activity.get("icu_average_watts"),
    }

    # Computed pace
    dist = activity.get("distance", 0)
    moving = activity.get("moving_time", 0)
    if dist > 0 and moving > 0:
        record["avg_pace_sec_km"] = round(moving / (dist / 1000), 1)
    else:
        record["avg_pace_sec_km"] = None

    # Intervals.icu computed metrics
    record["icu_training_load"] = activity.get("icu_training_load")
    record["icu_ctl"] = activity.get("icu_ctl")
    record["icu_atl"] = activity.get("icu_atl")
    record["icu_ramp_rate"] = activity.get("icu_ramp_rate")
    record["icu_efficiency_factor"] = activity.get("icu_efficiency_factor")
    record["icu_hrrc"] = activity.get("icu_hrrc")
    record["decoupling"] = activity.get("decoupling")

    # VDOT estimate (from local computation)
    if dist >= 1500 and moving > 0:
        record["estimated_vdot"] = _estimate_vdot(moving, dist)
    else:
        record["estimated_vdot"] = None

    # Pace zones from Intervals.icu intervals (if available)
    intervals = activity.get("icu_intervals", [])
    record["pace_zones"] = _extract_pace_zones(intervals)

    # Per-km splits from Intervals.icu laps
    laps = activity.get("laps") or activity.get("icu_laps") or []
    record["km_splits"] = _extract_km_splits(laps)

    # Efficiency factor: pace / HR (lower = more efficient for same pace)
    if record["avg_pace_sec_km"] and record["avg_hr"]:
        record["efficiency_factor"] = round(
            record["avg_pace_sec_km"] / record["avg_hr"], 3
        )
    else:
        record["efficiency_factor"] = None

    return record


def _halve_cadence(cadence):
    """Intervals.icu reports cadence as full steps; halve if > 250."""
    if cadence is None:
        return None
    # Some APIs report double cadence (both feet); normalize to steps/min
    return round(cadence) if cadence < 250 else round(cadence / 2)


def _estimate_vdot(time_seconds: float, distance_m: float) -> float | None:
    """Estimate VDOT from Daniels' formula."""
    import math

    t = time_seconds / 60.0
    v = distance_m / t

    vo2 = -4.60 + 0.182258 * v + 0.000104 * v * v
    pct = (
        0.8
        + 0.1894393 * math.exp(-0.012778 * t)
        + 0.2989558 * math.exp(-0.1932605 * t)
    )
    if pct <= 0:
        return None
    return round(vo2 / pct, 1)


def _extract_pace_zones(intervals: list[dict]) -> dict[str, float]:
    """Extract pace zone distribution from Intervals.icu intervals."""
    # This is a simplified extraction; Intervals.icu provides zone data
    # in various formats depending on configuration
    zones = {"E": 0, "M": 0, "T": 0, "I": 0, "R": 0}
    total = 0
    for iv in intervals:
        label = (iv.get("label") or iv.get("type") or "").upper()
        duration = iv.get("moving_time") or iv.get("elapsed_time") or 0
        if "RECOVERY" in label or "EASY" in label or "WARMUP" in label or "COOLDOWN" in label:
            zones["E"] += duration
        elif "MARATHON" in label or "STEADY" in label:
            zones["M"] += duration
        elif "THRESHOLD" in label or "TEMPO" in label:
            zones["T"] += duration
        elif "INTERVAL" in label or "VO2" in label:
            zones["I"] += duration
        elif "REPETITION" in label or "SPRINT" in label:
            zones["R"] += duration
        else:
            zones["E"] += duration  # default to easy
        total += duration

    if total == 0:
        return {}
    return {z: round(t / total * 100, 1) for z, t in zones.items()}


def _extract_km_splits(laps: list[dict]) -> list[dict]:
    """Extract per-km splits from Intervals.icu laps."""
    splits = []
    for i, lap in enumerate(laps, 1):
        dist = lap.get("distance", 0)
        moving = lap.get("moving_time") or lap.get("elapsed_time") or 0
        if dist > 0 and moving > 0:
            pace = round(moving / (dist / 1000), 1)
        else:
            pace = None
        splits.append({
            "km": i,
            "pace": pace,
            "hr": lap.get("average_heartrate"),
        })
    return splits


def sync_activities(
    api_key: str, store: dict, days_back: int = 30, verbose: bool = True
) -> int:
    """Pull recent activities from Intervals.icu, append new ones to store.

    Returns the number of new activities added.
    """
    newest = datetime.now().strftime("%Y-%m-%d")
    oldest = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    if verbose:
        print(f"Fetching activities from {oldest} to {newest}...")

    activities = intervals_api.list_activities(api_key, oldest, newest)
    existing = _existing_ids(store)
    new_count = 0

    for activity in activities:
        act_id = activity.get("id", "")
        if not act_id or act_id in existing:
            continue

        if verbose:
            name = activity.get("name", "unnamed")
            date = activity.get("start_date_local", "")[:10]
            print(f"  Syncing: {date} — {name}")

        # Fetch full activity detail with intervals
        try:
            full = intervals_api.get_activity(api_key, act_id)
        except Exception as e:
            if verbose:
                print(f"    Warning: could not fetch detail for {act_id}: {e}")
            full = activity

        # Fetch streams (optional, don't fail if unavailable)
        streams = None
        try:
            streams = intervals_api.get_streams(api_key, act_id)
        except Exception:
            pass

        record = _build_activity_record(full, streams)
        store["activities"].append(record)
        existing.add(act_id)
        new_count += 1

    # Sort by date
    store["activities"].sort(key=lambda a: a.get("date", ""))
    store["last_sync"] = datetime.now().isoformat()

    if verbose:
        print(f"Synced {new_count} new activities ({len(store['activities'])} total).")

    return new_count


def sync_wellness(
    api_key: str, store: dict, days_back: int = 30, verbose: bool = True
) -> int:
    """Pull recent wellness data, merge into store.

    Returns the number of new/updated wellness records.
    """
    newest = datetime.now().strftime("%Y-%m-%d")
    oldest = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    if verbose:
        print(f"Fetching wellness data from {oldest} to {newest}...")

    wellness_list = intervals_api.get_wellness(api_key, oldest, newest)

    # Index existing wellness by date for merge
    existing_by_date = {w["date"]: i for i, w in enumerate(store["wellness"])}
    new_count = 0

    for w in wellness_list:
        date = w.get("id", "")  # wellness ID is the date string
        record = {
            "date": date,
            "resting_hr": w.get("restingHR"),
            "hrv": w.get("hrv"),
            "sleep_secs": w.get("sleepSecs"),
            "sleep_score": w.get("sleepScore"),
            "weight": w.get("weight"),
            "ctl": w.get("ctl"),
            "atl": w.get("atl"),
            "ramp_rate": w.get("rampRate"),
        }

        if date in existing_by_date:
            store["wellness"][existing_by_date[date]] = record
        else:
            store["wellness"].append(record)
            existing_by_date[date] = len(store["wellness"]) - 1
            new_count += 1

    store["wellness"].sort(key=lambda w: w.get("date", ""))

    if verbose:
        print(f"Synced {new_count} new wellness records ({len(store['wellness'])} total).")

    return new_count
