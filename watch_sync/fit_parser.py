"""FIT file parser for COROS/Garmin watch exports.

Requires: pip install fitparse

"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import DataPoint, LapSummary, WorkoutRecord

# Semicircles to degrees conversion factor
_SEMICIRCLES_TO_DEGREES = 180.0 / (2**31)

# FIT sport enum mapping
_SPORT_MAP = {
    0: "generic",
    1: "running",
    2: "cycling",
    11: "walking",
    17: "hiking",
    37: "trail_running",
}


def _to_degrees(semicircles: int | None) -> float | None:
    """Convert FIT semicircles to decimal degrees."""
    if semicircles is None:
        return None
    return semicircles * _SEMICIRCLES_TO_DEGREES


def _get(record, field_name, default=None):
    """Safely get a value from a FIT record."""
    val = record.get_value(field_name)
    return val if val is not None else default


def _speed_to_pace(speed: float | None) -> float | None:
    """Convert speed (m/s) to pace (sec/km)."""
    if speed is None or speed <= 0:
        return None
    return 1000.0 / speed


def parse_fit(filepath: str) -> WorkoutRecord:
    """Parse a FIT file and return a WorkoutRecord.

    Args:
        filepath: Path to a .fit file.

    Returns:
        WorkoutRecord with data points, laps, and summary.
    """
    try:
        from fitparse import FitFile
    except ImportError:
        raise ImportError(
            "fitparse is required for FIT file parsing. "
            "Install it with: pip install fitparse"
        )

    fitfile = FitFile(filepath)
    data_points: list[DataPoint] = []
    laps: list[LapSummary] = []

    # Session-level summary values
    session_data: dict = {}
    sport = "running"

    for record in fitfile.get_messages():
        msg_type = record.name

        if msg_type == "record":
            # Use enhanced fields when available (higher resolution)
            speed = _get(record, "enhanced_speed") or _get(record, "speed")
            altitude = _get(record, "enhanced_altitude") or _get(record, "altitude")

            timestamp = _get(record, "timestamp")
            if timestamp is None:
                continue

            dp = DataPoint(
                timestamp=timestamp,
                latitude=_to_degrees(_get(record, "position_lat")),
                longitude=_to_degrees(_get(record, "position_long")),
                altitude=altitude,
                heart_rate=_get(record, "heart_rate"),
                cadence=_get(record, "cadence"),
                speed=speed,
                pace=_speed_to_pace(speed),
                distance=_get(record, "distance"),
                temperature=_get(record, "temperature"),
                power=_get(record, "power"),
                stride_length=_get(record, "step_length"),
                vertical_oscillation=_get(record, "vertical_oscillation"),
                ground_contact_time=_get(record, "stance_time"),
            )
            data_points.append(dp)

        elif msg_type == "lap":
            start_time = _get(record, "start_time") or _get(record, "timestamp")
            distance = _get(record, "total_distance", 0)
            duration = _get(record, "total_elapsed_time") or _get(
                record, "total_timer_time", 0
            )

            avg_speed = _get(record, "enhanced_avg_speed") or _get(
                record, "avg_speed"
            )
            avg_pace = _speed_to_pace(avg_speed) if avg_speed else 0

            if start_time is not None:
                laps.append(
                    LapSummary(
                        start_time=start_time,
                        distance=distance,
                        duration=duration,
                        avg_pace=avg_pace or 0,
                        avg_heart_rate=_get(record, "avg_heart_rate"),
                        max_heart_rate=_get(record, "max_heart_rate"),
                        avg_cadence=_get(record, "avg_cadence"),
                    )
                )

        elif msg_type == "session":
            session_data = {
                "start_time": _get(record, "start_time")
                or _get(record, "timestamp"),
                "total_distance": _get(record, "total_distance", 0),
                "total_duration": _get(record, "total_elapsed_time")
                or _get(record, "total_timer_time", 0),
                "avg_speed": _get(record, "enhanced_avg_speed")
                or _get(record, "avg_speed"),
                "avg_heart_rate": _get(record, "avg_heart_rate"),
                "max_heart_rate": _get(record, "max_heart_rate"),
                "avg_cadence": _get(record, "avg_cadence"),
                "total_ascent": _get(record, "total_ascent"),
                "total_descent": _get(record, "total_descent"),
                "avg_temperature": _get(record, "avg_temperature"),
                "total_calories": _get(record, "total_calories"),
            }
            sport_num = _get(record, "sport")
            if sport_num is not None:
                sport = _SPORT_MAP.get(sport_num, f"sport_{sport_num}")
            elif isinstance(sport_num, str):
                sport = sport_num

    # Build summary from session data, fall back to computed values
    start_time = session_data.get("start_time")
    if start_time is None and data_points:
        start_time = data_points[0].timestamp
    if start_time is None:
        start_time = datetime.now(timezone.utc)

    total_distance = session_data.get("total_distance", 0)
    total_duration = session_data.get("total_duration", 0)

    # Compute avg pace from session speed or distance/duration
    avg_speed = session_data.get("avg_speed")
    if avg_speed and avg_speed > 0:
        avg_pace = 1000.0 / avg_speed
    elif total_distance > 0 and total_duration > 0:
        avg_pace = total_duration / (total_distance / 1000.0)
    else:
        avg_pace = 0

    return WorkoutRecord(
        source="fit",
        sport=sport,
        start_time=start_time,
        total_distance=total_distance,
        total_duration=total_duration,
        avg_pace=avg_pace,
        avg_heart_rate=session_data.get("avg_heart_rate"),
        max_heart_rate=session_data.get("max_heart_rate"),
        avg_cadence=session_data.get("avg_cadence"),
        total_ascent=session_data.get("total_ascent"),
        total_descent=session_data.get("total_descent"),
        avg_temperature=session_data.get("avg_temperature"),
        calories=session_data.get("total_calories"),
        vo2max_estimate=None,
        data_points=data_points,
        laps=laps,
    )
