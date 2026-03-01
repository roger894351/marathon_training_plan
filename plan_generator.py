#!/usr/bin/env python3
"""
Marathon Training Plan Generator (Daniels' Running Formula)

Generates a periodized marathon training plan based on VDOT pace zones.
Outputs CSV compatible with generate_calendar.py for ICS calendar generation.

Usage:
    python plan_generator.py --race-date 2026-12-20 --goal-time 3:00:00 --race-name "台北馬拉松"
    python plan_generator.py --race-date 2026-12-20 --goal-time 3:30:00 --lang en -o plan.csv
"""

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from translations import translate

# ---------------------------------------------------------------------------
# VDOT / Pace Zone Calculation (Daniels' Running Formula)
# ---------------------------------------------------------------------------

def _vo2_from_velocity(v: float) -> float:
    """Oxygen cost (ml/kg/min) at velocity v (m/min)."""
    return -4.60 + 0.182258 * v + 0.000104 * v * v


def _pct_vo2max_from_time(t: float) -> float:
    """%VO2max sustainable for duration t (minutes)."""
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t) + 0.2989558 * math.exp(-0.1932605 * t)


def vdot_from_marathon_time(seconds: int) -> float:
    """Calculate VDOT from marathon finish time in seconds."""
    t = seconds / 60.0  # minutes
    v = 42195.0 / t  # m/min
    vo2 = _vo2_from_velocity(v)
    pct = _pct_vo2max_from_time(t)
    return vo2 / pct


def _velocity_from_vo2(vo2: float) -> float:
    """Invert VO2 equation to get velocity (m/min) from VO2 (ml/kg/min)."""
    # Solve: 0.000104*v^2 + 0.182258*v - (4.60 + vo2) = 0
    a = 0.000104
    b = 0.182258
    c = -(4.60 + vo2)
    discriminant = b * b - 4 * a * c
    return (-b + math.sqrt(discriminant)) / (2 * a)


def _pace_from_vdot_fraction(vdot: float, fraction: float) -> float:
    """Get pace (seconds/km) for a given fraction of VDOT."""
    vo2 = vdot * fraction
    v = _velocity_from_vo2(vo2)  # m/min
    return 1000.0 / v * 60.0  # sec/km


@dataclass
class PaceZones:
    """Pace zones in seconds per km (low = fast end, high = slow end)."""
    e_low: float
    e_high: float
    m_low: float
    m_high: float
    t_low: float
    t_high: float
    i_low: float
    i_high: float
    r_low: float
    r_high: float


def pace_zones_from_vdot(vdot: float) -> PaceZones:
    """Derive all 5 pace zones from VDOT value."""
    return PaceZones(
        e_low=_pace_from_vdot_fraction(vdot, 0.74),
        e_high=_pace_from_vdot_fraction(vdot, 0.59),
        m_low=_pace_from_vdot_fraction(vdot, 0.84),
        m_high=_pace_from_vdot_fraction(vdot, 0.79),
        t_low=_pace_from_vdot_fraction(vdot, 0.88),
        t_high=_pace_from_vdot_fraction(vdot, 0.83),
        i_low=_pace_from_vdot_fraction(vdot, 1.00),
        i_high=_pace_from_vdot_fraction(vdot, 0.95),
        r_low=_pace_from_vdot_fraction(vdot, 1.10),
        r_high=_pace_from_vdot_fraction(vdot, 1.05),
    )


def format_pace(sec_per_km: float) -> str:
    """Format seconds/km as M:SS string."""
    m = int(sec_per_km) // 60
    s = int(sec_per_km) % 60
    return f"{m}:{s:02d}"


def format_pace_range(low: float, high: float) -> str:
    """Format a pace range as 'M:SS~M:SS/km'."""
    return f"{format_pace(low)}~{format_pace(high)}/km"


