"""Append-only JSON activity store with Intervals.icu sync.

Stores activities and wellness data at running_data/activity_log.json.
Each sync pulls new data and appends it, deduplicating by activity ID.
Supports --resync to re-download and update existing records.
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


def _normalize_streams(raw_streams: list | dict | None) -> dict | None:
    """Normalize Intervals.icu streams into {type: [values]} dict.

    The API returns a list of dicts like:
      [{"type": "heartrate", "data": [140, 141, ...], ...}, ...]
    We flatten to: {"heartrate": [140, 141, ...], "latlng": [[lat,lng], ...]}
    """
    if raw_streams is None:
        return None
    # Already a flat dict (shouldn't happen, but handle it)
    if isinstance(raw_streams, dict):
        return raw_streams
    if not isinstance(raw_streams, list):
        return None

    result = {}
    for stream in raw_streams:
        if not isinstance(stream, dict):
            continue
        stype = stream.get("type") or stream.get("name")
        if not stype:
            continue
        data = stream.get("data")
        if data is None:
            continue
        # latlng has data (lat) and data2 (lng) — combine into pairs
        data2 = stream.get("data2")
        if data2 is not None and stype == "latlng":
            result[stype] = list(zip(data, data2))
        else:
            result[stype] = data
    return result if result else None


def _build_activity_record(activity: dict, streams: list | dict | None) -> dict:
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
        "avg_cadence": _normalize_cadence(activity.get("average_cadence")),
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

    # --- Intervals.icu computed metrics ---
    record["icu_training_load"] = activity.get("icu_training_load")
    record["icu_ctl"] = activity.get("icu_ctl")
    record["icu_atl"] = activity.get("icu_atl")
    record["icu_ramp_rate"] = activity.get("icu_ramp_rate")
    record["icu_efficiency_factor"] = activity.get("icu_efficiency_factor")
    record["icu_hrrc"] = activity.get("icu_hrrc")
    record["decoupling"] = activity.get("decoupling")

    # --- HR/Pace zone data from API (replaces broken label parsing) ---
    record["icu_hr_zone_times"] = activity.get("icu_hr_zone_times")
    record["icu_hr_zones"] = activity.get("icu_hr_zones")
    record["pace_zone_times"] = activity.get("pace_zone_times")
    record["pace_zone_boundaries"] = activity.get("pace_zones")

    # --- Environment ---
    record["average_temp"] = activity.get("average_temp")

    # --- Grade-adjusted pace ---
    gap_ms = activity.get("gap")
    if gap_ms and gap_ms > 0:
        record["gap_sec_km"] = round(1000.0 / gap_ms, 1)
    else:
        record["gap_sec_km"] = None

    # --- Training load breakdown ---
    record["trimp"] = activity.get("trimp")
    record["hr_load"] = activity.get("hr_load")
    record["pace_load"] = activity.get("pace_load")
    record["icu_intensity"] = activity.get("icu_intensity")

    # --- Athlete settings at activity time ---
    record["lthr"] = activity.get("lthr")
    record["icu_resting_hr"] = activity.get("icu_resting_hr")
    record["icu_weight"] = activity.get("icu_weight")
    record["athlete_max_hr"] = activity.get("athlete_max_hr")
    tp = activity.get("threshold_pace")
    if tp and tp > 0:
        record["threshold_pace_sec_km"] = round(1000.0 / tp, 1)
    else:
        record["threshold_pace_sec_km"] = None

    # --- Biomechanics ---
    record["average_stride"] = activity.get("average_stride")
    record["average_speed"] = activity.get("average_speed")
    record["max_speed"] = activity.get("max_speed")

    # --- Elevation detail ---
    record["total_elevation_loss"] = activity.get("total_elevation_loss")
    record["min_altitude"] = activity.get("min_altitude")
    record["max_altitude"] = activity.get("max_altitude")

    # --- Device ---
    record["device_name"] = activity.get("device_name")

    # --- VDOT estimate (from local computation) ---
    if dist >= 1500 and moving > 0:
        record["estimated_vdot"] = _estimate_vdot(moving, dist)
    else:
        record["estimated_vdot"] = None

    # --- Pace zones (backward compat: E/M/T/I/R percentages from API zone times) ---
    record["pace_zones"] = _pace_zone_percentages(
        activity.get("pace_zone_times")
    )

    # --- Per-km splits from Intervals.icu laps ---
    laps = activity.get("laps") or activity.get("icu_laps") or []
    record["km_splits"] = _extract_km_splits(laps)

    # --- Interval summaries ---
    record["intervals"] = _extract_intervals(
        activity.get("icu_intervals", [])
    )

    # --- Efficiency factor: pace / HR ---
    if record["avg_pace_sec_km"] and record["avg_hr"]:
        record["efficiency_factor"] = round(
            record["avg_pace_sec_km"] / record["avg_hr"], 3
        )
    else:
        record["efficiency_factor"] = None

    # --- Per-second streams ---
    record["streams"] = _normalize_streams(streams)

    return record


def _normalize_cadence(cadence):
    """Normalize cadence to steps per minute (both feet).

    COROS/Intervals.icu reports single-leg cadence (~80 spm).
    Double it if < 120 to get full cadence (~160 spm).
    """
    if cadence is None:
        return None
    return round(cadence * 2) if cadence < 120 else round(cadence)


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


def _pace_zone_percentages(pace_zone_times: list | None) -> dict:
    """Convert API pace_zone_times array to percentage dict.

    Intervals.icu provides 7 zones. We label them Z1-Z7.
    """
    if not pace_zone_times:
        return {}
    total = sum(pace_zone_times)
    if total == 0:
        return {}
    labels = ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"]
    return {
        labels[i]: round(t / total * 100, 1)
        for i, t in enumerate(pace_zone_times)
        if i < len(labels)
    }


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
            "cadence": _normalize_cadence(lap.get("average_cadence")),
            "elevation_gain": lap.get("total_elevation_gain"),
        })
    return splits


def _extract_intervals(icu_intervals: list[dict]) -> list[dict]:
    """Extract simplified interval summaries for the detail view."""
    result = []
    for iv in icu_intervals:
        dist = iv.get("distance") or 0
        moving = iv.get("moving_time") or 0
        if dist > 0 and moving > 0:
            pace = round(moving / (dist / 1000), 1)
        else:
            pace = None
        result.append({
            "type": iv.get("type"),
            "label": iv.get("label"),
            "distance": dist,
            "moving_time": moving,
            "avg_pace_sec_km": pace,
            "avg_hr": iv.get("average_heartrate"),
            "max_hr": iv.get("max_heartrate"),
            "avg_cadence": _normalize_cadence(iv.get("average_cadence")),
            "avg_speed": iv.get("average_speed"),
            "intensity": iv.get("intensity"),
        })
    return result


def sync_activities(
    api_key: str,
    store: dict,
    days_back: int = 30,
    force_update: bool = False,
    verbose: bool = True,
) -> tuple[int, int]:
    """Pull recent activities from Intervals.icu, append or update in store.

    Returns (new_count, updated_count).
    """
    newest = datetime.now().strftime("%Y-%m-%d")
    oldest = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    if verbose:
        action = "Re-syncing" if force_update else "Fetching"
        print(f"{action} activities from {oldest} to {newest}...")

    activities = intervals_api.list_activities(api_key, oldest, newest)
    existing = _existing_ids(store)
    # Build index for in-place updates
    id_to_idx = {a["id"]: i for i, a in enumerate(store["activities"])}
    new_count = 0
    updated_count = 0

    for activity in activities:
        act_id = activity.get("id", "")
        if not act_id:
            continue

        is_existing = act_id in existing
        if is_existing and not force_update:
            continue

        if verbose:
            name = activity.get("name", "unnamed")
            date = activity.get("start_date_local", "")[:10]
            tag = "Updating" if is_existing else "Syncing"
            print(f"  {tag}: {date} — {name}")

        # Fetch full activity detail with intervals
        try:
            full = intervals_api.get_activity(api_key, act_id)
        except Exception as e:
            if verbose:
                print(f"    Warning: could not fetch detail for {act_id}: {e}")
            full = activity

        # Fetch streams
        streams = None
        try:
            streams = intervals_api.get_streams(api_key, act_id)
        except Exception:
            pass

        record = _build_activity_record(full, streams)

        if is_existing:
            store["activities"][id_to_idx[act_id]] = record
            updated_count += 1
        else:
            store["activities"].append(record)
            existing.add(act_id)
            id_to_idx[act_id] = len(store["activities"]) - 1
            new_count += 1

    # Sort by date
    store["activities"].sort(key=lambda a: a.get("date", ""))
    store["last_sync"] = datetime.now().isoformat()

    if verbose:
        parts = []
        if new_count:
            parts.append(f"{new_count} new")
        if updated_count:
            parts.append(f"{updated_count} updated")
        if not parts:
            parts.append("0 new")
        print(f"Synced {', '.join(parts)} ({len(store['activities'])} total).")

    return new_count, updated_count


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
            "avg_sleeping_hr": w.get("avgSleepingHR"),
            "steps": w.get("steps"),
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
