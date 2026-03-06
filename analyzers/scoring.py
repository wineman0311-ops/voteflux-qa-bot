"""
Scoring engine for prediction market platform analysis.

Provides rule-based scoring across 4 dimensions:
- 市場多樣性 (Market Variety)
- 功能特色 (Features)
- UI 設計 (UI Design)
- UX 體驗 (UX Experience)
"""

from typing import Dict, List, Any
from config.platforms import PlatformData


class ScoringEngine:
    """Rule-based scoring engine for platform dimensions."""

    # Market variety scoring thresholds
    MARKET_COUNT_THRESHOLDS = {
        1000: 10,  # >= 1000 markets = 10 points
        500: 9,
        200: 8,
        100: 7,
        50: 6,
        20: 5,
        10: 4,
        0: 2,
    }

    # Category count scoring
    CATEGORY_COUNT_THRESHOLDS = {
        50: 10,  # >= 50 categories = 10 points
        30: 9,
        15: 8,
        10: 7,
        5: 6,
        3: 4,
        1: 2,
        0: 1,
    }

    # Features count scoring
    FEATURES_COUNT_THRESHOLDS = {
        15: 10,  # >= 15 features = 10 points
        12: 9,
        10: 8,
        8: 7,
        6: 6,
        4: 5,
        2: 3,
        1: 2,
        0: 1,
    }

    def score_platform(self, platform: PlatformData) -> Dict[str, float]:
        """
        Score a single platform across 4 dimensions.

        Args:
            platform: PlatformData instance to score

        Returns:
            Dictionary with scores for each dimension and total:
            {
                'market_variety': float,      # 1-10
                'features': float,             # 1-10
                'ui_design': float,            # 1-10
                'ux_experience': float,        # 1-10
                'total': float                 # average of 4 dimensions
            }
        """
        scores = {
            "market_variety": self._score_market_variety(platform),
            "features": self._score_features(platform),
            "ui_design": self._score_ui_design(platform),
            "ux_experience": self._score_ux_experience(platform),
        }

        scores["total"] = round(sum(scores.values()) / 4, 2)

        return scores

    def score_all(self, platforms: List[PlatformData]) -> Dict[str, Any]:
        """
        Score all platforms and return comprehensive scoring matrix.

        Args:
            platforms: List of PlatformData instances

        Returns:
            Dictionary with platform scores:
            {
                'platform_id': {
                    'market_variety': float,
                    'features': float,
                    'ui_design': float,
                    'ux_experience': float,
                    'total': float
                },
                ...
            }
        """
        scores = {}

        for platform in platforms:
            if platform.status == "success":
                scores[platform.id] = self.score_platform(platform)
            else:
                # Failed scrapes get 0 across board
                scores[platform.id] = {
                    "market_variety": 0.0,
                    "features": 0.0,
                    "ui_design": 0.0,
                    "ux_experience": 0.0,
                    "total": 0.0,
                }

        return scores

    def _score_market_variety(self, platform: PlatformData) -> float:
        """
        Score market variety based on count and category diversity.

        Factors:
        - Market count (40%)
        - Category count (40%)
        - Category diversity (20%)
        """
        market_score = self._threshold_score(
            platform.market_count, self.MARKET_COUNT_THRESHOLDS
        )

        category_score = self._threshold_score(
            platform.category_count, self.CATEGORY_COUNT_THRESHOLDS
        )

        # Category diversity: how well distributed markets are across categories
        diversity_score = 10.0
        if platform.categories and platform.market_count > 0:
            total_categorized = sum(cat.count for cat in platform.categories)
            if total_categorized > 0:
                avg_per_category = total_categorized / len(platform.categories)
                # Measure uniformity: lower std dev = higher diversity
                variance = sum(
                    (cat.count - avg_per_category) ** 2
                    for cat in platform.categories
                ) / len(platform.categories)
                std_dev = variance ** 0.5
                # Higher std dev = less diverse, reduce score
                diversity_score = max(1, 10 - (std_dev / avg_per_category if avg_per_category > 0 else 0) * 5)

        return round(market_score * 0.4 + category_score * 0.4 + diversity_score * 0.2, 2)

    def _score_features(self, platform: PlatformData) -> float:
        """
        Score features based on count and richness.

        Factors:
        - Feature count (70%)
        - Unique features bonus (30%)
        """
        feature_score = self._threshold_score(
            len(platform.features), self.FEATURES_COUNT_THRESHOLDS
        )

        # Bonus for having diverse/interesting features
        unique_bonus = 0
        if platform.features:
            # Check for premium features
            premium_keywords = [
                "api",
                "native app",
                "複雜市場",
                "conditional",
                "portfolio",
                "advanced",
                "real-time",
            ]
            premium_count = sum(
                1
                for feature in platform.features
                if any(kw in feature.lower() for kw in premium_keywords)
            )
            unique_bonus = min(10, premium_count * 1.5)

        return round(feature_score * 0.7 + unique_bonus * 0.3, 2)

    def _score_ui_design(self, platform: PlatformData) -> float:
        """
        Score UI design based on ui_notes content analysis.

        Analyzes ui_notes for mentions of:
        - Modern/clean design
        - Responsive layout
        - Accessibility issues
        - Visual polish
        """
        if not platform.ui_notes:
            return 5.0  # Neutral if no data

        notes_lower = platform.ui_notes.lower()
        score = 5.0

        # Positive indicators
        positive_keywords = [
            "modern",
            "clean",
            "responsive",
            "intuitive",
            "polish",
            "elegant",
            "sleek",
            "professional",
            "好看",
            "精美",
            "現代",
        ]
        positive_count = sum(1 for kw in positive_keywords if kw in notes_lower)
        score += positive_count * 0.8

        # Negative indicators
        negative_keywords = [
            "cluttered",
            "confusing",
            "outdated",
            "dated",
            "ugly",
            "clunky",
            "amateur",
            "混亂",
            "過時",
            "醜陋",
        ]
        negative_count = sum(1 for kw in negative_keywords if kw in notes_lower)
        score -= negative_count * 1.0

        return round(max(1, min(10, score)), 2)

    def _score_ux_experience(self, platform: PlatformData) -> float:
        """
        Score UX experience based on ux_notes and accessibility.

        Analyzes:
        - Navigation ease
        - Login wall/friction
        - Performance notes
        - User flow clarity
        """
        if not platform.ux_notes:
            return 5.0  # Neutral if no data

        notes_lower = platform.ux_notes.lower()
        score = 5.0

        # Positive indicators
        positive_keywords = [
            "easy",
            "smooth",
            "seamless",
            "intuitive",
            "quick",
            "fast",
            "user-friendly",
            "accessible",
            "簡單",
            "流暢",
            "易用",
            "快速",
        ]
        positive_count = sum(1 for kw in positive_keywords if kw in notes_lower)
        score += positive_count * 0.7

        # Negative indicators (login wall, friction)
        friction_keywords = [
            "login wall",
            "paywall",
            "signup required",
            "slow",
            "laggy",
            "confusing flow",
            "navigation issues",
            "登入牆",
            "付費牆",
            "緩慢",
        ]
        friction_count = sum(1 for kw in friction_keywords if kw in notes_lower)
        score -= friction_count * 1.5

        return round(max(1, min(10, score)), 2)

    @staticmethod
    def _threshold_score(value: int, thresholds: Dict[int, float]) -> float:
        """
        Score a value based on threshold mapping.

        Args:
            value: The value to score
            thresholds: Dict mapping threshold to score (highest threshold first)

        Returns:
            Score between 1-10
        """
        # Sort thresholds descending
        sorted_thresholds = sorted(thresholds.items(), key=lambda x: x[0], reverse=True)

        for threshold, score in sorted_thresholds:
            if value >= threshold:
                return float(score)

        # Default to 1 if below all thresholds
        return 1.0