def equivalent_race_time(vdot: float, distance_m: float) -> int:
    """Estimate race time (seconds) for a given distance at a VDOT level.

    Uses iterative approach: find time t where VDOT(distance, t) = vdot.
    """
    # Initial estimate from I-pace velocity
    v_est = _velocity_from_vo2(vdot * 0.90)
    t_est = distance_m / v_est  # minutes

    # Newton-like iteration
    for _ in range(50):
        v = distance_m / t_est
        vo2 = _vo2_from_velocity(v)
        pct = _pct_vo2max_from_time(t_est)
        computed_vdot = vo2 / pct
        if abs(computed_vdot - vdot) < 0.01:
            break
        # Adjust: if computed_vdot > target, we're too fast, increase time
        t_est *= (computed_vdot / vdot) ** 0.5

    return int(t_est * 60)


def format_race_time(seconds: int) -> str:
    """Format race time as MM:SS or H:MM:SS."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# Periodization Engine
# ---------------------------------------------------------------------------

@dataclass
class PhaseInfo:
    key: str
    name_zh: str
    subtitle_zh: str
    ideal_weeks: int
    min_weeks: int


PHASES = [
    PhaseInfo("base1", "基礎期1", "坡道與有氧", 4, 2),
    PhaseInfo("base2", "基礎期2", "速度開發", 8, 3),
    PhaseInfo("development", "開發期", "心肺刺激", 8, 3),
    PhaseInfo("threshold1", "閾值期1", "乳酸門檻", 5, 2),
    PhaseInfo("threshold2", "閾值期2", "耐力強化", 5, 2),
    PhaseInfo("peak1", "高峰期1", "M配速整合", 4, 2),
    PhaseInfo("summit", "巔峰期", "全馬專項", 4, 2),
    PhaseInfo("race", "比賽期", "減量衝刺", 3, 2),
]


@dataclass
class PhaseAllocation:
    info: PhaseInfo
    start_date: date
    num_weeks: int


def allocate_phases(race_date: date, total_weeks: int) -> list:
    """Allocate training weeks to phases proportionally."""
    total_ideal = sum(p.ideal_weeks for p in PHASES)
    total_min = sum(p.min_weeks for p in PHASES)

    if total_weeks < total_min:
        print(f"Warning: {total_weeks} weeks is very short (minimum recommended: {total_min})", file=sys.stderr)

    # Start with minimum weeks for each phase
    allocated = [p.min_weeks for p in PHASES]
    remaining = total_weeks - sum(allocated)

    if remaining > 0:
        # Distribute remaining weeks proportionally to (ideal - min)
        extras = [p.ideal_weeks - p.min_weeks for p in PHASES]
        total_extra = sum(extras)
        if total_extra > 0:
            for i in range(len(PHASES)):
                share = int(remaining * extras[i] / total_extra)
                allocated[i] += share

            # Distribute any leftover from rounding to earlier phases (build more base)
            leftover = total_weeks - sum(allocated)
            for i in range(len(PHASES)):
                if leftover <= 0:
                    break
                can_add = PHASES[i].ideal_weeks * 2 - allocated[i]  # cap at 2x ideal
                add = min(leftover, max(0, can_add))
                allocated[i] += add
                leftover -= add

    # Build phase allocations with dates (working backward from race date)
    # Race day is on the last day of the last phase
    total_days = sum(w * 7 for w in allocated)
    start = race_date - timedelta(days=total_days - 1)

    result = []
    current_date = start
    for i, phase in enumerate(PHASES):
        result.append(PhaseAllocation(
            info=phase,
            start_date=current_date,
            num_weeks=allocated[i],
        ))
        current_date += timedelta(days=allocated[i] * 7)

    return result


# ---------------------------------------------------------------------------
# Workout Templates
# ---------------------------------------------------------------------------

def _build_pace_dict(zones: PaceZones) -> dict:
    """Build template format dict from pace zones."""
    return {
        "e_pace": format_pace_range(zones.e_low, zones.e_high),
        "m_pace": format_pace_range(zones.m_low, zones.m_high),
        "t_pace": format_pace_range(zones.t_low, zones.t_high),
        "i_pace": format_pace_range(zones.i_low, zones.i_high),
        "r_pace": format_pace_range(zones.r_low, zones.r_high),
    }


# Phase workout templates: each phase defines long, hard1, hard2 workout lists
# Templates cycle through the list across weeks
PHASE_WORKOUTS: dict = {
    "base1": {
        "long": [
            "長跑 21km ([E] {e_pace}) 途中穿插 1km 計時 ([I] {i_pace})",
            "長跑 21km ([E] {e_pace}) 穿插 1km 計時",
        ],
        "hard1": [
            "坡道全速衝刺 (80~120m) x 10組 (每趟完全恢復 2-3分)",
            "坡道全速衝刺 x 10組 (完全恢復)",
        ],
        "hard2": [
            "坡道衝刺 x 10組 (完全恢復) + 有氧5km",
            "法特萊克跑 (1分快 [T {t_pace}] / 1分慢 [E {e_pace}]) x 20組",
        ],
    },
    "base2": {
        "long": [
            "長跑 120分 ([E] {e_pace}) 穿插 1km 計時",
        ],
        "hard1": [
            "400m間歇 x 10組 ([R] {r_pace}) (每趟休 3分，完全恢復)",
            "400m間歇 x 10組 (休 3分)",
        ],
        "hard2": [
            "200m間歇 x 15組 ([R] {r_pace}) (每趟休 2分，維持姿勢)",
            "200m間歇 x 15組 (休 2分)",
        ],
    },
    "development": {
        "long": [
            "長跑 120分 ([E] {e_pace}) 穿插 1km 計時",
        ],
        "hard1": [
            "800m間歇 x 6組 ([I] {i_pace}) (每趟休 3分半，慢跑恢復)",
            "600m間歇 x 8組 ([I] {i_pace}) (每趟休 3分)",
            "800m間歇 x 6組 (休 3分半)",
            "600m間歇 x 8組 (休 3分)",
        ],
        "hard2": [
            "M配速跑 6-8km ([M] {m_pace}) (建立穩定感)",
            "M配速跑 6-8km ([M] {m_pace})",
        ],
        "time_trial": "有氧2k + 5km計時賽(目標{tt_5k}內) + 有氧3k",
    },
    "threshold1": {
        "long": [
            "長跑 21km ([E] {e_pace})",
        ],
        "hard1": [
            "OBLA(T)跑 6-8km ([T] {t_pace}) (組間休 90秒)",
            "OBLA(T)跑 6-8km ([T] {t_pace})",
        ],
        "hard2": [
            "VO2max(I)間歇 1km x 5~7組 ([I] {i_pace}) (每趟休 4分)",
            "VO2max(I)間歇 1.2km x 4~6組 ([I] {i_pace}) (每趟休 5分)",
            "VO2max(I)間歇 1km x 5~7組 (休 4分)",
        ],
    },
    "threshold2": {
        "long": [
            "起伏長跑 21km ([E] {e_pace})",
        ],
        "hard1": [
            "OBLA(T)跑 6-8km ([T] {t_pace}) (休 1分鐘)",
            "OBLA(T)間歇 2km x 3組 ([T] {t_pace}) (組間休 2分)",
            "OBLA(T)間歇 4km x 2組 ([T] {t_pace}) (組間休 3分)",
            "OBLA(T)間歇 3k+2k ([T] {t_pace}) (休 3分)",
            "OBLA(T)跑 6-8km",
        ],
        "hard2": [
            "VO2max(I)間歇 1km x 5組 ([I] {i_pace}) (休 4分)",
            "VO2max(I)間歇 1km x 5組 (休 4分)",
        ],
        "time_trial": "10km計時賽 + 有氧慢跑 10km",
    },
    "peak1": {
        "long": [
            "長跑 21km ([M] {m_pace}) + 1km x 3組 ([T] {t_pace}) (每趟休 3分)",
            "長跑 21km + 1km x 3組 (休 3分)",
            "長跑 25km ([M] {m_pace}) + 1km x 3組 ([T] {t_pace}) (休 3分)",
        ],
        "hard1": [
            "OBLA(T)跑 6-8km ([T] {t_pace}) (休 1分)",
            "OBLA(T)跑 6-8km (休 1分)",
        ],
        "hard2": [
            "有氧慢跑 + 短衝刺 (50m x 4~6組)",
            "有氧慢跑 + 短衝刺",
        ],
        "time_trial": "10km計時賽 (目標{tt_10k}) + 有氧慢跑 5km",
    },
    "summit": {
        "long": [
            "長跑 28~30km ([M] {m_pace})",
            "長跑 28~30km ([M] {m_pace})",
            "長跑 30~35km ([M] {m_pace})",
        ],
        "hard1": [
            "M配速間歇 1km x 8~12組 ([M] {m_pace}) (每趟休 75秒)",
            "M配速間歇 1km x 8~12組 (休 75秒)",
            "M配速跑 8~12km ([M] {m_pace}) (休 2分)",
            "M配速跑 8~12km (休 2分)",
        ],
        "hard2": [
            "法特萊克跑 (1分快 [T] / 1分慢 [E]) x 15組",
            "50/50 Sharpener 2km (磨利體感，50m快/50m慢)",
        ],
    },
    "race": {
        "long": [
            "長跑 28~30km ([M] {m_pace})",
            "M配速跑 14~21km ([M] {m_pace})",
            "OBLA(T)跑 10~14k ([T] {t_pace}) (休 2分)",
            "有氧慢跑 15-20km ([E] {e_pace})",
        ],
        "hard1": [
            "M配速跑 10~12km ([M] {m_pace})",
            "M配速跑 10~12km",
            "M配速跑 10~12km ([M] {m_pace}) (休 2分)",
        ],
        "hard2": [
            "法特萊克跑 x 15組",
            "50/50 Sharpener 2km",
            "有氧慢跑 + 短衝刺",
        ],
    },
}

# Final taper week (last 7 days before race)
TAPER_FINAL_WEEK = [
    "有氧慢跑 8km",
    "有氧慢跑 7km ([E] {e_pace})",
    "[減量週] 1km x 3組 ({near_m}) (休 3分) + 有氧3k",
    "有氧慢跑 5km",
    "有氧慢跑 4km",
    "有氧2k + 短衝刺 50m x 4~6組 (完全恢復)",
    "{race_name}",
]

# Second-to-last taper week
TAPER_PENULTIMATE_WEEK = [
    "M配速跑 14~21km ([M] {m_pace})",
    "有氧慢跑 10km ([E] {e_pace})",
    "有氧慢跑 10km ([E] {e_pace})",
    "M配速跑 10~12km ([M] {m_pace})",
    "有氧慢跑 10km ([E] {e_pace})",
    "有氧慢跑 10km ([E] {e_pace})",
    "有氧慢跑 30分鐘",
]


# ---------------------------------------------------------------------------
# Week / Day Schedule Builder
# ---------------------------------------------------------------------------

@dataclass
class DayEvent:
    subject: str
    date: date
    description: str


def _get_easy_run(pace_dict: dict) -> str:
    return "有氧慢跑 10~14km ([E] {e_pace})".format(**pace_dict)


def _depletion_easy(pace_dict: dict, phase_weeks_left: int) -> str:
    """In later phases, reduce easy run volume slightly."""
    if phase_weeks_left <= 1:
        return "有氧慢跑 8~10km".format(**pace_dict)
    return _get_easy_run(pace_dict)


def generate_phase_events(
    phase: PhaseAllocation,
    zones: PaceZones,
    vdot: float,
    race_name: str,
    goal_time_str: str,
) -> list:
    """Generate all daily events for a phase."""
    pace_dict = _build_pace_dict(zones)

    # Add time trial targets and race name to pace_dict
    tt_5k_sec = equivalent_race_time(vdot, 5000)
    tt_10k_sec = equivalent_race_time(vdot, 10000)
    pace_dict["tt_5k"] = format_race_time(tt_5k_sec)
    pace_dict["tt_10k"] = format_race_time(tt_10k_sec)
    pace_dict["race_name"] = race_name
    # Near-M pace for taper sharpening (slightly faster than M)
    near_m = format_pace((zones.m_low + zones.m_high) / 2)
    pace_dict["near_m"] = f"{near_m}/km"

    key = phase.info.key
    templates = PHASE_WORKOUTS.get(key, {})
    events = []

    for week_idx in range(phase.num_weeks):
        week_start = phase.start_date + timedelta(days=week_idx * 7)
        is_last_phase = (key == "race")
        is_final_week = is_last_phase and (week_idx == phase.num_weeks - 1)
        is_penultimate_week = is_last_phase and (week_idx == phase.num_weeks - 2)

        # Build description for this phase
        month = week_start.month
        goal_display = goal_time_str.rstrip(":00").rstrip(":")
        if ":" not in goal_display:
            goal_display = goal_time_str
        desc = f"{month}月:{phase.info.name_zh} ({phase.info.subtitle_zh}) | 目標: {goal_display}"

        if is_final_week:
            # Final taper week
            for day_idx, tmpl in enumerate(TAPER_FINAL_WEEK):
                d = week_start + timedelta(days=day_idx)
                subject = tmpl.format(**pace_dict)
                events.append(DayEvent(subject=subject, date=d, description=desc))
        elif is_penultimate_week:
            # Penultimate taper week
            for day_idx, tmpl in enumerate(TAPER_PENULTIMATE_WEEK):
                d = week_start + timedelta(days=day_idx)
                subject = tmpl.format(**pace_dict)
                events.append(DayEvent(subject=subject, date=d, description=desc))
        else:
            # Normal week: Long - Easy - Easy - Hard1 - Easy - Easy - Hard2
            weeks_left = phase.num_weeks - week_idx

            # Check for time trial weeks (mid-phase, every ~4 weeks)
            has_time_trial = (
                "time_trial" in templates
                and week_idx > 0
                and week_idx % 4 == 3
            )

            for day_idx in range(7):
                d = week_start + timedelta(days=day_idx)

                if day_idx == 0:  # Long run
                    long_list = templates.get("long", ["長跑 21km ([E] {e_pace})"])
                    tmpl = long_list[week_idx % len(long_list)]
                    subject = tmpl.format(**pace_dict)
                elif day_idx == 3:  # Hard 1
                    hard1_list = templates.get("hard1", [_get_easy_run(pace_dict)])
                    tmpl = hard1_list[week_idx % len(hard1_list)]
                    subject = tmpl.format(**pace_dict)
                elif day_idx == 6:  # Hard 2
                    if has_time_trial:
                        subject = templates["time_trial"].format(**pace_dict)
                    else:
                        hard2_list = templates.get("hard2", [_get_easy_run(pace_dict)])
                        tmpl = hard2_list[week_idx % len(hard2_list)]
                        subject = tmpl.format(**pace_dict)
                else:  # Easy days
                    subject = _depletion_easy(pace_dict, weeks_left)

                events.append(DayEvent(subject=subject, date=d, description=desc))

    return events


# ---------------------------------------------------------------------------
# CSV Output
# ---------------------------------------------------------------------------

def write_csv(events: list, output_path: str, lang: str = "zh"):
    """Write events to CSV file compatible with generate_calendar.py."""
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(["Subject", "Start Date", "All Day Event", "Description"])
        for event in events:
            subject = event.subject
            description = event.description
            if lang == "en":
                subject = translate(subject, include_original=False)
                description = translate(description, include_original=False)
            writer.writerow([
                subject,
                event.date.strftime("%Y-%m-%d"),
                "True",
                description,
            ])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_goal_time(s: str) -> int:
    """Parse goal time string to total seconds. Accepts H:MM:SS or H:MM."""
    parts = s.strip().split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 3600 + int(parts[1]) * 60
    raise ValueError(f"Invalid time format: {s}. Use H:MM:SS or H:MM")


def format_goal_display(seconds: int) -> str:
    """Format goal time for display in description field."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if m == 0:
        return f"{h}:0"
    return f"{h}:{m:02d}"


