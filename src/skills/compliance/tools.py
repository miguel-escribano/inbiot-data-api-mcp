"""Compliance tools for WELL Building Standard assessment."""

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from src.api.inbiot import InBiotClient, InBiotAPIError
from src.models.schemas import DeviceConfig
from src.well.compliance import WELLComplianceEngine
from src.well.thresholds import get_threshold_for_parameter, is_range_based, is_higher_better, normalize_parameter_name
from src.utils.dates import parse_date_param
from src.utils.validation import validate_device


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
    ) -> dict:
        """
        Assess WELL Building Standard compliance for an InBiot device.

        Evaluates current air quality against WELL v2, ASHRAE 62.1/55, and WHO Indoor
        standards. Returns certification level eligibility and parameter-by-parameter assessment.
        """
        try:
            device_config = validate_device(devices, device)
        except ValueError as e:
            return {"error": str(e)}

        try:
            data = await inbiot_client.get_latest_measurements(device_config)
            assessment = well_engine.assess(device_config.name, data)

            return {
                "device": assessment.device_name,
                "overall_score": assessment.overall_score,
                "max_score": assessment.max_score,
                "percentage": assessment.percentage,
                "well_level": assessment.well_level,
                "parameters": [
                    {
                        "parameter": p.parameter,
                        "value": p.value,
                        "unit": p.unit,
                        "score": p.score,
                        "level": p.level,
                        "well_compliant": p.well_compliant,
                    }
                    for p in assessment.parameters
                ],
                "recommendations": assessment.recommendations,
            }

        except InBiotAPIError as e:
            return {"error": e.message, "device": device_config.name}

    @mcp.tool()
    async def well_feature_compliance(
        device: Annotated[str, Field(description="Device ID for WELL feature analysis")]
    ) -> dict:
        """
        Get WELL Building Standard compliance broken down by individual features (A01-A08, T01-T07).

        Shows compliance status for each WELL v2 feature with specific scores and
        recommendations. More detailed than standard compliance check.
        """
        try:
            device_config = validate_device(devices, device)
        except ValueError as e:
            return {"error": str(e)}

        try:
            from src.well.features import WELL_FEATURES
            from src.well.thresholds import normalize_parameter_name

            data = await inbiot_client.get_latest_measurements(device_config)

            features = []
            for feature_id, feature in WELL_FEATURES.items():
                feature_params = []
                for param in data:
                    if normalize_parameter_name(param.type) in feature.parameters:
                        feature_params.append(param)

                if feature_params:
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
                    compliant = percentage >= 50

                    entry = {
                        "feature_id": feature_id,
                        "name": feature.name,
                        "score": total_score,
                        "max_score": max_score,
                        "percentage": round(percentage, 1),
                        "level": well_engine._determine_well_level(percentage),
                        "compliant": compliant,
                    }

                    if not compliant:
                        entry["health_impact"] = feature.health_impact
                        entry["mitigation_strategies"] = feature.mitigation_strategies[:3]

                    features.append(entry)

            return {
                "device": device_config.name,
                "features": features,
            }

        except InBiotAPIError as e:
            return {"error": e.message, "device": device_config.name}

    @mcp.tool()
    async def health_recommendations(
        device: Annotated[str, Field(description="Device ID to generate recommendations for")]
    ) -> dict:
        """
        Generate health and comfort recommendations based on current air quality.

        Provides actionable advice for building managers and occupants based on
        current sensor readings and WELL Building Standard guidelines.
        """
        try:
            device_config = validate_device(devices, device)
        except ValueError as e:
            return {"error": str(e)}

        try:
            data = await inbiot_client.get_latest_measurements(device_config)
            assessment = well_engine.assess(device_config.name, data)

            if assessment.percentage >= 75:
                overall_status = "good"
            elif assessment.percentage >= 50:
                overall_status = "moderate"
            else:
                overall_status = "needs_improvement"

            issues = []
            for param in assessment.parameters:
                if param.score <= 2:
                    severity = "critical" if param.score <= 1 else "moderate"
                    entry = {
                        "parameter": param.parameter,
                        "value": param.value,
                        "unit": param.unit,
                        "level": param.level,
                        "severity": severity,
                        "advice": _get_advice_dict(param.parameter, param.value, param.unit, severity),
                    }
                    issues.append(entry)

            return {
                "device": device_config.name,
                "overall_status": overall_status,
                "percentage": assessment.percentage,
                "issues": issues,
            }

        except InBiotAPIError as e:
            return {"error": e.message, "device": device_config.name}

    @mcp.tool()
    async def well_certification_roadmap(
        device: Annotated[str, Field(description="Device ID for certification roadmap")]
    ) -> dict:
        """
        Get a prioritized roadmap to improve WELL certification level.

        Analyzes current compliance gaps and prioritizes improvements by ROI
        (points gained per effort). Shows the fastest path to the next
        certification level with specific, actionable steps.
        """
        try:
            device_config = validate_device(devices, device)
        except ValueError as e:
            return {"error": str(e)}

        try:
            data = await inbiot_client.get_latest_measurements(device_config)
            assessment = well_engine.assess(device_config.name, data)

            if assessment.percentage < 40:
                next_level, target_pct = "Bronze", 40
            elif assessment.percentage < 60:
                next_level, target_pct = "Silver", 60
            elif assessment.percentage < 75:
                next_level, target_pct = "Gold", 75
            elif assessment.percentage < 90:
                next_level, target_pct = "Platinum", 90
            else:
                return {
                    "device": device_config.name,
                    "current_level": assessment.well_level,
                    "percentage": assessment.percentage,
                    "status": "platinum_achieved",
                }

            points_needed = int((target_pct - assessment.percentage) * assessment.max_score / 100)

            opportunities = []
            for param in assessment.parameters:
                if param.score < 4:
                    threshold = get_threshold_for_parameter(param.parameter)
                    if not threshold:
                        continue

                    potential_gain = 4 - param.score

                    if is_range_based(param.parameter):
                        optimal_min = threshold.get("optimal_min", 20)
                        optimal_max = threshold.get("optimal_max", 24)
                        if param.value < optimal_min:
                            effort = optimal_min - param.value
                        elif param.value > optimal_max:
                            effort = param.value - optimal_max
                        else:
                            effort = 0
                        action = f"{effort:.1f} {param.unit} adjustment needed"
                    elif is_higher_better(param.parameter):
                        next_threshold = threshold.get("good", 60) if param.score < 3 else threshold.get("excellent", 80)
                        effort = next_threshold - param.value
                        action = f"Improve by {effort:.0f} points"
                    else:
                        if param.score == 0:
                            next_threshold = threshold.get("poor", param.value)
                        elif param.score == 1:
                            next_threshold = threshold.get("acceptable", param.value)
                        elif param.score == 2:
                            next_threshold = threshold.get("good", param.value)
                        else:
                            next_threshold = threshold.get("excellent", param.value)
                        effort = param.value - next_threshold
                        action = f"Reduce by {effort:.0f} {param.unit}"

                    roi = potential_gain / max(effort, 0.1) if effort > 0 else potential_gain * 10

                    opportunities.append({
                        "parameter": param.parameter,
                        "current": param.value,
                        "unit": param.unit,
                        "score": param.score,
                        "potential_gain": potential_gain,
                        "action": action,
                        "roi": round(roi, 2),
                        "level": param.level,
                    })

            opportunities.sort(key=lambda x: x["roi"], reverse=True)

            cumulative = 0
            steps_to_target = len(opportunities)
            for i, opp in enumerate(opportunities, 1):
                cumulative += opp["potential_gain"]
                if cumulative >= points_needed:
                    steps_to_target = i
                    break

            return {
                "device": device_config.name,
                "current_level": assessment.well_level,
                "percentage": assessment.percentage,
                "next_level": next_level,
                "target_pct": target_pct,
                "points_needed": points_needed,
                "opportunities": opportunities[:5],
                "steps_to_target": steps_to_target,
            }

        except InBiotAPIError as e:
            return {"error": e.message, "device": device_config.name}

    @mcp.tool()
    async def compliance_over_time(
        device: Annotated[str, Field(description="Device ID")],
        start_date: Annotated[str, Field(description="Start date (YYYY-MM-DD)")],
        end_date: Annotated[str, Field(description="End date (YYYY-MM-DD)")],
    ) -> dict:
        """
        Evaluate sustained WELL compliance over a time period.

        Unlike well_compliance_check (single snapshot), this analyzes every
        measurement in the range and reports what percentage of the time each
        parameter was compliant. Essential for real WELL certification which
        requires sustained performance, not just a single good reading.
        """
        try:
            device_config = validate_device(devices, device)
        except ValueError as e:
            return {"error": str(e)}

        try:
            start_dt = parse_date_param(start_date)
            end_dt = parse_date_param(end_date, end_of_day=True)
        except ValueError as e:
            return {"error": f"Invalid date format: {e}. Use YYYY-MM-DD or ISO-8601 format."}

        try:
            data = await inbiot_client.get_historical_data(device_config, start_dt, end_dt)

            parameters = []
            total_compliant_hours = 0
            total_hours = 0

            for param in data:
                if not param.measurements:
                    continue

                normalized = normalize_parameter_name(param.type)
                threshold = get_threshold_for_parameter(normalized)
                if not threshold:
                    continue

                compliant_count = 0
                for m in param.measurements:
                    val = m.numeric_value
                    if is_range_based(normalized):
                        ok = threshold["acceptable_min"] <= val <= threshold["acceptable_max"]
                    elif is_higher_better(normalized):
                        ok = val >= threshold["acceptable"]
                    else:
                        ok = val <= threshold["acceptable"]
                    if ok:
                        compliant_count += 1

                total = len(param.measurements)
                pct = round(compliant_count / total * 100, 1) if total > 0 else 0

                # Find worst violation
                if is_range_based(normalized):
                    values = [m.numeric_value for m in param.measurements]
                    worst = max(values, key=lambda v: max(
                        threshold["acceptable_min"] - v if v < threshold["acceptable_min"] else 0,
                        v - threshold["acceptable_max"] if v > threshold["acceptable_max"] else 0,
                    ))
                elif is_higher_better(normalized):
                    worst = min(m.numeric_value for m in param.measurements)
                else:
                    worst = max(m.numeric_value for m in param.measurements)

                parameters.append({
                    "parameter": normalized,
                    "unit": param.unit,
                    "measurements": total,
                    "compliant_count": compliant_count,
                    "compliant_pct": pct,
                    "worst_value": round(worst, 1),
                    "sustained": pct >= 95,
                })

                total_compliant_hours += compliant_count
                total_hours += total

            overall_pct = round(total_compliant_hours / total_hours * 100, 1) if total_hours > 0 else 0

            # Determine sustained level
            if overall_pct >= 95:
                sustained_level = "Sustained compliance"
            elif overall_pct >= 80:
                sustained_level = "Mostly compliant"
            elif overall_pct >= 50:
                sustained_level = "Intermittent compliance"
            else:
                sustained_level = "Non-compliant"

            worst_params = sorted(parameters, key=lambda p: p["compliant_pct"])

            return {
                "device": device_config.name,
                "period": {"start": start_date, "end": end_date},
                "overall_compliant_pct": overall_pct,
                "sustained_level": sustained_level,
                "parameters": parameters,
                "weakest_parameters": [
                    {"parameter": p["parameter"], "compliant_pct": p["compliant_pct"]}
                    for p in worst_params[:3]
                    if p["compliant_pct"] < 100
                ],
            }

        except InBiotAPIError as e:
            return {"error": e.message, "device": device_config.name}


