"""Compliance tools for WELL Building Standard assessment."""

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from src.api.inbiot import InBiotClient, InBiotAPIError
from src.models.schemas import DeviceConfig
from src.well.compliance import WELLComplianceEngine
from src.well.thresholds import get_threshold_for_parameter, is_range_based, is_higher_better
from src.utils.provenance import (
    generate_provenance,
    create_data_unavailable_error,
)


def register_compliance_tools(
    mcp: FastMCP,
    devices: dict[str, DeviceConfig],
    inbiot_client: InBiotClient,
    well_engine: WELLComplianceEngine,
):
    """Register compliance tools with the MCP server."""

    @mcp.tool()
    async def well_compliance_check(
        device: Annotated[str, Field(description="Device ID to check WELL compliance for")]
    ) -> str:
        """
        Assess WELL Building Standard compliance for an InBiot device.

        Evaluates current air quality against WELL v2, ASHRAE 62.1/55, and WHO Indoor
        standards. Returns certification level eligibility and parameter-by-parameter assessment.
        """
        if device not in devices:
            return f"Unknown device: {device}. Use list_devices to see available options."

        device_config = devices[device]
        endpoint = f"/last-measurements/{device_config.api_key}/{device_config.system_id}"

        try:
            data = await inbiot_client.get_latest_measurements(device_config)
            assessment = well_engine.assess(device_config.name, data)

            # Format results
            result = f"## WELL Compliance Assessment: {device_config.name}\n\n"
            result += f"### Overall Score: {assessment.overall_score}/{assessment.max_score} ({assessment.percentage}%)\n"
            result += f"### Certification Level: **{assessment.well_level}**\n\n"

            result += "### Parameter Assessment\n\n"
            result += "| Parameter | Value | Level | WELL Compliant |\n"
            result += "|-----------|-------|-------|----------------|\n"

            for param in assessment.parameters:
                compliant = "✅" if param.well_compliant else "❌"
                result += f"| {param.parameter} | {param.value} {param.unit} | {param.level} | {compliant} |\n"

            result += "\n### Recommendations\n\n"
            for rec in assessment.recommendations:
                result += f"- {rec}\n"

            # Add provenance
            result += generate_provenance(
                device_name=device_config.name,
                device_api_key=device_config.api_key,
                endpoint=endpoint,
                data=data,
                analysis_type="WELL Compliance Assessment",
            )

            return result

        except InBiotAPIError as e:
            return create_data_unavailable_error(
                device_name=device_config.name,
                error_message=e.message,
                endpoint=endpoint,
            )

    @mcp.tool()
    async def well_feature_compliance(
        device: Annotated[str, Field(description="Device ID for WELL feature analysis")]
    ) -> str:
        """
        Get WELL Building Standard compliance broken down by individual features (A01-A08, T01-T07).

        Shows compliance status for each WELL v2 feature with specific scores and
        recommendations. More detailed than standard compliance check.
        """
        if device not in devices:
            return f"Unknown device: {device}. Use list_devices to see available options."

        device_config = devices[device]

        try:
            from src.well.features import WELL_FEATURES
            from src.well.thresholds import normalize_parameter_name

            data = await inbiot_client.get_latest_measurements(device_config)

            # Group parameters by feature
            feature_data = {}
            for feature_id, feature in WELL_FEATURES.items():
                feature_params = []
                for param in data:
                    if normalize_parameter_name(param.type) in feature.parameters:
                        feature_params.append(param)

                if feature_params:
                    # Assess parameters for this feature
                    assessments = []
                    total_score = 0
                    max_score = 0

                    for param in feature_params:
                        assessment = well_engine._assess_parameter(param)
                        if assessment:
                            assessments.append(assessment)
                            total_score += assessment.score
                            max_score += 4

                    percentage = (total_score / max_score * 100) if max_score > 0 else 0

                    feature_data[feature_id] = {
                        "feature": feature,
                        "score": total_score,
                        "max_score": max_score,
                        "percentage": round(percentage, 1),
                        "level": well_engine._determine_well_level(percentage),
                        "compliant": percentage >= 50,
                        "assessments": assessments,
                    }

            # Format results
            result = f"## WELL Feature Compliance: {device_config.name}\n\n"

            # Air quality features
            result += "### Air Quality Features (A01-A08)\n\n"
            result += "| Feature | Name | Score | Level | Status |\n"
            result += "|---------|------|-------|-------|--------|\n"

            for feature_id in ["A01", "A03", "A05", "A06", "A08"]:
                if feature_id in feature_data:
                    fd = feature_data[feature_id]
                    status = "✅" if fd["compliant"] else "❌"
                    result += f"| {feature_id} | {fd['feature'].name} | {fd['score']}/{fd['max_score']} | {fd['level']} | {status} |\n"

            # Thermal comfort features
            result += "\n### Thermal Comfort Features (T01-T07)\n\n"
            result += "| Feature | Name | Score | Level | Status |\n"
            result += "|---------|------|-------|-------|--------|\n"

            for feature_id in ["T01", "T06", "T07"]:
                if feature_id in feature_data:
                    fd = feature_data[feature_id]
                    status = "✅" if fd["compliant"] else "❌"
                    result += f"| {feature_id} | {fd['feature'].name} | {fd['score']}/{fd['max_score']} | {fd['level']} | {status} |\n"

            # Feature-specific recommendations
            result += "\n### Feature-Specific Recommendations\n\n"

            for feature_id, fd in feature_data.items():
                if not fd["compliant"]:
                    result += f"**{feature_id} - {fd['feature'].name}** ({fd['percentage']:.0f}% compliant)\n"
                    result += f"- Health Impact: {fd['feature'].health_impact}\n"
                    result += "- Actions:\n"
                    for strategy in fd['feature'].mitigation_strategies[:3]:
                        result += f"  • {strategy}\n"
                    result += "\n"

            if all(fd["compliant"] for fd in feature_data.values()):
                result += "✅ All monitored features are compliant. Excellent performance!\n"

            return result

        except InBiotAPIError as e:
            return create_data_unavailable_error(
                device_name=device_config.name,
                error_message=e.message,
            )

    @mcp.tool()
    async def health_recommendations(
        device: Annotated[str, Field(description="Device ID to generate recommendations for")]
    ) -> str:
        """
        Generate health and comfort recommendations based on current air quality.

        Provides actionable advice for building managers and occupants based on
        current sensor readings and WELL Building Standard guidelines.
        """
        if device not in devices:
            return f"Unknown device: {device}. Use list_devices to see available options."

        device_config = devices[device]

        try:
            data = await inbiot_client.get_latest_measurements(device_config)
            assessment = well_engine.assess(device_config.name, data)

            result = f"## Health Recommendations: {device_config.name}\n\n"

            # Overall status
            if assessment.percentage >= 75:
                result += "### Overall Status: ✅ Good\n\n"
                result += "Air quality conditions are favorable for occupant health and productivity.\n\n"
            elif assessment.percentage >= 50:
                result += "### Overall Status: ⚠️ Moderate\n\n"
                result += "Some parameters need attention. Review recommendations below.\n\n"
            else:
                result += "### Overall Status: ❌ Needs Improvement\n\n"
                result += "Multiple air quality issues detected. Immediate action recommended.\n\n"

            # Specific recommendations with context-aware targets
            result += "### Specific Recommendations\n\n"

            for param in assessment.parameters:
                if param.score <= 1:
                    result += f"**🔴 {param.parameter.upper()}** ({param.value} {param.unit})\n"
                    result += f"- Status: {param.level}\n"
                    result += f"- Action: Immediate intervention required\n"
                    result += _get_context_aware_advice(param.parameter, param.value, param.unit, "critical")
                    result += "\n"
                elif param.score == 2:
                    result += f"**🟡 {param.parameter.upper()}** ({param.value} {param.unit})\n"
                    result += f"- Status: {param.level}\n"
                    result += _get_context_aware_advice(param.parameter, param.value, param.unit, "moderate")
                    result += "\n"

            # General advice
            result += "### General Guidance\n\n"
            result += "- Monitor air quality trends over time\n"
            result += "- Ensure HVAC systems are properly maintained\n"
            result += "- Consider air purifiers for high-traffic areas\n"
            result += "- Communicate with occupants about air quality status\n"

            return result

        except InBiotAPIError as e:
            return create_data_unavailable_error(
                device_name=device_config.name,
                error_message=e.message,
            )

    @mcp.tool()
    async def well_certification_roadmap(
        device: Annotated[str, Field(description="Device ID for certification roadmap")]
    ) -> str:
        """
        Get a prioritized roadmap to improve WELL certification level.

        Analyzes current compliance gaps and prioritizes improvements by ROI
        (points gained per effort). Shows the fastest path to the next
        certification level with specific, actionable steps.
        """
        if device not in devices:
            return f"Unknown device: {device}. Use list_devices to see available options."

        device_config = devices[device]

        try:
            data = await inbiot_client.get_latest_measurements(device_config)
            assessment = well_engine.assess(device_config.name, data)

            result = f"## WELL Certification Roadmap: {device_config.name}\n\n"
            result += f"**Current Level**: {assessment.well_level} ({assessment.percentage:.0f}%)\n\n"

            # Determine next level target
            if assessment.percentage < 40:
                next_level = "Bronze"
                target_pct = 40
            elif assessment.percentage < 60:
                next_level = "Silver"
                target_pct = 60
            elif assessment.percentage < 75:
                next_level = "Gold"
                target_pct = 75
            elif assessment.percentage < 90:
                next_level = "Platinum"
                target_pct = 90
            else:
                result += "🏆 **Congratulations!** You've achieved Platinum-level compliance.\n\n"
                result += "Focus on maintaining current excellent conditions.\n"
                return result

            points_needed = int((target_pct - assessment.percentage) * assessment.max_score / 100)
            result += f"**Next Target**: {next_level} ({target_pct}%) - Need ~{points_needed} more points\n\n"

            # Analyze improvement opportunities
            opportunities = []
            for param in assessment.parameters:
                if param.score < 4:  # Room for improvement
                    threshold = get_threshold_for_parameter(param.parameter)
                    if not threshold:
                        continue

                    potential_gain = 4 - param.score  # Max points we could gain

                    # Calculate effort (how far from next threshold)
                    if is_range_based(param.parameter):
                        optimal_min = threshold.get("optimal_min", 20)
                        optimal_max = threshold.get("optimal_max", 24)
                        if param.value < optimal_min:
                            effort = optimal_min - param.value
                        elif param.value > optimal_max:
                            effort = param.value - optimal_max
                        else:
                            effort = 0
                        effort_str = f"{effort:.1f} {param.unit} adjustment needed"
                    elif is_higher_better(param.parameter):
                        next_threshold = threshold.get("good", 60) if param.score < 3 else threshold.get("excellent", 80)
                        effort = next_threshold - param.value
                        effort_str = f"Improve by {effort:.0f} points"
                    else:
                        # Pollutants - lower is better
                        if param.score == 0:
                            next_threshold = threshold.get("poor", param.value)
                        elif param.score == 1:
                            next_threshold = threshold.get("acceptable", param.value)
                        elif param.score == 2:
                            next_threshold = threshold.get("good", param.value)
                        else:
                            next_threshold = threshold.get("excellent", param.value)
                        effort = param.value - next_threshold
                        effort_str = f"Reduce by {effort:.0f} {param.unit}"

                    # ROI = points gained / relative effort
                    roi = potential_gain / max(effort, 0.1) if effort > 0 else potential_gain * 10

                    opportunities.append({
                        "parameter": param.parameter,
                        "current": param.value,
                        "unit": param.unit,
                        "score": param.score,
                        "potential_gain": potential_gain,
                        "effort_str": effort_str,
                        "roi": roi,
                        "level": param.level,
                    })

            # Sort by ROI (highest first = easiest wins)
            opportunities.sort(key=lambda x: x["roi"], reverse=True)

            result += "### Priority Actions (by ROI)\n\n"
            result += "| Priority | Parameter | Current | Potential | Action |\n"
            result += "|----------|-----------|---------|-----------|--------|\n"

            for i, opp in enumerate(opportunities[:5], 1):
                result += f"| {i} | {opp['parameter'].upper()} | {opp['current']} {opp['unit']} | +{opp['potential_gain']} pts | {opp['effort_str']} |\n"

            result += "\n### Quick Wins\n\n"
            quick_wins = [o for o in opportunities if o["score"] == 2 or o["score"] == 3]
            if quick_wins:
                for opp in quick_wins[:3]:
                    result += f"- **{opp['parameter'].upper()}**: Already at '{opp['level']}' - small improvement reaches next tier\n"
            else:
                result += "- Focus on the priority actions above\n"

            result += "\n### Estimated Path to " + next_level + "\n\n"
            cumulative = 0
            for i, opp in enumerate(opportunities, 1):
                cumulative += opp["potential_gain"]
                if cumulative >= points_needed:
                    result += f"Improving the top {i} parameters would achieve {next_level} certification.\n"
                    break

            return result

        except InBiotAPIError as e:
            return create_data_unavailable_error(
                device_name=device_config.name,
                error_message=e.message,
            )


