"""
Version comparison module for tracking metric changes across analysis runs.

Compares current results with previous versions to identify trends and anomalies.
"""

import os
import re
from typing import Dict, List, Any, Optional
from pathlib import Path
from config.platforms import AnalysisResult


class VersionComparer:
    """Compares current analysis results with previous versions."""

    def __init__(self, reports_dir: str):
        """
        Initialize the version comparer.

        Args:
            reports_dir: Directory containing saved HTML reports
        """
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def compare_versions(
        self, current: AnalysisResult, previous_versions: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Compare current analysis with previous versions.

        Args:
            current: Current AnalysisResult
            previous_versions: List of previous version strings (filenames or version IDs)

        Returns:
            List of comparison items:
            [
                {
                    'item': str,                    # e.g., "Total Markets"
                    'current': str,                 # Current value
                    'values': {version: str},       # Previous values
                    'status': str,                  # Status icon
                    'trend': 'up'|'down'|'stable'
                },
                ...
            ]
        """
        comparison = []

        # Extract metrics from current
        current_metrics = self._extract_metrics_from_result(current)

        # Extract metrics from previous versions
        previous_metrics_list = []
        for version_id in previous_versions:
            filepath = self.reports_dir / f"{version_id}.html"
            if filepath.exists():
                metrics = self._extract_metrics_from_html(str(filepath))
                previous_metrics_list.append((version_id, metrics))

        # Build comparison table
        # Key metrics to compare
        key_metrics = [
            ("total_markets", "總市場數"),
            ("total_categories", "總分類數"),
            ("voteflux_markets", "VoteFlux 市場數"),
            ("avg_platform_score", "平均平台評分"),
            ("success_scrapers", "成功爬蟲數"),
        ]

        for metric_key, metric_label in key_metrics:
            current_value = current_metrics.get(metric_key, "N/A")
            row = {
                "item": metric_label,
                "current": current_value,
                "values": {},
                "status": "➡ 維持",
                "trend": "stable",
            }

            if previous_metrics_list:
                # Add previous values
                for version_id, metrics in previous_metrics_list:
                    row["values"][version_id] = metrics.get(metric_key, "N/A")

                # Determine trend (comparing current vs first previous)
                if previous_metrics_list:
                    prev_version_id, prev_metrics = previous_metrics_list[0]
                    prev_value = prev_metrics.get(metric_key, 0)
                    curr_val = (
                        current_value
                        if isinstance(current_value, (int, float))
                        else 0
                    )

                    if isinstance(prev_value, (int, float)) and isinstance(
                        curr_val, (int, float)
                    ):
                        if curr_val > prev_value:
                            row["status"] = "▲ 增長"
                            row["trend"] = "up"
                        elif curr_val < prev_value:
                            row["status"] = "▼ 下降"
                            row["trend"] = "down"
                        else:
                            row["status"] = "➡ 維持"
                            row["trend"] = "stable"
                    else:
                        row["status"] = "❓ 無法比較"
                        row["trend"] = "unknown"

            comparison.append(row)

        return comparison

    def extract_metrics_from_html(self, filepath: str) -> Dict[str, Any]:
        """
        Extract key metrics from a saved HTML report.

        Uses regex to find data in the HTML structure.

        Args:
            filepath: Path to HTML report

        Returns:
            Dictionary of extracted metrics
        """
        return self._extract_metrics_from_html(filepath)

    def _extract_metrics_from_html(self, filepath: str) -> Dict[str, Any]:
        """
        Extract key metrics from HTML report using regex patterns.

        Args:
            filepath: Path to HTML file

        Returns:
            Dictionary of metrics
        """
        metrics = {}

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            # Pattern: look for data in common HTML structures
            # Total markets pattern
            market_match = re.search(r"總市場.*?(\d+)", content)
            if market_match:
                metrics["total_markets"] = int(market_match.group(1))

            # Total categories pattern
            category_match = re.search(r"總分類.*?(\d+)", content)
            if category_match:
                metrics["total_categories"] = int(category_match.group(1))

            # VoteFlux markets pattern
            vf_match = re.search(r"VoteFlux.*?(\d+)", content)
            if vf_match:
                metrics["voteflux_markets"] = int(vf_match.group(1))

            # Average score pattern
            avg_match = re.search(r"平均.*?[\d.]+", content)
            if avg_match:
                try:
                    score_str = re.search(r"[\d.]+", avg_match.group()).group()
                    metrics["avg_platform_score"] = float(score_str)
                except (ValueError, AttributeError):
                    pass

            # Success scrapers count
            success_match = re.search(r"成功.*?(\d+)", content)
            if success_match:
                metrics["success_scrapers"] = int(success_match.group(1))

        except Exception as e:
            # Return empty dict if extraction fails
            pass

        return metrics

    def _extract_metrics_from_result(
        self, result: AnalysisResult
    ) -> Dict[str, Any]:
        """
        Extract metrics from AnalysisResult object.

        Args:
            result: AnalysisResult instance

        Returns:
            Dictionary of metrics
        """
        metrics = {}

        # Total markets across all platforms
        total_markets = sum(p.market_count for p in result.platforms)
        metrics["total_markets"] = total_markets

        # Total categories
        total_categories = sum(p.category_count for p in result.platforms)
        metrics["total_categories"] = total_categories

        # VoteFlux specific
        voteflux_platform = next(
            (p for p in result.platforms if p.id == "voteflux"), None
        )
        if voteflux_platform:
            metrics["voteflux_markets"] = voteflux_platform.market_count

        # Average platform score
        if result.scores:
            total_scores = [s.get("total", 0) for s in result.scores.values()]
            if total_scores:
                metrics["avg_platform_score"] = round(
                    sum(total_scores) / len(total_scores), 2
                )

        # Success scrapers
        success_count = sum(
            1 for p in result.platforms if p.status == "success"
        )
        metrics["success_scrapers"] = success_count

        return metrics

    def get_latest_versions(self, limit: int = 3) -> List[str]:
        """
        Get the most recent version files.

        Args:
            limit: Number of versions to return

        Returns:
            List of version filenames (most recent first)
        """
        if not self.reports_dir.exists():
            return []

        html_files = sorted(
            self.reports_dir.glob("*.html"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )

        return [f.stem for f in html_files[:limit]]
