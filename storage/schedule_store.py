"""
Schedule storage and management.

Handles persistence of cron schedule with validation.
"""

import json
from pathlib import Path
from typing import Optional

try:
    from croniter import croniter
except ImportError:
    croniter = None


class ScheduleStore:
    """Manages persistence and validation of cron schedules."""

    def __init__(self, storage_path: str = "./schedule.json") -> None:
        """
        Initialize ScheduleStore.

        Args:
            storage_path: Path to JSON file for schedule persistence
        """
        self.storage_path = Path(storage_path)

    def get_schedule(self) -> str:
        """
        Retrieve current cron schedule.

        Returns default "0 9 * * *" if file doesn't exist or is invalid.

        Returns:
            Cron expression string
        """
        if not self.storage_path.exists():
            return "0 9 * * *"

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                schedule = data.get("schedule", "0 9 * * *")
                return schedule if isinstance(schedule, str) else "0 9 * * *"
        except (json.JSONDecodeError, IOError):
            return "0 9 * * *"

    def set_schedule(self, cron_expr: str) -> bool:
        """
        Set and persist cron schedule with validation.

        Validates cron expression using croniter if available.
        If croniter is not available, performs basic format validation.

        Args:
            cron_expr: Cron expression string (5-field format)

        Returns:
            True if schedule was successfully set and persisted, False otherwise
        """
        # Basic validation: check if it has 5 fields
        fields = cron_expr.strip().split()
        if len(fields) != 5:
            return False

        # Validate with croniter if available
        if croniter is not None:
            try:
                croniter(cron_expr)
            except (ValueError, KeyError):
                return False

        # Persist to storage
        try:
            data = {"schedule": cron_expr}
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True
        except IOError:
            return False