def _get_context_aware_advice(parameter: str, value: float, unit: str, severity: str) -> str:
    """Get context-aware advice with specific targets based on current value."""
    threshold = get_threshold_for_parameter(parameter)

    if not threshold:
        return "- Review parameter and consult WELL guidelines\n"

    result = ""

    if is_range_based(parameter):
        # Temperature/humidity - range-based
        optimal_min = threshold.get("optimal_min", 20)
        optimal_max = threshold.get("optimal_max", 24)

        if value < optimal_min:
            diff = optimal_min - value
            result += f"- Target: Increase by {diff:.1f} {unit} to reach optimal range ({optimal_min}-{optimal_max} {unit})\n"
            if parameter == "temperature":
                result += "- Action: Increase heating setpoint or check heating system\n"
            elif parameter == "humidity":
                result += "- Action: Activate humidification system\n"
        elif value > optimal_max:
            diff = value - optimal_max
            result += f"- Target: Reduce by {diff:.1f} {unit} to reach optimal range ({optimal_min}-{optimal_max} {unit})\n"
            if parameter == "temperature":
                result += "- Action: Increase cooling or improve ventilation\n"
            elif parameter == "humidity":
                result += "- Action: Activate dehumidification or increase ventilation\n"

    elif is_higher_better(parameter):
        # IAQ indicators - higher is better
        good_target = threshold.get("good", 60)
        excellent_target = threshold.get("excellent", 80)

        if value < good_target:
            diff = good_target - value
            result += f"- Target: Improve by {diff:.0f} points to reach 'Good' level ({good_target}+)\n"
        else:
            diff = excellent_target - value
            result += f"- Target: Improve by {diff:.0f} points to reach 'Excellent' level ({excellent_target}+)\n"
        result += "- Action: Address underlying air quality parameters\n"

    else:
        # Pollutants - lower is better
        good_target = threshold.get("good", value * 0.8)
        excellent_target = threshold.get("excellent", value * 0.5)

        if severity == "critical":
            diff = value - good_target
            result += f"- Target: Reduce by {diff:.0f} {unit} to reach 'Good' level (≤{good_target} {unit})\n"
        else:
            diff = value - excellent_target
            result += f"- Target: Reduce by {diff:.0f} {unit} to reach 'Excellent' level (≤{excellent_target} {unit})\n"

        # Parameter-specific actions
        if parameter == "co2":
            result += "- Action: Increase outdoor air ventilation rate\n"
            if value > 1000:
                result += "- Consider: Reducing occupancy or adding demand-controlled ventilation\n"
        elif parameter in ["pm25", "pm10", "pm1", "pm4"]:
            result += "- Action: Check/replace HVAC filters (MERV 13+ recommended)\n"
            result += "- Consider: Adding portable HEPA air purifiers\n"
        elif parameter == "vocs":
            result += "- Action: Increase ventilation and identify VOC sources\n"
            result += "- Consider: Using low-VOC materials and products\n"
        elif parameter == "formaldehyde":
            result += "- Action: Increase ventilation and identify emission sources\n"
            result += "- Consider: Removing or sealing formaldehyde-emitting materials\n"

    return result


def _get_parameter_advice(parameter: str, severity: str) -> str:
    """Legacy function - kept for backward compatibility."""
    return _get_context_aware_advice(parameter, 0, "", severity)
