"""GPX (GPS Exchange Format) file parser.

Uses stdlib xml.etree.ElementTree — no external dependencies.
Supports Garmin TrackPointExtension for heart rate data.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from datetime import datetime

from .models import DataPoint, LapSummary, WorkoutRecord

_GPX_NS = {"gpx": "http://www.topografix.com/GPX/1/1"}
_GARMIN_TPE_NS = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"

# Earth radius in meters for Haversine
_EARTH_RADIUS_M = 6_371_000


def _text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    return element.text


def _float(element: ET.Element | None) -> float | None:
    t = _text(element)
    if t is None:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _int(element: ET.Element | None) -> int | None:
    t = _text(element)
    if t is None:
        return None
    try:
        return int(float(t))
    except ValueError:
        return None


def _parse_time(time_str: str) -> datetime:
    """Parse ISO 8601 timestamp from GPX."""
    time_str = time_str.rstrip("Z")
    return datetime.fromisoformat(time_str)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute distance in meters between two GPS coordinates."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return _EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def parse_gpx(filepath: str) -> WorkoutRecord:
    """Parse a GPX file and return a WorkoutRecord.

    Extracts GPS positions, elevation, timestamps, and optional HR from
    Garmin TrackPointExtension. Computes pace/speed and cumulative distance
    from consecutive GPS points.

    Args:
        filepath: Path to a .gpx file.

    Returns:
        WorkoutRecord with data points and summary.
    """
    tree = ET.parse(filepath)
    root = tree.getroot()

    # Detect namespace — GPX 1.1 vs 1.0
    ns = _GPX_NS
    if root.find("gpx:trk", ns) is None:
        # Try without namespace (GPX 1.0 or no namespace)
        ns = {}

    raw_points: list[dict] = []

    for trk in root.findall("gpx:trk", ns) or root.findall("trk"):
        for seg in trk.findall("gpx:trkseg", ns) or trk.findall("trkseg"):
            for pt in seg.findall("gpx:trkpt", ns) or seg.findall("trkpt"):
                lat_str = pt.get("lat")
                lon_str = pt.get("lon")
                if lat_str is None or lon_str is None:
                    continue

                lat = float(lat_str)
                lon = float(lon_str)

                time_elem = pt.find("gpx:time", ns) if ns else pt.find("time")
                time_str = _text(time_elem)
                if time_str is None:
                    continue

                timestamp = _parse_time(time_str)
                ele = _float(pt.find("gpx:ele", ns) if ns else pt.find("ele"))

                # HR from Garmin TrackPointExtension
                hr = None
                cad = None
                extensions = pt.find("gpx:extensions", ns) if ns else pt.find(
                    "extensions"
                )
                if extensions is not None:
                    tpe = extensions.find(f"{{{_GARMIN_TPE_NS}}}TrackPointExtension")
                    if tpe is not None:
                        hr = _int(tpe.find(f"{{{_GARMIN_TPE_NS}}}hr"))
                        cad = _int(tpe.find(f"{{{_GARMIN_TPE_NS}}}cad"))

                raw_points.append({
                    "timestamp": timestamp,
                    "lat": lat,
                    "lon": lon,
                    "altitude": ele,
                    "heart_rate": hr,
                    "cadence": cad,
                })

    # Compute cumulative distance, speed, pace from GPS
    data_points: list[DataPoint] = []
    cumulative_dist = 0.0
    total_ascent = 0.0
    total_descent = 0.0

    for i, pt in enumerate(raw_points):
        speed = None
        pace = None

        if i > 0:
            prev = raw_points[i - 1]
            segment_dist = _haversine(prev["lat"], prev["lon"], pt["lat"], pt["lon"])
            dt = (pt["timestamp"] - prev["timestamp"]).total_seconds()
            cumulative_dist += segment_dist

            if dt > 0 and segment_dist > 0:
                speed = segment_dist / dt
                pace = 1000.0 / speed

            # Elevation gain/loss
            if pt["altitude"] is not None and prev["altitude"] is not None:
                diff = pt["altitude"] - prev["altitude"]
                if diff > 0:
                    total_ascent += diff
                else:
                    total_descent += abs(diff)

        data_points.append(
            DataPoint(
                timestamp=pt["timestamp"],
                latitude=pt["lat"],
                longitude=pt["lon"],
                altitude=pt["altitude"],
                heart_rate=pt["heart_rate"],
                cadence=pt["cadence"],
                speed=speed,
                pace=pace,
                distance=cumulative_dist,
            )
        )

    # Summary
    start_time = data_points[0].timestamp if data_points else datetime.now()
    total_distance = cumulative_dist
    total_duration = (
        (data_points[-1].timestamp - data_points[0].timestamp).total_seconds()
        if len(data_points) >= 2
        else 0
    )
    avg_pace = (
        total_duration / (total_distance / 1000.0)
        if total_distance > 0 and total_duration > 0
        else 0
    )

    # Average HR
    hr_vals = [dp.heart_rate for dp in data_points if dp.heart_rate is not None]
    avg_hr = int(sum(hr_vals) / len(hr_vals)) if hr_vals else None
    max_hr = max(hr_vals) if hr_vals else None

    cad_vals = [dp.cadence for dp in data_points if dp.cadence is not None]
    avg_cad = int(sum(cad_vals) / len(cad_vals)) if cad_vals else None

    # Detect sport from GPX type element
    sport = "running"
    type_elem = root.find(".//gpx:trk/gpx:type", _GPX_NS)
    if type_elem is not None and type_elem.text:
        sport = type_elem.text.lower().replace(" ", "_")

    # Build per-km laps
    laps = _compute_km_laps(data_points)

    return WorkoutRecord(
        source="gpx",
        sport=sport,
        start_time=start_time,
        total_distance=total_distance,
        total_duration=total_duration,
        avg_pace=avg_pace,
        avg_heart_rate=avg_hr,
        max_heart_rate=max_hr,
        avg_cadence=avg_cad,
        total_ascent=total_ascent if total_ascent > 0 else None,
        total_descent=total_descent if total_descent > 0 else None,
        data_points=data_points,
        laps=laps,
    )


def _compute_km_laps(data_points: list[DataPoint]) -> list[LapSummary]:
    """Compute per-kilometer lap splits from data points."""
    if not data_points:
        return []

    laps: list[LapSummary] = []
    km_boundary = 1000.0
    lap_start_idx = 0

    for i, dp in enumerate(data_points):
        if dp.distance is not None and dp.distance >= km_boundary:
            lap_start = data_points[lap_start_idx]
            duration = (dp.timestamp - lap_start.timestamp).total_seconds()
            distance = dp.distance - (lap_start.distance or 0)

            hr_vals = [
                p.heart_rate
                for p in data_points[lap_start_idx : i + 1]
                if p.heart_rate is not None
            ]

            cad_vals = [
                p.cadence
                for p in data_points[lap_start_idx : i + 1]
                if p.cadence is not None
            ]

            avg_pace = duration / (distance / 1000.0) if distance > 0 else 0

            laps.append(
                LapSummary(
                    start_time=lap_start.timestamp,
                    distance=distance,
                    duration=duration,
                    avg_pace=avg_pace,
                    avg_heart_rate=(
                        int(sum(hr_vals) / len(hr_vals)) if hr_vals else None
                    ),
                    max_heart_rate=max(hr_vals) if hr_vals else None,
                    avg_cadence=(
                        int(sum(cad_vals) / len(cad_vals)) if cad_vals else None
                    ),
                )
            )
            km_boundary += 1000.0
            lap_start_idx = i

    return laps
