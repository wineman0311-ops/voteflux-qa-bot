"""
Analysis orchestrator for coordinating all analysis components.

Runs scrapers, calculates scores, compares versions, and generates alerts/recommendations.
"""

import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from config.platforms import AnalysisResult, PlatformData, CountryNews
from config.settings import COUNTRIES, REPORTS_DIR, PLATFORM_STORE_PATH
from storage.platform_store import PlatformStore
from analyzers.scoring import ScoringEngine
from analyzers.version_comparer import VersionComparer


class AnalysisOrchestrator:
    """Orchestrates the complete analysis workflow."""

    def __init__(self, reports_dir: str = REPORTS_DIR, version: str = ""):
        """
        Initialize the orchestrator.

        Args:
            reports_dir: Directory to save reports
            version: Version identifier for this run
        """
        self.reports_dir = reports_dir
        self.version = version or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.scoring_engine = ScoringEngine()
        self.version_comparer = VersionComparer(reports_dir)

    def run_analysis(
        self,
        platforms_data: List[PlatformData],
        countries_data: List[CountryNews],
    ) -> AnalysisResult:
        """
        Run complete analysis on collected data.

        Args:
            platforms_data: List of scraped platform data
            countries_data: List of scraped country news data

        Returns:
            Complete AnalysisResult with scores, alerts, and recommendations
        """
        # Calculate scores
        scores = self.scoring_engine.score_all(platforms_data)

        # Get comparison with previous versions
        previous_versions = self.version_comparer.get_latest_versions(limit=2)

        # Generate alerts
        alerts = self._generate_alerts(platforms_data, scores)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            platforms_data, scores, countries_data
        )

        # Build result
        result = AnalysisResult(
            version=self.version,
            date=datetime.now(),
            platforms=platforms_data,
            countries=countries_data,
            scores=scores,
            alerts=alerts,
            recommendations=recommendations,
        )

        return result

    def _generate_alerts(
        self, platforms: List[PlatformData], scores: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """
        Generate alert items based on analysis findings.

        Args:
            platforms: List of platform data
            scores: Scoring results

        Returns:
            List of alert dicts with type, title, description
        """
        alerts = []

        # Count successful scrapers
        successful = sum(1 for p in platforms if p.status == "success")
        total = len(platforms)

        if successful == total:
            alerts.append(
                {
                    "type": "success",
                    "title": "爬蟲狀態正常",
                    "description": f"全部 {total} 個平台成功爬取資料",
                }
            )
        elif successful > 0:
            alerts.append(
                {
                    "type": "warning",
                    "title": "部分爬蟲失敗",
                    "description": f"成功: {successful}/{total}, 失敗: {total - successful}",
                }
            )
        else:
            alerts.append(
                {
                    "type": "danger",
                    "title": "爬蟲全部失敗",
                    "description": "無法獲取任何平台資料",
                }
            )

        # Check VoteFlux specifically
        voteflux = next((p for p in platforms if p.id == "voteflux"), None)
        if voteflux:
            if voteflux.status == "success":
                alerts.append(
                    {
                        "type": "success",
                        "title": "VoteFlux 數據完整",
                        "description": f"VoteFlux 市場數: {voteflux.market_count}, 分類數: {voteflux.category_count}",
                    }
                )
            else:
                alerts.append(
                    {
                        "type": "danger",
                        "title": "VoteFlux 爬蟲失敗",
                        "description": f"錯誤: {voteflux.error_msg or '未知錯誤'}",
                    }
                )

        # Check for login wall issues
        login_wall_platforms = [
            p for p in platforms if p.ux_notes and "login wall" in p.ux_notes.lower()
        ]
        if login_wall_platforms:
            platform_names = ", ".join(p.name for p in login_wall_platforms)
            alerts.append(
                {
                    "type": "warning",
                    "title": "登入牆阻擋",
                    "description": f"{platform_names} 有登入牆限制",
                }
            )

        # Check for exceptional scores
        if scores:
            high_performers = [
                (pid, s["total"])
                for pid, s in scores.items()
                if s.get("total", 0) >= 8.5
            ]
            if high_performers:
                top = max(high_performers, key=lambda x: x[1])
                platform = next(
                    (p for p in platforms if p.id == top[0]), None
                )
                if platform:
                    alerts.append(
                        {
                            "type": "info",
                            "title": "優秀平台",
                            "description": f"{platform.name} 總分 {top[1]}/10，表現卓越",
                        }
                    )

        return alerts

    def _generate_recommendations(
        self,
        platforms: List[PlatformData],
        scores: Dict[str, Any],
        countries: List[CountryNews],
    ) -> List[Dict[str, Any]]:
        """
        Generate actionable recommendations.

        Args:
            platforms: List of platform data
            scores: Scoring results
            countries: List of country news data

        Returns:
            List of recommendation dicts with priority, title, actions
        """
        recommendations = []

        # P0: Critical issues
        critical_platforms = [
            p for p in platforms if p.status == "error"
        ]
        if critical_platforms:
            recommendations.append(
                {
                    "priority": "P0",
                    "title": "修復爬蟲故障",
                    "actions": [
                        f"檢查 {p.name} 連接問題: {p.error_msg}"
                        for p in critical_platforms
                    ],
                }
            )

        # P0: VoteFlux specific
        voteflux = next((p for p in platforms if p.id == "voteflux"), None)
        if voteflux and voteflux.status == "success":
            if voteflux.market_count < 50:
                recommendations.append(
                    {
                        "priority": "P0",
                        "title": "VoteFlux 市場數不足",
                        "actions": [
                            "當前僅 {} 個市場，檢查資料完整性".format(
                                voteflux.market_count
                            ),
                            "檢查是否新增市場分類",
                            "驗證資料庫連接",
                        ],
                    }
                )

        # P1: Performance improvements
        low_performers = [
            (pid, s)
            for pid, s in scores.items()
            if s.get("total", 0) < 4.0
        ]
        if low_performers:
            recommendations.append(
                {
                    "priority": "P1",
                    "title": "改進低評分平台",
                    "actions": [
                        f"改進 {next((p.name for p in platforms if p.id == pid), pid)} 的"
                        + (
                            " UI 設計"
                            if s.get("ui_design", 0) < s.get("features", 0)
                            else " 功能特色"
                        )
                        for pid, s in low_performers[:2]
                    ],
                }
            )

        # P1: Feature expansion opportunities
        feature_gaps = [
            p
            for p in platforms
            if p.status == "success" and len(p.features) < 5
        ]
        if feature_gaps:
            recommendations.append(
                {
                    "priority": "P1",
                    "title": "擴展平台功能",
                    "actions": [
                        f"為 {p.name} 新增高級功能（API, 複雜市場等）"
                        for p in feature_gaps[:2]
                    ],
                }
            )

        # P2: Monitoring & documentation
        recommendations.append(
            {
                "priority": "P2",
                "title": "定期監控與更新",
                "actions": [
                    "每週檢查競品市場數量變化",
                    "跟蹤新興市場趨勢",
                    "更新UI/UX評估標準",
                ],
            }
        )

        # P2: News-based market opportunities
        if countries:
            hot_countries = [
                c for c in countries if len(c.news_items) > 0
            ]
            if hot_countries:
                country_names = ", ".join(
                    c.name for c in hot_countries[:2]
                )
                recommendations.append(
                    {
                        "priority": "P2",
                        "title": "基於新聞的市場機會",
                        "actions": [
                            f"在 {country_names} 新聞基礎上設計市場",
                            "利用熱點事件創建時效性市場",
                        ],
                    }
                )

        return recommendations

    def save_result_json(self, result: AnalysisResult) -> str:
        """
        Save analysis result as JSON.

        Args:
            result: AnalysisResult to save

        Returns:
            Path to saved JSON file
        """
        reports_path = Path(self.reports_dir)
        reports_path.mkdir(parents=True, exist_ok=True)

        filepath = reports_path / f"{self.version}.json"

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)

        return str(filepath)

    def load_result_json(self, filepath: str) -> Optional[AnalysisResult]:
        """
        Load analysis result from JSON.

        Args:
            filepath: Path to JSON file

        Returns:
            AnalysisResult or None if load fails
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Reconstruct AnalysisResult from dict
            # (Implementation would depend on JSON structure)
            return None  # TODO: Implement deserialization
        except Exception as e:
            return None
