#!/usr/bin/env python3
"""
Marathon Training Plan Calendar Generator

Reads a CSV training plan and generates an ICS calendar file
compatible with Outlook, Google Calendar, and Apple Calendar.
Supports Traditional Chinese and English bilingual content.

Usage:
    python generate_calendar.py <csv_file> [options]

Examples:
    python generate_calendar.py trainning_plans/台北馬拉松_訓練計畫.csv --name "台北馬拉松"
    python generate_calendar.py plan.csv --name "Boston Marathon" --lang en --output boston.ics
"""

import argparse
import csv
import sys
import uuid
from datetime import datetime, timedelta

from translations import translate


def generate_uid() -> str:
    """Generate a unique ID for a calendar event."""
    return f"{uuid.uuid4().hex[:12]}@marathon-plan.app"


def escape_ics_text(text: str) -> str:
    """Escape special characters for ICS format (RFC 5545)."""
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\n", "\\n")
    return text


def fold_ics_line(line: str) -> str:
    """Fold long lines per RFC 5545 (max 75 octets per line)."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line

    result = []
    current = b""
    for char in line:
        char_bytes = char.encode("utf-8")
        if len(current) + len(char_bytes) > 75:
            result.append(current.decode("utf-8"))
            current = b" " + char_bytes  # continuation line starts with space
        else:
            current += char_bytes
    if current:
        result.append(current.decode("utf-8"))
    return "\r\n".join(result)


def format_summary(subject: str, marathon_name: str, lang: str) -> str:
    """Format the event summary based on language preference."""
    prefix = f"[{marathon_name}] " if marathon_name else ""

    if lang == "zh":
        return f"{prefix}{subject}"
    elif lang == "en":
        translated = translate(subject, include_original=False)
        return f"{prefix}{translated}"
    else:  # both
        translated = translate(subject, include_original=False)
        if translated != subject:
            return f"{prefix}{subject} ({translated})"
        return f"{prefix}{subject}"


def format_description(description: str, subject: str, lang: str) -> str:
    """Format the event description based on language preference."""
    if lang == "zh":
        lines = [f"訓練課表：{subject}"]
        if description:
            lines.append(f"階段：{description}")
        return "\\n".join(lines)
    elif lang == "en":
        translated_subject = translate(subject, include_original=False)
        lines = [f"Workout: {translated_subject}"]
        if description:
            translated_desc = translate(description, include_original=False)
            lines.append(f"Phase: {translated_desc}")
        return "\\n".join(lines)
    else:  # both
        translated_subject = translate(subject, include_original=False)
        lines = [f"訓練課表 / Workout：{subject}"]
        if translated_subject != subject:
            lines.append(f"Workout: {translated_subject}")
        if description:
            translated_desc = translate(description, include_original=False)
            lines.append(f"階段 / Phase：{description}")
            if translated_desc != description:
                lines.append(f"Phase: {translated_desc}")
        return "\\n".join(lines)


def read_csv(filepath: str) -> list[dict]:
    """Read training plan from CSV file."""
    events = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            subject = row.get("Subject", "").strip()
            start_date = row.get("Start Date", "").strip()
            description = row.get("Description", "").strip()

            if not subject or not start_date:
                continue

            events.append({
                "subject": subject,
                "start_date": start_date,
                "description": description,
            })
    return events


def generate_ics(events: list[dict], marathon_name: str, lang: str) -> str:
    """Generate ICS calendar content from events."""
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Marathon Plan Generator//TW",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for event in events:
        # Parse date
        try:
            dt = datetime.strptime(event["start_date"], "%Y-%m-%d")
        except ValueError:
            print(f"Warning: skipping event with invalid date: {event['start_date']}", file=sys.stderr)
            continue

        dt_start = dt.strftime("%Y%m%d")
        dt_end = (dt + timedelta(days=1)).strftime("%Y%m%d")

        summary = format_summary(event["subject"], marathon_name, lang)
        description = format_description(event["description"], event["subject"], lang)

        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{generate_uid()}")
        lines.append(f"DTSTAMP:{now}")
        lines.append(f"DTSTART;VALUE=DATE:{dt_start}")
        lines.append(f"DTEND;VALUE=DATE:{dt_end}")
        lines.append(f"SUMMARY:{escape_ics_text(summary)}")
        lines.append(f"DESCRIPTION:{escape_ics_text(description)}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")

    # Fold long lines and join with CRLF
    folded = [fold_ics_line(line) for line in lines]
    return "\r\n".join(folded) + "\r\n"


def main():
    parser = argparse.ArgumentParser(
        description="Generate ICS calendar from marathon training plan CSV. "
                    "產生馬拉松訓練計畫行事曆檔案。"
    )
    parser.add_argument(
        "csv_file",
        help="Path to the training plan CSV file / 訓練計畫 CSV 檔案路徑",
    )
    parser.add_argument(
        "--name",
        default="Marathon Training",
        help="Marathon name for event prefix / 馬拉松名稱 (default: Marathon Training)",
    )
    parser.add_argument(
        "--lang",
        choices=["zh", "en", "both"],
        default="both",
        help="Output language: zh=繁體中文, en=English, both=雙語 (default: both)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output ICS file path / 輸出 ICS 檔案路徑 (default: <marathon_name>.ics)",
    )

    args = parser.parse_args()

    # Read CSV
    events = read_csv(args.csv_file)
    if not events:
        print("Error: No valid events found in CSV file.", file=sys.stderr)
        sys.exit(1)

    print(f"Read {len(events)} events from {args.csv_file}")

    # Generate ICS
    ics_content = generate_ics(events, args.name, args.lang)

    # Determine output path
    output_path = args.output
    if not output_path:
        safe_name = args.name.replace(" ", "_")
        output_path = f"{safe_name}_training_plan.ics"

    # Write ICS file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ics_content)

    print(f"Calendar generated: {output_path}")
    print(f"Language: {args.lang}")
    print(f"Events: {len(events)}")
    print(f"\nImport this .ics file into:")
    print(f"  - Google Calendar: Settings > Import & Export > Import")
    print(f"  - Outlook: File > Open & Export > Import/Export")
    print(f"  - Apple Calendar: File > Import or double-click the .ics file")


if __name__ == "__main__":
    main()
