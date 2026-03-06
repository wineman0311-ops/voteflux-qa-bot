"""
Configuration settings for VoteFlux QA automation bot.

Loads environment variables with sensible defaults.
Platform list is now managed dynamically via PlatformStore.
"""

import os
from typing import List, Dict, Any

# Telegram Configuration
TG_BOT_TOKEN: str = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID: str = os.environ.get("TG_CHAT_ID", "")

# Cron Schedule Configuration
CRON_SCHEDULE: str = os.environ.get("CRON_SCHEDULE", "0 9 * * *")

# VoteFlux Login Credentials
VF_EMAIL: str = os.environ.get("VF_EMAIL", "")
VF_PASSWORD: str = os.environ.get("VF_PASSWORD", "")

# Reports Directory
REPORTS_DIR: str = os.environ.get("REPORTS_DIR", "./reports")

# Platform Store Path
PLATFORM_STORE_PATH: str = os.environ.get("PLATFORM_STORE_PATH", "./platforms.json")

# Countries Configuration (static — less likely to change)
COUNTRIES: List[Dict[str, Any]] = [
    {
        "id": "india",
        "name": "印度",
        "flag": "🇮🇳",
        "name_en": "India",
        "search_keywords": ["economy", "cricket", "politics", "Modi"],
    },
    {
        "id": "bangladesh",
        "name": "孟加拉",
        "flag": "🇧🇩",
        "name_en": "Bangladesh",
        "search_keywords": ["election", "politics", "garment industry"],
    },
    {
        "id": "vietnam",
        "name": "越南",
        "flag": "🇻🇳",
        "name_en": "Vietnam",
        "search_keywords": ["economy", "National Assembly", "trade"],
    },
    {
        "id": "thailand",
        "name": "泰國",
        "flag": "🇹🇭",
        "name_en": "Thailand",
        "search_keywords": ["election", "tourism", "tariff"],
    },
    {
        "id": "malaysia",
        "name": "馬來西亞",
        "flag": "🇲🇾",
        "name_en": "Malaysia",
        "search_keywords": ["trade", "semiconductor", "politics"],
    },
    {
        "id": "philippines",
        "name": "菲律賓",
        "flag": "🇵🇭",
        "name_en": "Philippines",
        "search_keywords": ["ICC", "South China Sea", "central bank"],
    },
    {
        "id": "cambodia",
        "name": "柬埔寨",
        "flag": "🇰🇭",
        "name_en": "Cambodia",
        "search_keywords": ["border conflict", "scam centers", "Hun Sen"],
    },
]
