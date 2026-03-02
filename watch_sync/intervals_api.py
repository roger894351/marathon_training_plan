"""Intervals.icu REST API client.

Provides functions to fetch activities, per-second streams, and wellness
data from the Intervals.icu API using HTTP Basic auth.
"""

from __future__ import annotations

import os

import requests

BASE_URL = "https://intervals.icu/api/v1"
ATHLETE_ID = "0"  # "0" = authenticated user (self)


def load_api_key(env_path: str = "running_data/.env") -> str:
    """Read INTERVALS_API_KEY from a .env file (simple KEY=value format)."""
    path = os.path.expanduser(env_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"No .env file at {path}. Copy .env.example to {path} and add your key."
        )
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("INTERVALS_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise ValueError(f"INTERVALS_API_KEY not found in {path}")


def _session(api_key: str) -> requests.Session:
    """Create a requests Session with Basic auth (user=API_KEY, password=api_key)."""
    s = requests.Session()
    s.auth = ("API_KEY", api_key)
    s.headers["Accept"] = "application/json"
    return s


def list_activities(api_key: str, oldest: str, newest: str) -> list[dict]:
    """List activities between oldest and newest (YYYY-MM-DD inclusive).

    Returns a list of activity summary dicts from Intervals.icu.
    """
    url = f"{BASE_URL}/athlete/{ATHLETE_ID}/activities"
    params = {"oldest": oldest, "newest": newest}
    resp = _session(api_key).get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_activity(api_key: str, activity_id: str) -> dict:
    """Get full activity detail including intervals.

    Returns the activity dict with computed metrics.
    """
    url = f"{BASE_URL}/activity/{activity_id}"
    params = {"intervals": "true"}
    resp = _session(api_key).get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_streams(
    api_key: str,
    activity_id: str,
    types: str = "heartrate,cadence,latlng,altitude,distance,time",
) -> dict:
    """Get per-second stream data for an activity.

    Returns a dict keyed by stream type, each value is a list of numbers.
    """
    url = f"{BASE_URL}/activity/{activity_id}/streams.json"
    params = {"types": types}
    resp = _session(api_key).get(url, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def get_wellness(api_key: str, oldest: str, newest: str) -> list[dict]:
    """Get wellness records (resting HR, HRV, sleep, weight, CTL/ATL).

    Returns a list of wellness dicts, one per day.
    """
    url = f"{BASE_URL}/athlete/{ATHLETE_ID}/wellness"
    params = {"oldest": oldest, "newest": newest}
    resp = _session(api_key).get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()
