# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Vision

Build an **AI-powered dynamic marathon training platform** that generates, monitors, and adapts personalized training plans in real-time. The system uses running watch data, physiological metrics, and environmental factors to optimize training toward a race goal (target date + finish time for half/full marathon).

### Long-Term Roadmap

1. **Phase 1 (Current)**: CSV-to-ICS calendar generator with bilingual support
2. **Phase 2**: Marathon plan generator — create periodized training plans from goal race date/time, current fitness level, and training history
3. **Phase 3**: Running watch data integration — extract metrics from COROS / Apple Watch / Garmin (pace, heart rate, cadence, stride length, power, elevation, GPS routes)
4. **Phase 4**: Predictive model — use large-scale running datasets to model pace/HR/effort correlations, predict race performance (VDOT, race equivalency, fatigue curves), and compute a composite "readiness score"
5. **Phase 5**: Dynamic plan adaptation — feed execution data back into the model to adjust upcoming workouts, modify intensity/volume, and re-forecast goal achievability
6. **Phase 6**: Full app with scoring system — quantified training load, recovery score, weather/altitude/location adjustments, short-term & long-term goal tracking dashboards

### Key Data Dimensions to Model

- **Performance**: pace zones (E/M/T/I/R), heart rate zones, VO2max estimates, lactate threshold
- **Load & Recovery**: training stress score (TSS), acute/chronic training load (ATL/CTL), rest/sleep quality
- **Environment**: weather (temperature, humidity), altitude, terrain profile, race course specifics
- **Biomechanics**: cadence, ground contact time, vertical oscillation, stride length (from watch sensors)
- **Longitudinal**: historical race results, injury history, training volume trends

## Commands

```bash
# Generate calendar (bilingual, default)
python3 generate_calendar.py trainning_plans/台北馬拉松_訓練計畫.csv --name "台北馬拉松"

# Generate with specific language
python3 generate_calendar.py <csv_file> --name "Name" --lang zh    # Chinese only
python3 generate_calendar.py <csv_file> --name "Name" --lang en    # English only
python3 generate_calendar.py <csv_file> --name "Name" --lang both  # Bilingual

# Custom output path
python3 generate_calendar.py <csv_file> --name "Name" --output my_plan.ics
```

## Architecture

### Current (Phase 1)
- **`generate_calendar.py`** — Main CLI script. Reads CSV, generates RFC 5545 ICS with proper line folding and escaping. No external dependencies (stdlib only).
- **`translations.py`** — Bilingual term dictionaries (workout types, training phases, general terms) and `translate()` function. Terms are sorted longest-first to prevent partial matches.
- **`trainning_plans/`** — Reference training plan files (CSV and ICS examples).

### Planned Modules
- **`plan_generator/`** — Periodized plan creation engine (Daniels' Running Formula, Pfitzinger, Hanson methods)
- **`watch_sync/`** — Data extraction from COROS API, Apple HealthKit, Garmin Connect
- **`models/`** — Predictive models for performance, fatigue, race outcome
- **`scoring/`** — Composite scoring system (training load, readiness, goal progress)
- **`app/`** — Web/mobile interface for dashboards and plan management

## CSV Input Format

```
Subject,Start Date,All Day Event,Description
"有氧慢跑 10~14km ([E] 5:12~5:46/km)",2026-03-02,True,"4月:基礎期1 (坡道與有氧) | 目標: 3:0"
```

## Key Design Decisions

- ICS generated via string formatting (no `icalendar` pip package) to keep zero external dependencies
- All events are all-day events (`DTSTART;VALUE=DATE`)
- Line folding at 75 octets per RFC 5545 with UTF-8 awareness
- Translation uses longest-match-first replacement to avoid partial term collisions
- Bilingual (Traditional Chinese / English) as first-class requirement throughout
