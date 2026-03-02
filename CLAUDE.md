# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Vision

Build an **AI-powered dynamic marathon training platform** that generates, monitors, and adapts personalized training plans in real-time. The system uses running watch data, physiological metrics, and environmental factors to optimize training toward a race goal (target date + finish time for half/full marathon).

### Long-Term Roadmap

1. **Phase 1 (Done)**: CSV-to-ICS calendar generator with bilingual support
2. **Phase 2 (Done)**: Marathon plan generator — Daniels' VDOT-based periodized plans from goal race date/time
3. **Phase 3 (Done)**: Running watch data integration — parse FIT/TCX/GPX exports from COROS / Garmin (pace, heart rate, cadence, stride length, power, elevation, GPS routes)
4. **Phase 3b (Done)**: Intervals.icu sync + activity store + HTML dashboard — auto-sync via REST API, local JSON store with dedup, Chart.js dashboard (weekly volume, cardiac efficiency, zone distribution, fitness/fatigue, latest run card)
5. **Phase 4**: Predictive model — use large-scale running datasets to model pace/HR/effort correlations, predict race performance (VDOT, race equivalency, fatigue curves), and compute a composite "readiness score"
6. **Phase 5**: Dynamic plan adaptation — feed execution data back into the model to adjust upcoming workouts, modify intensity/volume, and re-forecast goal achievability
7. **Phase 6**: Full app with scoring system — quantified training load, recovery score, weather/altitude/location adjustments, short-term & long-term goal tracking dashboards

### Key Data Dimensions to Model

- **Performance**: pace zones (E/M/T/I/R), heart rate zones, VO2max estimates, lactate threshold
- **Load & Recovery**: training stress score (TSS), acute/chronic training load (ATL/CTL), rest/sleep quality
- **Environment**: weather (temperature, humidity), altitude, terrain profile, race course specifics
- **Biomechanics**: cadence, ground contact time, vertical oscillation, stride length (from watch sensors)
- **Longitudinal**: historical race results, injury history, training volume trends

## Commands

```bash
# --- Phase 3b: Intervals.icu sync + dashboard ---
pip install -r requirements.txt           # install fitparse + requests
python3 -m watch_sync sync --days 30      # sync last 30 days from Intervals.icu
python3 -m watch_sync sync                # sync last 7 days (default)
python3 -m watch_sync sync --open         # sync + open dashboard
python3 -m watch_sync dashboard --open    # regenerate + open dashboard
./sync.sh                                 # convenience: sync + dashboard

# --- Phase 3: Parse watch exports ---
python3 -m watch_sync parse activity.fit        # parse a single FIT file
python3 -m watch_sync parse exports/ --format fit  # parse a directory
python3 -m watch_sync activity.fit -o summary.json  # JSON output (backward-compat)
python3 -m watch_sync activity.fit -o data.csv --detail  # per-second CSV

# --- Phase 2: Generate training plan ---
# Sub-3:00 marathon plan (42 weeks, Chinese output)
python3 plan_generator.py --race-date 2026-12-20 --goal-time 3:00:00 --race-name "台北馬拉松"

# 3:30 goal, 30 weeks, English output
python3 plan_generator.py --race-date 2026-12-20 --goal-time 3:30:00 --weeks 30 --lang en -o plan.csv

# --- Phase 1: Generate calendar from CSV ---
python3 generate_calendar.py <csv_file> --name "Name" --lang both

# Full pipeline: generate plan → generate calendar
python3 plan_generator.py --race-date 2026-12-20 --goal-time 3:00:00 --race-name "台北馬拉松" -o plan.csv
python3 generate_calendar.py plan.csv --name "台北馬拉松" --lang both
```

## Architecture

- **`plan_generator.py`** — Marathon training plan generator using Daniels' VDOT system. Calculates pace zones from goal time, allocates 8 training phases proportionally to available weeks, generates daily workouts from phase-specific templates. Outputs CSV.
- **`generate_calendar.py`** — CSV-to-ICS calendar converter. Reads plan CSV, generates RFC 5545 ICS with proper line folding and escaping. Compatible with Outlook, Google Calendar, Apple Calendar.
- **`translations.py`** — Bilingual term dictionaries (workout types, training phases, general terms) and `translate()` function. Terms are sorted longest-first to prevent partial matches.
- **`trainning_plans/`** — Reference training plan files (CSV and ICS examples).

### Implemented Modules
- **`watch_sync/`** — Parse FIT/TCX/GPX activity exports and sync from Intervals.icu. FIT parser uses `fitparse`; TCX/GPX use stdlib. Includes Intervals.icu REST client (`intervals_api.py`), append-only JSON activity store (`activity_store.py`), and Chart.js HTML dashboard generator (`dashboard.py`). API key stored in `running_data/.env` (gitignored).

### Planned Modules
- **`models/`** — Predictive models for performance, fatigue, race outcome
- **`scoring/`** — Composite scoring system (training load, readiness, goal progress)
- **`app/`** — Web/mobile interface for dashboards and plan management

## VDOT System (plan_generator.py)

Pace zones are calculated from Daniels' Running Formula equations:
- `VO2 = -4.60 + 0.182258*v + 0.000104*v²` (v in m/min)
- `%VO2max = 0.8 + 0.1894393*e^(-0.012778*t) + 0.2989558*e^(-0.1932605*t)`
- `VDOT = VO2 / %VO2max`

Zones: E (59-74%), M (75-84%), T (83-88%), I (95-100%), R (105-110%)

## 8-Phase Periodization

Base 1 (Hills) → Base 2 (Speed) → Development (VO2max) → Threshold 1 (LT) → Threshold 2 (Endurance) → Peak (M-pace Integration) → Summit (Marathon Specific) → Race (Taper)

Weekly pattern: Long Run → Easy → Easy → Hard 1 → Easy → Easy → Hard 2

## CSV Format

```
Subject,Start Date,All Day Event,Description
"有氧慢跑 10~14km ([E] 5:12~5:46/km)",2026-03-02,True,"4月:基礎期1 (坡道與有氧) | 目標: 3:0"
```

## Key Design Decisions

- Core modules (Phase 1-2) have zero external dependencies; `watch_sync` requires `fitparse` for FIT files and `requests` for Intervals.icu sync (TCX/GPX use stdlib only)
- ICS via string formatting with RFC 5545 line folding at 75 octets
- Translation uses longest-match-first replacement to avoid partial term collisions
- Workout templates use `{pace}` placeholders filled with computed VDOT zones — same structure, different paces per goal time
- Phase allocation adapts proportionally to available weeks (16-52 weeks supported)
- Bilingual (Traditional Chinese / English) as first-class requirement throughout
