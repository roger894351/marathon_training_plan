"""CLI entry point for watch_sync — parse exports, sync from Intervals.icu, dashboard.

Usage:
    python3 -m watch_sync parse activity.fit
    python3 -m watch_sync parse exports/ --format fit
    python3 -m watch_sync sync --days 30
    python3 -m watch_sync dashboard --open

Backward-compat: if first arg is a file/dir, treat as 'parse'.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from .models import WorkoutRecord

# Format detection by extension
_EXT_FORMAT = {
    ".fit": "fit",
    ".tcx": "tcx",
    ".gpx": "gpx",
}


def _detect_format(filepath: str) -> str:
    """Detect file format from extension."""
    ext = Path(filepath).suffix.lower()
    fmt = _EXT_FORMAT.get(ext)
    if fmt is None:
        raise ValueError(
            f"Cannot detect format for '{filepath}'. "
            f"Supported extensions: {', '.join(_EXT_FORMAT.keys())}"
        )
    return fmt


def _parse_file(filepath: str, fmt: str | None = None) -> WorkoutRecord:
    """Parse a single activity file."""
    if fmt is None:
        fmt = _detect_format(filepath)

    if fmt == "fit":
        from .fit_parser import parse_fit
        return parse_fit(filepath)
    elif fmt == "tcx":
        from .tcx_parser import parse_tcx
        return parse_tcx(filepath)
    elif fmt == "gpx":
        from .gpx_parser import parse_gpx
        return parse_gpx(filepath)
    else:
        raise ValueError(f"Unsupported format: {fmt}")


def _collect_files(path: str, fmt: str | None) -> list[str]:
    """Collect activity files from a path (file or directory)."""
    if os.path.isfile(path):
        return [path]

    if not os.path.isdir(path):
        raise FileNotFoundError(f"Path not found: {path}")

    files = []
    valid_exts = (
        {f".{fmt}"} if fmt else set(_EXT_FORMAT.keys())
    )
    for entry in sorted(os.listdir(path)):
        if Path(entry).suffix.lower() in valid_exts:
            files.append(os.path.join(path, entry))

    if not files:
        raise FileNotFoundError(
            f"No activity files found in '{path}' "
            f"(looking for: {', '.join(valid_exts)})"
        )
    return files


# ---------------------------------------------------------------------------
# Computed metrics
# ---------------------------------------------------------------------------

def _vdot_from_time_distance(time_seconds: float, distance_m: float) -> float | None:
    """Estimate VDOT from a workout's time and distance.

    Uses the same Daniels' formula as plan_generator.py.
    Only meaningful for race-effort runs >= 1500m.
    """
    import math

    if distance_m < 1500 or time_seconds <= 0:
        return None

    t = time_seconds / 60.0  # minutes
    v = distance_m / t  # m/min

    # VO2 from velocity
    vo2 = -4.60 + 0.182258 * v + 0.000104 * v * v

    # %VO2max from duration
    pct = (
        0.8
        + 0.1894393 * math.exp(-0.012778 * t)
        + 0.2989558 * math.exp(-0.1932605 * t)
    )

    if pct <= 0:
        return None

    return vo2 / pct


def _pace_zone_for_pace(pace_sec_km: float, vdot: float) -> str:
    """Classify a pace into E/M/T/I/R zone given a VDOT."""
    import math

    def pace_at_frac(frac: float) -> float:
        vo2 = vdot * frac
        a = 0.000104
        b = 0.182258
        c = -(4.60 + vo2)
        disc = b * b - 4 * a * c
        v = (-b + math.sqrt(disc)) / (2 * a)  # m/min
        return 1000.0 / v * 60.0  # sec/km

    # Zone boundaries (pace: lower number = faster)
    r_fast = pace_at_frac(1.10)
    i_fast = pace_at_frac(1.00)
    t_fast = pace_at_frac(0.88)
    m_fast = pace_at_frac(0.84)

    if pace_sec_km <= r_fast:
        return "R"
    elif pace_sec_km <= i_fast:
        return "I"
    elif pace_sec_km <= t_fast:
        return "T"
    elif pace_sec_km <= m_fast:
        return "M"
    else:
        return "E"


def _compute_pace_zones(record: WorkoutRecord) -> dict[str, float]:
    """Compute time-in-zone percentages for a workout."""
    vdot = _vdot_from_time_distance(record.total_duration, record.total_distance)
    if vdot is None or not record.data_points:
        return {}

    zone_time: dict[str, float] = {"E": 0, "M": 0, "T": 0, "I": 0, "R": 0}
    total_time = 0.0

    for i in range(1, len(record.data_points)):
        dp = record.data_points[i]
        prev = record.data_points[i - 1]
        if dp.pace is None or dp.pace <= 0:
            continue

        dt = (dp.timestamp - prev.timestamp).total_seconds()
        if dt <= 0 or dt > 30:  # skip gaps > 30s
            continue

        zone = _pace_zone_for_pace(dp.pace, vdot)
        zone_time[zone] += dt
        total_time += dt

    if total_time == 0:
        return {}

    return {z: round(t / total_time * 100, 1) for z, t in zone_time.items()}


def _compute_km_splits(record: WorkoutRecord) -> list[dict]:
    """Compute per-km split paces from laps or data points."""
    splits = []
    for i, lap in enumerate(record.laps, 1):
        splits.append({
            "km": i,
            "pace": _format_pace(lap.avg_pace),
            "pace_sec_km": round(lap.avg_pace, 1),
            "heart_rate": lap.avg_heart_rate,
        })
    return splits


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_pace(sec_per_km: float) -> str:
    """Format seconds/km as M:SS/km."""
    if sec_per_km <= 0:
        return "—"
    m = int(sec_per_km) // 60
    s = int(sec_per_km) % 60
    return f"{m}:{s:02d}/km"


def _format_duration(seconds: float) -> str:
    """Format duration as H:MM:SS or M:SS."""
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _record_to_summary_dict(record: WorkoutRecord) -> dict:
    """Convert a WorkoutRecord to a summary dictionary for JSON output."""
    vdot = _vdot_from_time_distance(record.total_duration, record.total_distance)
    pace_zones = _compute_pace_zones(record)
    splits = _compute_km_splits(record)

    summary = {
        "source": record.source,
        "sport": record.sport,
        "start_time": record.start_time.isoformat(),
        "total_distance_km": round(record.total_distance / 1000, 2),
        "total_duration": _format_duration(record.total_duration),
        "avg_pace": _format_pace(record.avg_pace),
        "avg_heart_rate": record.avg_heart_rate,
        "max_heart_rate": record.max_heart_rate,
        "avg_cadence": record.avg_cadence,
    }

    if record.total_ascent is not None:
        summary["total_ascent_m"] = round(record.total_ascent, 1)
    if record.total_descent is not None:
        summary["total_descent_m"] = round(record.total_descent, 1)
    if record.avg_temperature is not None:
        summary["avg_temperature_c"] = record.avg_temperature
    if record.calories is not None:
        summary["calories"] = record.calories

    if splits:
        summary["laps"] = splits

    computed = {}
    if vdot is not None:
        computed["estimated_vdot"] = round(vdot, 1)
    if pace_zones:
        computed["pace_zones_hit"] = pace_zones
    if computed:
        summary["computed"] = computed

    return summary


def _print_summary(record: WorkoutRecord) -> None:
    """Print a human-readable summary to stdout."""
    d = record
    print(f"Source:     {d.source.upper()}")
    print(f"Sport:      {d.sport}")
    print(f"Date:       {d.start_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"Distance:   {d.total_distance / 1000:.2f} km")
    print(f"Duration:   {_format_duration(d.total_duration)}")
    print(f"Avg Pace:   {_format_pace(d.avg_pace)}")

    if d.avg_heart_rate:
        print(f"Avg HR:     {d.avg_heart_rate} bpm")
    if d.max_heart_rate:
        print(f"Max HR:     {d.max_heart_rate} bpm")
    if d.avg_cadence:
        print(f"Avg Cadence:{d.avg_cadence} spm")
    if d.total_ascent is not None:
        print(f"Ascent:     {d.total_ascent:.0f} m")
    if d.calories is not None:
        print(f"Calories:   {d.calories}")

    # Data point count
    print(f"Data Points:{len(d.data_points)}")
    print(f"Laps:       {len(d.laps)}")

    # Computed metrics
    vdot = _vdot_from_time_distance(d.total_duration, d.total_distance)
    if vdot is not None:
        print(f"\nEstimated VDOT: {vdot:.1f}")

    zones = _compute_pace_zones(record)
    if zones:
        print("Pace Zones: ", end="")
        print("  ".join(f"{z}:{pct:.0f}%" for z, pct in zones.items()))

    if d.laps:
        print(f"\nSplits:")
        for i, lap in enumerate(d.laps, 1):
            hr_str = f"  HR:{lap.avg_heart_rate}" if lap.avg_heart_rate else ""
            print(f"  km {i:2d}: {_format_pace(lap.avg_pace)}{hr_str}")


def _write_json(records: list[WorkoutRecord], output_path: str) -> None:
    """Write workout summaries as JSON."""
    if len(records) == 1:
        data = _record_to_summary_dict(records[0])
    else:
        data = [_record_to_summary_dict(r) for r in records]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Written: {output_path}")


def _write_csv(records: list[WorkoutRecord], output_path: str, detail: bool) -> None:
    """Write workout data as CSV."""
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        if detail:
            # Per-data-point CSV
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "distance_km", "pace_sec_km", "heart_rate",
                "cadence", "altitude", "temperature", "power",
                "latitude", "longitude",
            ])
            for record in records:
                for dp in record.data_points:
                    writer.writerow([
                        dp.timestamp.isoformat(),
                        f"{dp.distance / 1000:.3f}" if dp.distance else "",
                        f"{dp.pace:.0f}" if dp.pace else "",
                        dp.heart_rate or "",
                        dp.cadence or "",
                        f"{dp.altitude:.1f}" if dp.altitude is not None else "",
                        dp.temperature or "",
                        dp.power or "",
                        f"{dp.latitude:.6f}" if dp.latitude is not None else "",
                        f"{dp.longitude:.6f}" if dp.longitude is not None else "",
                    ])
        else:
            # Summary CSV (one row per workout)
            writer = csv.writer(f)
            writer.writerow([
                "source", "sport", "start_time", "distance_km", "duration",
                "avg_pace", "avg_hr", "max_hr", "avg_cadence",
                "ascent_m", "calories", "estimated_vdot",
            ])
            for record in records:
                vdot = _vdot_from_time_distance(
                    record.total_duration, record.total_distance
                )
                writer.writerow([
                    record.source,
                    record.sport,
                    record.start_time.isoformat(),
                    f"{record.total_distance / 1000:.2f}",
                    _format_duration(record.total_duration),
                    _format_pace(record.avg_pace),
                    record.avg_heart_rate or "",
                    record.max_heart_rate or "",
                    record.avg_cadence or "",
                    f"{record.total_ascent:.0f}" if record.total_ascent else "",
                    record.calories or "",
                    f"{vdot:.1f}" if vdot else "",
                ])

    print(f"Written: {output_path}")


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def _cmd_parse(args: argparse.Namespace) -> None:
    """Handle the 'parse' subcommand."""
    files = _collect_files(args.path, args.format)
    records: list[WorkoutRecord] = []

    for filepath in files:
        try:
            record = _parse_file(filepath, args.format)
            records.append(record)
            if not args.output:
                if len(files) > 1:
                    print(f"\n{'='*60}")
                    print(f"File: {filepath}")
                    print(f"{'='*60}")
                _print_summary(record)
        except Exception as e:
            print(f"Error parsing {filepath}: {e}", file=sys.stderr)

    if not records:
        print("No activities parsed.", file=sys.stderr)
        sys.exit(1)

    if args.output:
        ext = Path(args.output).suffix.lower()
        if ext == ".json":
            _write_json(records, args.output)
        elif ext == ".csv":
            _write_csv(records, args.output, args.detail)
        else:
            print(
                f"Unsupported output format '{ext}'. Use .json or .csv.",
                file=sys.stderr,
            )
            sys.exit(1)


def _cmd_sync(args: argparse.Namespace) -> None:
    """Handle the 'sync' subcommand."""
    from .activity_store import load_store, save_store, sync_activities, sync_wellness
    from .intervals_api import load_api_key

    env_path = args.env or "running_data/.env"
    store_path = args.store or "running_data/activity_log.json"

    api_key = load_api_key(env_path)
    store = load_store(store_path)

    sync_activities(api_key, store, days_back=args.days)
    sync_wellness(api_key, store, days_back=args.days)
    save_store(store, store_path)

    if args.open:
        from .dashboard import generate_dashboard, open_dashboard
        output = generate_dashboard(store_path)
        print(f"Dashboard: {output}")
        open_dashboard(output)


def _cmd_dashboard(args: argparse.Namespace) -> None:
    """Handle the 'dashboard' subcommand."""
    from .dashboard import generate_dashboard, open_dashboard

    store_path = args.store or "running_data/activity_log.json"
    output_path = args.output or "running_data/dashboard.html"

    output = generate_dashboard(store_path, output_path)
    print(f"Dashboard generated: {output}")

    if args.open:
        open_dashboard(output)


def main(argv: list[str] | None = None) -> None:
    """Main CLI entry point with subcommands."""
    # Backward-compat: if first arg looks like a file/dir path, treat as 'parse'
    raw_args = argv if argv is not None else sys.argv[1:]
    if raw_args and not raw_args[0].startswith("-"):
        first = raw_args[0]
        if first not in ("parse", "sync", "dashboard") and (
            os.path.exists(first) or "." in first
        ):
            raw_args = ["parse"] + raw_args

    parser = argparse.ArgumentParser(
        prog="watch_sync",
        description="Parse running watch exports, sync from Intervals.icu, and visualize.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- parse subcommand ---
    parse_parser = subparsers.add_parser(
        "parse", help="Parse FIT/TCX/GPX activity files"
    )
    parse_parser.add_argument(
        "path", help="Activity file or directory of exports"
    )
    parse_parser.add_argument(
        "--format", choices=["fit", "tcx", "gpx"], default=None,
        help="Force file format (default: auto-detect)",
    )
    parse_parser.add_argument(
        "-o", "--output", default=None,
        help="Output file path (.json or .csv)",
    )
    parse_parser.add_argument(
        "--detail", action="store_true",
        help="Include per-second data points in CSV output",
    )

    # --- sync subcommand ---
    sync_parser = subparsers.add_parser(
        "sync", help="Sync activities from Intervals.icu"
    )
    sync_parser.add_argument(
        "--days", type=int, default=7,
        help="Number of days to look back (default: 7)",
    )
    sync_parser.add_argument(
        "--env", default=None,
        help="Path to .env file (default: running_data/.env)",
    )
    sync_parser.add_argument(
        "--store", default=None,
        help="Path to activity store JSON (default: running_data/activity_log.json)",
    )
    sync_parser.add_argument(
        "--open", action="store_true",
        help="Generate and open dashboard after sync",
    )

    # --- dashboard subcommand ---
    dash_parser = subparsers.add_parser(
        "dashboard", help="Generate HTML dashboard from synced data"
    )
    dash_parser.add_argument(
        "--store", default=None,
        help="Path to activity store JSON (default: running_data/activity_log.json)",
    )
    dash_parser.add_argument(
        "-o", "--output", default=None,
        help="Output HTML path (default: running_data/dashboard.html)",
    )
    dash_parser.add_argument(
        "--open", action="store_true",
        help="Open dashboard in browser after generating",
    )

    args = parser.parse_args(raw_args)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "parse":
        _cmd_parse(args)
    elif args.command == "sync":
        _cmd_sync(args)
    elif args.command == "dashboard":
        _cmd_dashboard(args)