def _get_advice_dict(parameter: str, value: float, unit: str, severity: str) -> dict:
    """Get structured advice based on current value and severity."""
    threshold = get_threshold_for_parameter(parameter)

    if not threshold:
        return {"action": "Review parameter and consult WELL guidelines"}

    result = {}

    if is_range_based(parameter):
        optimal_min = threshold.get("optimal_min", 20)
        optimal_max = threshold.get("optimal_max", 24)
        if value < optimal_min:
            result["target"] = f"Increase by {optimal_min - value:.1f} {unit} to optimal range ({optimal_min}-{optimal_max})"
        elif value > optimal_max:
            result["target"] = f"Reduce by {value - optimal_max:.1f} {unit} to optimal range ({optimal_min}-{optimal_max})"
    elif is_higher_better(parameter):
        good_target = threshold.get("good", 60)
        result["target"] = f"Improve by {good_target - value:.0f} points to reach 'Good' level"
    else:
        target_key = "good" if severity == "critical" else "excellent"
        target_val = threshold.get(target_key, value * 0.8)
        result["target"] = f"Reduce to {target_val} {unit} ({target_key} level)"

    # Parameter-specific actions
    actions = {
        "co2": "Increase outdoor air ventilation rate",
        "pm25": "Check/replace HVAC filters (MERV 13+ recommended)",
        "pm10": "Check/replace HVAC filters (MERV 13+ recommended)",
        "vocs": "Increase ventilation and identify VOC sources",
        "formaldehyde": "Increase ventilation and identify emission sources",
        "temperature": "Adjust HVAC setpoint",
        "humidity": "Adjust humidification/dehumidification system",
    }
    if parameter in actions:
        result["action"] = actions[parameter]

    return result
