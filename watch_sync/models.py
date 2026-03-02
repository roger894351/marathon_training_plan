"""Unified data model for watch activity data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DataPoint:
    """A single timestamped measurement from a running watch."""

    timestamp: datetime
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None          # meters
    heart_rate: int | None = None          # bpm
    cadence: int | None = None             # steps/min
    pace: float | None = None              # sec/km
    speed: float | None = None             # m/s
    distance: float | None = None          # cumulative meters
    temperature: float | None = None       # celsius
    power: int | None = None               # watts
    stride_length: float | None = None     # meters
    vertical_oscillation: float | None = None  # mm
    ground_contact_time: int | None = None     # ms


@dataclass
class LapSummary:
    """Summary metrics for a single lap/split."""

    start_time: datetime
    distance: float              # meters
    duration: float              # seconds
    avg_pace: float              # sec/km
    avg_heart_rate: int | None = None
    max_heart_rate: int | None = None
    avg_cadence: int | None = None


@dataclass
class WorkoutRecord:
    """Complete record of a single workout/activity."""

    source: str                  # "fit", "tcx", "gpx"
    sport: str                   # "running", "trail_running", etc.
    start_time: datetime
    total_distance: float        # meters
    total_duration: float        # seconds
    avg_pace: float              # sec/km
    avg_heart_rate: int | None = None
    max_heart_rate: int | None = None
    avg_cadence: int | None = None
    total_ascent: float | None = None    # meters
    total_descent: float | None = None   # meters
    avg_temperature: float | None = None
    calories: int | None = None
    vo2max_estimate: float | None = None  # from device
    data_points: list[DataPoint] = field(default_factory=list)
    laps: list[LapSummary] = field(default_factory=list)
