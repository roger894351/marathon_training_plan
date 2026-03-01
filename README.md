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
| 2 | Marathon plan generator (periodized plans from goal race) | Planned |
| 3 | Running watch data integration (COROS / Apple Watch / Garmin) | Planned |
| 4 | Predictive model (pace/HR/effort correlations, race forecasting) | Planned |
| 5 | Dynamic plan adaptation (auto-adjust based on execution data) | Planned |
| 6 | Scoring system & app (training load, readiness, goal dashboards) | Planned |

---

## Phase 1: Calendar Generator / 行事曆產生器

Convert marathon training plan CSV files into ICS calendar files importable by Outlook, Google Calendar, or Apple Calendar.

將馬拉松訓練計畫 CSV 檔案轉換為 ICS 行事曆檔案，可匯入 Outlook、Google 日曆或 Apple 行事曆。

## Requirements / 需求

- Python 3.9+
- No external dependencies / 無需安裝額外套件

## Usage / 使用方式

```bash
python3 generate_calendar.py <csv_file> --name <marathon_name> [options]
```

### Options / 選項

| Flag | Description | 說明 |
|------|-------------|------|
| `--name` | Marathon name (used as event prefix) | 馬拉松名稱（作為事件前綴） |
| `--lang` | `zh` / `en` / `both` (default: `both`) | 語言選擇 |
| `--output` / `-o` | Output file path | 輸出檔案路徑 |

### Examples / 範例

```bash
# Bilingual output (default) / 雙語輸出（預設）
python3 generate_calendar.py trainning_plans/台北馬拉松_訓練計畫.csv --name "台北馬拉松"

# Chinese only / 僅中文
python3 generate_calendar.py trainning_plans/台北馬拉松_訓練計畫.csv --name "台北馬拉松" --lang zh

# English only / 僅英文
python3 generate_calendar.py trainning_plans/台北馬拉松_訓練計畫.csv --name "Taipei Marathon" --lang en

# Custom output path / 自訂輸出路徑
python3 generate_calendar.py plan.csv --name "My Marathon" -o my_calendar.ics
```

## CSV Format / CSV 格式

The input CSV must have these columns / 輸入 CSV 需包含以下欄位：

```csv
Subject,Start Date,All Day Event,Description
"有氧慢跑 10~14km ([E] 5:12~5:46/km)",2026-03-02,True,"4月:基礎期1 (坡道與有氧) | 目標: 3:0"
```

| Column | Format | 說明 |
|--------|--------|------|
| `Subject` | Workout description | 訓練內容 |
| `Start Date` | `YYYY-MM-DD` | 日期 |
| `All Day Event` | `True` / `False` | 全天事件 |
| `Description` | Training phase info | 訓練階段資訊 |

## Importing the Calendar / 匯入行事曆

- **Google Calendar**: Settings > Import & Export > Import
- **Outlook**: File > Open & Export > Import/Export
- **Apple Calendar**: File > Import, or double-click the `.ics` file

---

## Contributing / 貢獻

See [CLAUDE.md](CLAUDE.md) for architecture details, design decisions, and the full project roadmap.
