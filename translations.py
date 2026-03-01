"""
Bilingual translations for marathon training plan terms.
Supports Traditional Chinese (zh-TW) and English (en).
"""

# Workout type translations (Chinese → English)
WORKOUT_TERMS = {
    "有氧慢跑": "Easy Run",
    "長跑": "Long Run",
    "起伏長跑": "Hilly Long Run",
    "間歇": "Interval",
    "坡道全速衝刺": "Hill Sprint",
    "坡道衝刺": "Hill Sprint",
    "坡道短距離全速衝刺": "Hill Sprint",
    "短距離全速衝刺": "Short Sprint",
    "短衝刺": "Short Sprint",
    "衝刺": "Sprint",
    "法特萊克跑": "Fartlek Run",
    "法特萊克": "Fartlek",
    "配速跑": "Pace Run",
    "配速間歇": "Pace Interval",
    "計時賽": "Time Trial",
    "計時": "Time Trial",
    "慢跑恢復": "Jog Recovery",
    "完全恢復": "Full Recovery",
    "減量週": "Taper Week",
    "磨利體感": "sharpen feel",
    "有氧": "Aerobic",
}

# Training phase translations
PHASE_TERMS = {
    "基礎期1": "Base Phase 1",
    "基礎期2": "Base Phase 2",
    "基礎期": "Base Phase",
    "開發期": "Development Phase",
    "閾值期1": "Threshold Phase 1",
    "閾值期2": "Threshold Phase 2",
    "閾值期": "Threshold Phase",
    "高峰期1": "Peak Phase 1",
    "高峰期2": "Peak Phase 2",
    "高峰期": "Peak Phase",
    "巔峰期": "Summit Phase",
    "比賽期": "Race Phase",
}

# Phase subtitle translations
PHASE_SUBTITLE_TERMS = {
    "坡道與有氧": "Hills & Aerobic",
    "速度開發": "Speed Development",
    "心肺刺激": "Cardio Stimulation",
    "乳酸門檻": "Lactate Threshold",
    "耐力強化": "Endurance Building",
    "M配速整合": "Marathon Pace Integration",
    "全馬專項": "Marathon Specific",
    "減量衝刺": "Taper & Race",
}

# General terms
GENERAL_TERMS = {
    "目標": "Goal",
    "組": "sets",
    "每趟休": "rest between sets",
    "組間休": "rest between sets",
    "休": "rest",
    "分鐘": "min",
    "維持姿勢": "maintain form",
    "建立穩定感": "build consistency",
    "途中穿插": "with intermittent",
    "穿插": "with intermittent",
    "訓練課表": "Workout",
}


def translate(text: str, include_original: bool = True) -> str:
    """
    Translate Chinese training text to English.

    Args:
        text: Original Chinese text
        include_original: If True, return "Chinese (English)" format.
                         If False, return English only.

    Returns:
        Translated text
    """
    if not text:
        return text

    translated = text

    # Apply all translation dictionaries
    all_terms = {}
    all_terms.update(GENERAL_TERMS)
    all_terms.update(PHASE_SUBTITLE_TERMS)
    all_terms.update(PHASE_TERMS)
    all_terms.update(WORKOUT_TERMS)

    # Sort by length (longest first) to avoid partial replacements
    for zh, en in sorted(all_terms.items(), key=lambda x: len(x[0]), reverse=True):
        translated = translated.replace(zh, en)

    if include_original and translated != text:
        return f"{text} ({translated})"
    elif not include_original:
        return translated
    return text
