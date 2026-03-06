"""WELL Building Standard compliance assessment engine."""

from datetime import datetime, timezone
from typing import Optional

from src.models.schemas import (
    ParameterData,
    WELLAssessment,
    ParameterAssessment,
)
from src.well.thresholds import (
    get_threshold_for_parameter,
    normalize_parameter_name,
    is_higher_better,
    is_range_based,
)


class WELLComplianceEngine:
    """Engine for assessing WELL Building Standard compliance."""

    def assess(
        self, device_name: str, parameters: list[ParameterData]
    ) -> WELLAssessment:
        """
        Assess WELL compliance for a set of parameters.

        Args:
            device_name: Name of the device being assessed
            parameters: List of parameter data with measurements

        Returns:
            Complete WELL assessment with scores and recommendations
        """
        assessments: list[ParameterAssessment] = []
        total_score = 0
        max_score = 0

        for param in parameters:
            if param.latest_value is None:
                continue

            assessment = self._assess_parameter(param)
            if assessment:
                assessments.append(assessment)
                total_score += assessment.score
                max_score += 4  # Max score per parameter

        # Calculate overall percentage and level
        percentage = (total_score / max_score * 100) if max_score > 0 else 0
        well_level = self._determine_well_level(percentage)

        # Generate recommendations
        recommendations = self._generate_recommendations(assessments)

        return WELLAssessment(
            device_name=device_name,
            timestamp=datetime.now(timezone.utc),
            overall_score=total_score,
            max_score=max_score,
            percentage=round(percentage, 1),
            well_level=well_level,
            parameters=assessments,
            recommendations=recommendations,
        )

    def _assess_parameter(self, param: ParameterData) -> Optional[ParameterAssessment]:
        """
        Assess a single parameter against WELL thresholds.

        Args:
            param: Parameter data with measurements

        Returns:
            Parameter assessment or None if no threshold exists
        """
        normalized_type = normalize_parameter_name(param.type)
        threshold = get_threshold_for_parameter(normalized_type)

        if not threshold:
            return None

        value = param.latest_value
        if value is None:
            return None

        # Determine score and level based on threshold type
        if is_range_based(normalized_type):
            score, level = self._assess_range_parameter(value, threshold)
        elif is_higher_better(normalized_type):
            score, level = self._assess_indicator_parameter(value, threshold)
        else:
            score, level = self._assess_pollutant_parameter(value, threshold)

        return ParameterAssessment(
            parameter=normalized_type,
            value=value,
            unit=param.unit,
            score=score,
            level=level,
            well_compliant=score >= 2,
            threshold_used=threshold.get("feature", "WELL v2"),
        )

    def _assess_pollutant_parameter(
        self, value: float, threshold: dict
    ) -> tuple[int, str]:
        """Assess a pollutant parameter (lower is better)."""
        if value <= threshold["excellent"]:
            return 4, "Excellent (WELL Platinum)"
        elif value <= threshold["good"]:
            return 3, "Good (WELL Gold)"
        elif value <= threshold["acceptable"]:
            return 2, "Acceptable (WELL Silver)"
        elif value <= threshold["poor"]:
            return 1, "Poor"
        else:
            return 0, "Very Poor"

    def _assess_indicator_parameter(
        self, value: float, threshold: dict
    ) -> tuple[int, str]:
        """Assess an indicator parameter (higher is better)."""
        if value >= threshold["excellent"]:
            return 4, "Excellent"
        elif value >= threshold["good"]:
            return 3, "Good"
        elif value >= threshold["acceptable"]:
            return 2, "Acceptable"
        elif value >= threshold["poor"]:
            return 1, "Poor"
        else:
            return 0, "Very Poor"

    def _assess_range_parameter(
        self, value: float, threshold: dict
    ) -> tuple[int, str]:
        """Assess a range-based parameter (optimal range)."""
        optimal_min = threshold["optimal_min"]
        optimal_max = threshold["optimal_max"]
        acceptable_min = threshold["acceptable_min"]
        acceptable_max = threshold["acceptable_max"]

        if optimal_min <= value <= optimal_max:
            return 4, "Excellent (WELL Platinum)"
        elif acceptable_min <= value <= acceptable_max:
            return 2, "Acceptable"
        else:
            return 0, "Out of Range"

    def _determine_well_level(self, percentage: float) -> str:
        """Determine WELL certification level based on percentage score."""
        if percentage >= 90:
            return "WELL Platinum Eligible"
        elif percentage >= 75:
            return "WELL Gold Eligible"
        elif percentage >= 60:
            return "WELL Silver Eligible"
        elif percentage >= 40:
            return "WELL Bronze Eligible"
        else:
            return "Below WELL Standards"

    def _generate_recommendations(
        self, assessments: list[ParameterAssessment]
    ) -> list[str]:
        """Generate actionable, parameter-specific recommendations."""
        from src.well.features import WELL_FEATURES, get_feature_for_parameter
        from src.well.thresholds import get_threshold_for_parameter

        recommendations = []

        for assessment in assessments:
            if assessment.score <= 1:
                # Critical: Get feature-specific mitigation strategies
                feature_ids = get_feature_for_parameter(assessment.parameter)

                rec = f"🔴 **PRIORITY: {assessment.parameter.upper()}** is {assessment.level}\n"
                rec += f"   Current value: {assessment.value} {assessment.unit}\n"

                for feature_id in feature_ids:
                    if feature_id in WELL_FEATURES:
                        feature = WELL_FEATURES[feature_id]
                        rec += f"   **{feature.id} - {feature.name}**:\n"
                        for strategy in feature.mitigation_strategies[:2]:  # Top 2 strategies
                            rec += f"   • {strategy}\n"

                recommendations.append(rec)

            elif assessment.score == 2:
                # Moderate: Suggest next tier target
                rec = f"🟡 **{assessment.parameter.upper()}** is acceptable but could be improved\n"
                rec += f"   Current value: {assessment.value} {assessment.unit}\n"

                threshold = get_threshold_for_parameter(assessment.parameter)
                if threshold and "good" in threshold:
                    target = threshold["good"]
                    rec += f"   Target for 'Good' level: {target} {assessment.unit}\n"

                recommendations.append(rec)

        if not recommendations:
            recommendations.append(
                "✅ All parameters are within excellent or good ranges. "
                "Maintain current conditions for WELL compliance."
            )

        return recommendations

