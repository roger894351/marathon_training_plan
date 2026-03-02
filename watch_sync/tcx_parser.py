"""TCX (Training Center XML) file parser.

Uses stdlib xml.etree.ElementTree — no external dependencies.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime

from .models import DataPoint, LapSummary, WorkoutRecord

_NS = {"tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}


def _text(element: ET.Element | None) -> str | None:
    """Get text content of an element, or None."""
    if element is None:
        return None
    return element.text


def _float(element: ET.Element | None) -> float | None:
    """Get float value from element text, or None."""
    t = _text(element)
    if t is None:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _int(element: ET.Element | None) -> int | None:
    """Get int value from element text, or None."""
    t = _text(element)
    if t is None:
        return None
    try:
        return int(float(t))
    except ValueError:
        return None


def _parse_time(time_str: str) -> datetime:
    """Parse ISO 8601 timestamp from TCX."""
    # Handle both with and without trailing Z / timezone
    time_str = time_str.rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.fromisoformat(time_str)
        except ValueError:
            continue
    return datetime.fromisoformat(time_str)


def _speed_to_pace(speed: float | None) -> float | None:
    """Convert speed (m/s) to pace (sec/km)."""
    if speed is None or speed <= 0:
        return None
    return 1000.0 / speed


def parse_tcx(filepath: str) -> WorkoutRecord:
    """Parse a TCX file and return a WorkoutRecord.

    Args:
        filepath: Path to a .tcx file.

    Returns:
        WorkoutRecord with data points, laps, and summary.
    """
    tree = ET.parse(filepath)
    root = tree.getroot()

    activity = root.find(".//tcx:Activity", _NS)
    if activity is None:
        raise ValueError(f"No Activity found in TCX file: {filepath}")

    # Sport attribute
    sport_raw = activity.get("Sport", "Running")
    sport = sport_raw.lower().replace(" ", "_")

    data_points: list[DataPoint] = []
    laps: list[LapSummary] = []

    total_distance = 0.0
    total_duration = 0.0
    hr_sum = 0
    hr_count = 0
    hr_max = 0
    cadence_sum = 0
    cadence_count = 0
    calories_total = 0

    for lap_elem in activity.findall("tcx:Lap", _NS):
        # Lap start time from attribute
        lap_start_str = lap_elem.get("StartTime", "")
        lap_start = _parse_time(lap_start_str) if lap_start_str else None

        lap_duration = _float(lap_elem.find("tcx:TotalTimeSeconds", _NS)) or 0
        lap_distance = _float(lap_elem.find("tcx:DistanceMeters", _NS)) or 0
        lap_calories = _int(lap_elem.find("tcx:Calories", _NS)) or 0
        lap_avg_hr = _int(
            lap_elem.find("tcx:AverageHeartRateBpm/tcx:Value", _NS)
        )
        lap_max_hr = _int(
            lap_elem.find("tcx:MaximumHeartRateBpm/tcx:Value", _NS)
        )
        lap_cadence = _int(lap_elem.find("tcx:Cadence", _NS))

        total_distance += lap_distance
        total_duration += lap_duration
        calories_total += lap_calories

        if lap_avg_hr is not None:
            hr_sum += lap_avg_hr
            hr_count += 1
        if lap_max_hr is not None:
            hr_max = max(hr_max, lap_max_hr)
        if lap_cadence is not None:
            cadence_sum += lap_cadence
            cadence_count += 1

        # Compute lap avg pace
        lap_avg_pace = 0.0
        if lap_distance > 0 and lap_duration > 0:
            lap_avg_pace = lap_duration / (lap_distance / 1000.0)

        if lap_start is not None:
            laps.append(
                LapSummary(
                    start_time=lap_start,
                    distance=lap_distance,
                    duration=lap_duration,
                    avg_pace=lap_avg_pace,
                    avg_heart_rate=lap_avg_hr,
                    max_heart_rate=lap_max_hr,
                    avg_cadence=lap_cadence,
                )
            )

        # Parse trackpoints
        for tp in lap_elem.findall(".//tcx:Trackpoint", _NS):
            time_str = _text(tp.find("tcx:Time", _NS))
            if time_str is None:
                continue

            timestamp = _parse_time(time_str)
            lat = _float(tp.find("tcx:Position/tcx:LatitudeDegrees", _NS))
            lon = _float(tp.find("tcx:Position/tcx:LongitudeDegrees", _NS))
            alt = _float(tp.find("tcx:AltitudeMeters", _NS))
            hr = _int(tp.find("tcx:HeartRateBpm/tcx:Value", _NS))
            cad = _int(tp.find("tcx:Cadence", _NS))
            dist = _float(tp.find("tcx:DistanceMeters", _NS))

            # Speed from extensions if available
            speed = None
            extensions = tp.find("tcx:Extensions", _NS)
            if extensions is not None:
                # Try Garmin Activity Extension
                for child in extensions:
                    speed_elem = child.find(
                        "{http://www.garmin.com/xmlschemas/ActivityExtension/v2}Speed"
                    )
                    if speed_elem is not None:
                        speed = _float(speed_elem)
                        break

            dp = DataPoint(
                timestamp=timestamp,
                latitude=lat,
                longitude=lon,
                altitude=alt,
                heart_rate=hr,
                cadence=cad,
                speed=speed,
                pace=_speed_to_pace(speed),
                distance=dist,
            )
            data_points.append(dp)

    # Compute speed/pace between consecutive points where speed is missing
    for i in range(1, len(data_points)):
        if data_points[i].speed is not None:
            continue
        prev = data_points[i - 1]
        curr = data_points[i]
        if prev.distance is not None and curr.distance is not None:
            dt = (curr.timestamp - prev.timestamp).total_seconds()
            dd = curr.distance - prev.distance
            if dt > 0 and dd > 0:
                speed = dd / dt
                curr.speed = speed
                curr.pace = _speed_to_pace(speed)

    # Summary
    start_time_str = _text(activity.find("tcx:Id", _NS))
    start_time = _parse_time(start_time_str) if start_time_str else (
        data_points[0].timestamp if data_points else datetime.now()
    )

    avg_pace = 0.0
    if total_distance > 0 and total_duration > 0:
        avg_pace = total_duration / (total_distance / 1000.0)

    return WorkoutRecord(
        source="tcx",
        sport=sport,
        start_time=start_time,
        total_distance=total_distance,
        total_duration=total_duration,
        avg_pace=avg_pace,
        avg_heart_rate=int(hr_sum / hr_count) if hr_count else None,
        max_heart_rate=hr_max if hr_max > 0 else None,
        avg_cadence=int(cadence_sum / cadence_count) if cadence_count else None,
        calories=calories_total if calories_total > 0 else None,
        data_points=data_points,
        laps=laps,
    )
