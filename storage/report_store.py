"""
Report storage and management.

Handles saving, retrieving, and listing analysis reports with versioning.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


class ReportStore:
    """Manages storage and retrieval of analysis reports."""

    def __init__(self, reports_dir: str) -> None:
        """
        Initialize ReportStore.

        Args:
            reports_dir: Directory path for storing reports

        Raises:
            OSError: If directory creation fails
        """
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def get_next_version(self) -> str:
        """
        Generate next version string based on existing reports.

        Returns version in format "YYYYMMDD_HH" (e.g., "20260306_02").
        Increments hour suffix if multiple reports exist for the same day.

        Returns:
            Version string in YYYYMMDD_HH format
        """
        now = datetime.now()
        date_prefix = now.strftime("%Y%m%d")

        # Find all existing reports for today
        existing_reports = sorted(self.reports_dir.glob("VoteFlux_Analysis_Report_*.html"))
        today_reports = [
            f for f in existing_reports if date_prefix in f.name
        ]

        if not today_reports:
            return f"{date_prefix}_00"

        # Extract hour suffix from existing reports
        hour_suffixes = []
        for report in today_reports:
            # Extract version from filename: VoteFlux_Analysis_Report_{version}.html
            parts = report.stem.split("_")
            if len(parts) >= 4:
                version_part = "_".join(parts[3:])  # Handle underscore in version
                if "_" in version_part:
                    hour_str = version_part.split("_")[-1]
                    try:
                        hour_suffixes.append(int(hour_str))
                    except ValueError:
                        pass

        if hour_suffixes:
            next_hour = max(hour_suffixes) + 1
            return f"{date_prefix}_{next_hour:02d}"

        return f"{date_prefix}_00"

    def save_report(self, content: str, version: str) -> Path:
        """
        Save report content to HTML file.

        Args:
            content: HTML content of the report
            version: Version string (e.g., "20260306_02")

        Returns:
            Path to saved report file

        Raises:
            IOError: If file writing fails
        """
        filename = f"VoteFlux_Analysis_Report_{version}.html"
        filepath = self.reports_dir / filename

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        except IOError as e:
            raise IOError(f"Failed to save report to {filepath}: {e}")

        return filepath

    def list_reports(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        List recent reports sorted by creation date (descending).

        Args:
            limit: Maximum number of reports to return

        Returns:
            List of report info dicts with keys:
            - version: Version string
            - filename: Filename
            - path: Full path
            - size: File size in bytes
            - created_at: Creation datetime
        """
        reports = []

        for filepath in sorted(
            self.reports_dir.glob("VoteFlux_Analysis_Report_*.html"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]:
            stat = filepath.stat()
            # Extract version from filename
            version = filepath.stem.replace("VoteFlux_Analysis_Report_", "")

            reports.append(
                {
                    "version": version,
                    "filename": filepath.name,
                    "path": str(filepath),
                    "size": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime),
                }
            )

        return reports

    def get_report_path(self, version: str) -> Optional[Path]:
        """
        Get path to a report by version.

        Args:
            version: Version string (e.g., "20260306_02")

        Returns:
            Path to report file if it exists, None otherwise
        """
        filename = f"VoteFlux_Analysis_Report_{version}.html"
        filepath = self.reports_dir / filename

        return filepath if filepath.exists() else None

    def get_recent_versions(self, count: int = 3) -> List[str]:
        """
        Get list of recent version strings for comparison.

        Args:
            count: Number of recent versions to return

        Returns:
            List of version strings sorted by creation date (descending)
        """
        reports = self.list_reports(limit=count)
        return [report["version"] for report in reports]
