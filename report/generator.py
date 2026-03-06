"""
HTML report generator for analysis results.

Uses Jinja2 to render professional reports with analysis data.
"""

import os
from pathlib import Path
from typing import Optional
from datetime import datetime

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:
    raise ImportError(
        "Jinja2 is required for report generation. Install with: pip install Jinja2"
    )

from config.platforms import AnalysisResult


class ReportGenerator:
    """Generates self-contained HTML reports from analysis results."""

    def __init__(self, template_dir: Optional[str] = None):
        """
        Initialize the report generator.

        Args:
            template_dir: Directory containing Jinja2 templates.
                         Defaults to same directory as this module.
        """
        if template_dir is None:
            template_dir = Path(__file__).parent

        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def generate(self, result: AnalysisResult) -> str:
        """
        Generate a complete self-contained HTML report.

        Args:
            result: AnalysisResult object with all analysis data

        Returns:
            Complete HTML string ready for saving/display

        Raises:
            FileNotFoundError: If template.html not found
            Exception: If Jinja2 rendering fails
        """
        try:
            template = self.env.get_template("template.html")
        except Exception as e:
            raise FileNotFoundError(
                f"Could not load template.html: {str(e)}"
            ) from e

        # Prepare context data for template
        context = self._prepare_context(result)

        try:
            html = template.render(**context)
            return html
        except Exception as e:
            raise Exception(f"Failed to render template: {str(e)}") from e

    def save_report(
        self, result: AnalysisResult, filepath: str
    ) -> str:
        """
        Generate and save report to file.

        Args:
            result: AnalysisResult object
            filepath: Path where report should be saved

        Returns:
            Path to saved report file
        """
        html = self.generate(result)

        # Create directory if needed
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        return filepath

    def _prepare_context(self, result: AnalysisResult) -> dict:
        """
        Prepare template context from analysis result.

        Args:
            result: AnalysisResult object

        Returns:
            Dictionary with all data for template rendering
        """
        # Calculate statistics
        successful_platforms = [
            p for p in result.platforms if p.status == "success"
        ]

        total_markets = sum(p.market_count for p in successful_platforms)
        total_categories = sum(p.category_count for p in successful_platforms)

        # Prepare platform cards
        platform_cards = []
        for platform in result.platforms:
            card = {
                "id": platform.id,
                "name": platform.name,
                "url": platform.url,
                "role": platform.role,
                "status": platform.status,
                "market_count": platform.market_count,
                "category_count": platform.category_count,
                "features": platform.features,
                "top_markets": platform.top_markets,
                "trading_volume_info": platform.trading_volume_info,
                "ui_notes": platform.ui_notes,
                "ux_notes": platform.ux_notes,
                "error_msg": platform.error_msg,
                "score": result.scores.get(platform.id, {}).get("total", 0),
            }
            platform_cards.append(card)

        # Prepare scoring matrix
        scoring_matrix = []
        for platform in result.platforms:
            if platform.id in result.scores:
                scores = result.scores[platform.id]
                row = {
                    "platform": platform.name,
                    "market_variety": scores.get("market_variety", 0),
                    "features": scores.get("features", 0),
                    "ui_design": scores.get("ui_design", 0),
                    "ux_experience": scores.get("ux_experience", 0),
                    "total": scores.get("total", 0),
                }
                scoring_matrix.append(row)

        # Prepare VoteFlux deep dive data
        voteflux_platform = next(
            (p for p in result.platforms if p.id == "voteflux"), None
        )

        voteflux_data = {}
        if voteflux_platform and voteflux_platform.status == "success":
            # Category breakdown
            category_breakdown = [
                {
                    "name": cat.name,
                    "count": cat.count,
                    "percentage": (
                        f"{cat.count / voteflux_platform.market_count * 100:.1f}%"
                        if voteflux_platform.market_count > 0
                        else "0%"
                    ),
                }
                for cat in voteflux_platform.categories
            ]

            # Cross-platform volume comparison
            volume_comparison = []
            for platform in successful_platforms:
                volume_comparison.append(
                    {
                        "name": platform.name,
                        "markets": platform.market_count,
                        "volume": platform.trading_volume_info or "N/A",
                    }
                )

            voteflux_data = {
                "market_count": voteflux_platform.market_count,
                "category_count": voteflux_platform.category_count,
                "live_market_count": voteflux_platform.live_market_count,
                "categories": category_breakdown,
                "top_markets": voteflux_platform.top_markets,
                "volume_comparison": volume_comparison,
            }

        # Prepare country news cards
        country_cards = []
        for country in result.countries:
            card = {
                "flag": country.flag,
                "name": country.name,
                "name_en": country.name_en,
                "news_items": country.news_items[:3],  # Top 3 news
                "suggested_markets": country.suggested_markets[:3],  # Top 3 markets
            }
            country_cards.append(card)

        # Prepare recommendations grouped by priority
        recommendations_by_priority = {
            "P0": [],
            "P1": [],
            "P2": [],
        }
        for rec in result.recommendations:
            priority = rec.get("priority", "P2")
            recommendations_by_priority[priority].append(rec)

        return {
            "version": result.version,
            "date": result.date.strftime("%Y-%m-%d %H:%M:%S"),
            "date_short": result.date.strftime("%Y-%m-%d"),
            "platforms": platform_cards,
            "countries": country_cards,
            "alerts": result.alerts,
            "recommendations": result.recommendations,
            "recommendations_by_priority": recommendations_by_priority,
            "scores": result.scores,
            "scoring_matrix": scoring_matrix,
            "statistics": {
                "total_platforms": len(result.platforms),
                "successful_platforms": len(successful_platforms),
                "total_markets": total_markets,
                "total_categories": total_categories,
                "total_countries": len(result.countries),
            },
            "voteflux": voteflux_data,
        }

    @staticmethod
    def get_score_color(score: float) -> str:
        """
        Get CSS color class for a score.

        Args:
            score: Score value (1-10)

        Returns:
            CSS class name
        """
        if score >= 8:
            return "score-high"
        elif score >= 6:
            return "score-medium"
        else:
            return "score-low"

    @staticmethod
    def get_suitability_badge_color(suitability: str) -> str:
        """
        Get CSS color for suitability level.

        Args:
            suitability: Suitability level (high/medium/low)

        Returns:
            CSS class name
        """
        suitability_lower = suitability.lower()
        if "high" in suitability_lower or "高" in suitability:
            return "badge-success"
        elif "medium" in suitability_lower or "中" in suitability:
            return "badge-warning"
        else:
            return "badge-danger"
