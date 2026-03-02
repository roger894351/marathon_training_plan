# Marathon Training Plan / 馬拉松訓練計畫

> AI-powered dynamic marathon training platform — from calendar generation to adaptive training with real-time watch data.

> AI 驅動的動態馬拉松訓練平台 — 從行事曆產生到結合跑錶即時數據的自適應訓練。

## Vision / 願景

Build an intelligent training system that generates personalized marathon plans, integrates running watch data (COROS / Apple Watch / Garmin), predicts race performance, and dynamically adapts training based on execution metrics, environmental conditions, and goal progress.

打造一套智慧訓練系統：產生個人化馬拉松計畫、整合跑錶數據（COROS / Apple Watch / Garmin）、預測比賽表現，並根據訓練執行狀況、環境條件及目標進度動態調整訓練。

### Roadmap / 開發路線圖

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | CSV → ICS calendar generator (bilingual) | Done |
| 2 | Marathon plan generator (Daniels' VDOT periodized plans) | Done |
| 3 | Running watch data integration (FIT/TCX/GPX parsing) | Done |
| 3b | Intervals.icu sync + activity store + dashboard | Done |
| 4 | Predictive model (pace/HR/effort correlations, race forecasting) | Planned |
| 5 | Dynamic plan adaptation (auto-adjust based on execution data) | Planned |
| 6 | Scoring system & app (training load, readiness, goal dashboards) | Planned |

---

## Requirements / 需求

- Python 3.9+
- Core modules: no external dependencies / 核心模組無需額外套件
- Watch sync: `pip install -r requirements.txt` (installs `fitparse` + `requests`)

---

## Phase 2: Plan Generator / 訓練計畫產生器

Generate a periodized marathon training plan using Daniels' VDOT system.

使用 Daniels VDOT 系統產生週期化馬拉松訓練計畫。

```bash
python3 plan_generator.py --race-date <YYYY-MM-DD> --goal-time <H:MM:SS> --race-name <name> [options]
```

| Flag | Description | 說明 |
|------|-------------|------|
| `--race-date` | Race date (required) | 比賽日期 |
| `--goal-time` | Goal finish time H:MM:SS or H:MM (required) | 目標完賽時間 |
| `--race-name` | Race name (default: Marathon) | 比賽名稱 |
| `--weeks` | Training weeks 16-52 (default: auto) | 訓練週數 |
| `--lang` | `zh` / `en` (default: zh) | 輸出語言 |
| `--output` / `-o` | Output CSV path | 輸出路徑 |

### Examples / 範例

```bash
# Sub-3:00 marathon, 42-week plan / 破三計畫
python3 plan_generator.py --race-date 2026-12-20 --goal-time 3:00:00 --race-name "台北馬拉松"

# 3:30 goal, 30 weeks, English / 3小時30分目標
python3 plan_generator.py --race-date 2026-12-20 --goal-time 3:30:00 --weeks 30 --lang en

# Full pipeline: generate plan → generate calendar / 完整流程
python3 plan_generator.py --race-date 2026-12-20 --goal-time 3:00:00 --race-name "台北馬拉松" -o plan.csv
python3 generate_calendar.py plan.csv --name "台北馬拉松" --lang both
```

### VDOT Pace Zones / 配速區間

The generator calculates pace zones from your goal time using Daniels' Running Formula:

| Zone | Purpose | Example (sub-3:00) |
|------|---------|-------------------|
| E (Easy) | Aerobic base / 有氧基礎 | 4:37~5:33/km |
| M (Marathon) | Race pace / 比賽配速 | 4:10~4:23/km |
| T (Threshold) | Lactate threshold / 乳酸閾值 | 4:01~4:13/km |
| I (Interval) | VO2max / 最大攝氧量 | 3:37~3:46/km |
| R (Repetition) | Speed / 速度 | 3:21~3:29/km |

### 8-Phase Periodization / 八階段週期化

Base 1 (Hills) → Base 2 (Speed) → Development (VO2max) → Threshold 1 → Threshold 2 → Peak (M-pace) → Summit (Marathon Specific) → Race (Taper)

---

## Phase 3: Watch Data Sync / 跑錶數據同步

Parse running watch exports (FIT, TCX, GPX) and extract workout metrics.

解析跑錶匯出檔案（FIT、TCX、GPX）並擷取訓練數據。

```bash
# Install dependency / 安裝依賴
pip install -r requirements.txt

# Parse a single FIT file / 解析單一 FIT 檔案
python3 -m watch_sync activity.fit

# Parse a directory / 解析目錄中的所有檔案
python3 -m watch_sync exports/ --format fit

# Output as JSON / 輸出 JSON
python3 -m watch_sync activity.fit -o summary.json

# Detailed per-second CSV / 逐秒詳細 CSV
python3 -m watch_sync activity.fit -o data.csv --detail
```

| Flag | Description | 說明 |
|------|-------------|------|
| positional | File or directory path | 檔案或目錄路徑 |
| `--format` | Force format: fit/tcx/gpx (default: auto) | 強制格式 |
| `-o` / `--output` | Output path (.json or .csv) | 輸出路徑 |
| `--detail` | Per-second data points in CSV | 逐秒數據 |

### Supported Formats / 支援格式

| Format | Source | Metrics |
|--------|--------|---------|
| FIT | COROS, Garmin (native) | All: HR, pace, cadence, power, stride, ground contact |
| TCX | Garmin Connect export | HR, pace, cadence, altitude, GPS |
| GPX | Universal GPS format | GPS, elevation, optional HR via extensions |

### Computed Metrics / 計算指標

- **VDOT estimate**: Daniels' formula from workout distance/time
- **Pace zone distribution**: Time in E/M/T/I/R zones (%)
- **Per-km splits**: Pace and HR per kilometer

---

## Phase 3b: Intervals.icu Sync + Dashboard / 數據同步與儀表板

Sync activity and wellness data from Intervals.icu, store locally, and visualize with an interactive dashboard.

從 Intervals.icu 同步活動與健康數據，本地儲存，並以互動式儀表板視覺化。

```bash
# Setup: copy .env.example and add your API key / 設定 API 金鑰
cp .env.example running_data/.env
# Edit running_data/.env with your Intervals.icu API key

# Sync last 30 days / 同步最近 30 天
python3 -m watch_sync sync --days 30

# Regular sync (7 days) + open dashboard / 常規同步 + 開啟儀表板
python3 -m watch_sync sync --open

# Regenerate dashboard / 重新產生儀表板
python3 -m watch_sync dashboard --open

# Convenience script / 便利腳本
./sync.sh
```

### Dashboard Charts / 儀表板圖表

| Chart | Description | 說明 |
|-------|-------------|------|
| Weekly Volume | Bar chart of km/week | 每週跑量長條圖 |
| Cardiac Efficiency | Pace/HR trend over time | 心臟效率趨勢 |
| Zone Distribution | Stacked bar of E/M/T/I/R per week | 每週配速區間分布 |
| Fitness & Fatigue | CTL/ATL training load curves | 體能/疲勞訓練負荷曲線 |
| Latest Run Card | Summary of most recent activity | 最近活動摘要 |

---

## Phase 1: Calendar Generator / 行事曆產生器

Convert training plan CSV into ICS calendar files for Outlook, Google Calendar, or Apple Calendar.

將訓練計畫 CSV 轉換為 ICS 行事曆檔案。

```bash
python3 generate_calendar.py <csv_file> --name <marathon_name> [options]
```

| Flag | Description | 說明 |
|------|-------------|------|
| `--name` | Marathon name (used as event prefix) | 馬拉松名稱 |
| `--lang` | `zh` / `en` / `both` (default: `both`) | 語言選擇 |
| `--output` / `-o` | Output file path | 輸出路徑 |

### Importing / 匯入行事曆

- **Google Calendar**: Settings > Import & Export > Import
- **Outlook**: File > Open & Export > Import/Export
- **Apple Calendar**: File > Import, or double-click the `.ics` file

---

## Contributing / 貢獻

See [CLAUDE.md](CLAUDE.md) for architecture details, design decisions, and the full project roadmap.