def main():
    parser = argparse.ArgumentParser(
        description="Generate marathon training plan using Daniels' VDOT system. "
                    "使用 Daniels VDOT 系統產生馬拉松訓練計畫。"
    )
    parser.add_argument(
        "--race-date", required=True,
        help="Race date (YYYY-MM-DD) / 比賽日期",
    )
    parser.add_argument(
        "--goal-time", required=True,
        help="Goal finish time (H:MM:SS or H:MM) / 目標完賽時間",
    )
    parser.add_argument(
        "--race-name", default="Marathon",
        help="Race name / 比賽名稱 (default: Marathon)",
    )
    parser.add_argument(
        "--weeks", type=int, default=0,
        help="Training weeks (16-52, default: auto from today) / 訓練週數",
    )
    parser.add_argument(
        "--lang", choices=["zh", "en"], default="zh",
        help="Output language: zh=繁體中文, en=English (default: zh)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output CSV file path / 輸出 CSV 路徑",
    )

    args = parser.parse_args()

    # Parse inputs
    try:
        race_date = datetime.strptime(args.race_date, "%Y-%m-%d").date()
    except ValueError:
        print("Error: Invalid date format. Use YYYY-MM-DD.", file=sys.stderr)
        sys.exit(1)

    try:
        goal_seconds = parse_goal_time(args.goal_time)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Calculate VDOT and pace zones
    vdot = vdot_from_marathon_time(goal_seconds)
    zones = pace_zones_from_vdot(vdot)

    print(f"=== Marathon Training Plan Generator ===")
    print(f"Race: {args.race_name} on {args.race_date}")
    print(f"Goal: {format_race_time(goal_seconds)}")
    print(f"VDOT: {vdot:.1f}")
    print(f"")
    print(f"Pace Zones:")
    print(f"  E (Easy):      {format_pace_range(zones.e_low, zones.e_high)}")
    print(f"  M (Marathon):  {format_pace_range(zones.m_low, zones.m_high)}")
    print(f"  T (Threshold): {format_pace_range(zones.t_low, zones.t_high)}")
    print(f"  I (Interval):  {format_pace_range(zones.i_low, zones.i_high)}")
    print(f"  R (Repetition):{format_pace_range(zones.r_low, zones.r_high)}")
    print()

    # Determine training weeks
    if args.weeks > 0:
        total_weeks = max(16, min(52, args.weeks))
    else:
        today = date.today()
        days_until_race = (race_date - today).days
        if days_until_race < 0:
            print("Error: Race date is in the past.", file=sys.stderr)
            sys.exit(1)
        total_weeks = min(42, days_until_race // 7)
        if total_weeks < 16:
            print(f"Warning: Only {total_weeks} weeks until race. Minimum recommended is 16.", file=sys.stderr)
            total_weeks = max(total_weeks, 12)

    # Allocate phases
    phases = allocate_phases(race_date, total_weeks)

    print(f"Training period: {total_weeks} weeks")
    print(f"Start date: {phases[0].start_date}")
    print(f"")
    print(f"Phase allocation:")
    for p in phases:
        end = p.start_date + timedelta(days=p.num_weeks * 7 - 1)
        print(f"  {p.info.name_zh} ({p.info.subtitle_zh}): {p.num_weeks} weeks ({p.start_date} ~ {end})")
    print()

    # Generate events
    goal_display = format_goal_display(goal_seconds)
    all_events = []
    for phase in phases:
        events = generate_phase_events(phase, zones, vdot, args.race_name, goal_display)
        all_events.extend(events)

    # Determine output path
    output_path = args.output
    if not output_path:
        safe_name = args.race_name.replace(" ", "_")
        output_path = f"{safe_name}_訓練計畫.csv"

    # Write CSV
    write_csv(all_events, output_path, args.lang)

    print(f"Generated {len(all_events)} training days")
    print(f"Output: {output_path}")
    print(f"")
    print(f"Next step: Generate calendar with:")
    print(f'  python3 generate_calendar.py "{output_path}" --name "{args.race_name}"')


if __name__ == "__main__":
    main()
