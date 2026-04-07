"""Vital sign risk assessment rules."""


class VitalsRulesEngine:
    """Rules for assessing vital sign risk."""

    # Blood Pressure thresholds (mmHg)
    BP_NORMAL_MAX = 120
    BP_ELEVATED_MAX = 129
    BP_STAGE1_MAX = 139
    BP_STAGE2_MAX = 180  # 180+ is crisis level

    # Heart Rate thresholds (bpm)
    HR_NORMAL_MIN = 60
    HR_NORMAL_MAX = 100
    HR_TACHYCARDIA = 100
    HR_SEVERE_TACHYCARDIA = 120
    HR_BRADYCARDIA = 60
    HR_SEVERE_BRADYCARDIA = 40

    # Blood Glucose thresholds (mg/dL)
    GLUCOSE_NORMAL_FASTING = 100
    GLUCOSE_PREDIABETIC = 126
    GLUCOSE_DIABETIC_HIGH = 200
    GLUCOSE_SEVERE_HYPERGLYCEMIA = 400
    GLUCOSE_HYPOGLYCEMIA_WARNING = 70
    GLUCOSE_SEVERE_HYPOGLYCEMIA = 54

    # SpO2 thresholds (%)
    SPO2_NORMAL_MIN = 95
    SPO2_WARNING = 90
    SPO2_CRITICAL = 85

    @staticmethod
    def assess_blood_pressure(systolic: int, diastolic: int) -> dict:
        """Assess blood pressure risk and return findings."""
        findings = []

        if systolic >= VitalsRulesEngine.BP_STAGE2_MAX or diastolic >= 120:
            risk_level = "critical"
            findings.append({
                "code": "BP_CRISIS",
                "description": f"Hypertensive crisis: {systolic}/{diastolic} mmHg",
                "severity": "critical",
            })
        elif systolic >= VitalsRulesEngine.BP_STAGE1_MAX or diastolic >= 90:
            risk_level = "high"
            findings.append({
                "code": "BP_STAGE2",
                "description": f"Stage 2 hypertension: {systolic}/{diastolic} mmHg",
                "severity": "high",
            })
        elif systolic >= 130 or diastolic >= 80:
            risk_level = "moderate"
            findings.append({
                "code": "BP_STAGE1",
                "description": f"Stage 1 hypertension: {systolic}/{diastolic} mmHg",
                "severity": "moderate",
            })
        elif systolic >= VitalsRulesEngine.BP_NORMAL_MAX:
            risk_level = "low"
            findings.append({
                "code": "BP_ELEVATED",
                "description": f"Elevated blood pressure: {systolic}/{diastolic} mmHg",
                "severity": "low",
            })
        else:
            risk_level = "normal"

        return {"risk_level": risk_level, "findings": findings}

    @staticmethod
    def assess_heart_rate(heart_rate: int) -> dict:
        """Assess heart rate risk and return findings."""
        findings = []

        if heart_rate > VitalsRulesEngine.HR_SEVERE_TACHYCARDIA:
            risk_level = "high"
            findings.append({
                "code": "HR_SEVERE_TACHYCARDIA",
                "description": f"Severe tachycardia: {heart_rate} bpm",
                "severity": "high",
            })
        elif heart_rate > VitalsRulesEngine.HR_TACHYCARDIA:
            risk_level = "moderate"
            findings.append({
                "code": "HR_TACHYCARDIA",
                "description": f"Tachycardia: {heart_rate} bpm",
                "severity": "moderate",
            })
        elif heart_rate < VitalsRulesEngine.HR_SEVERE_BRADYCARDIA:
            risk_level = "high"
            findings.append({
                "code": "HR_SEVERE_BRADYCARDIA",
                "description": f"Severe bradycardia: {heart_rate} bpm",
                "severity": "high",
            })
        elif heart_rate < VitalsRulesEngine.HR_BRADYCARDIA:
            risk_level = "moderate"
            findings.append({
                "code": "HR_BRADYCARDIA",
                "description": f"Bradycardia: {heart_rate} bpm",
                "severity": "moderate",
            })
        else:
            risk_level = "normal"

        return {"risk_level": risk_level, "findings": findings}

    @staticmethod
    def assess_glucose(glucose_level: int) -> dict:
        """Assess blood glucose risk and return findings."""
        findings = []

        if glucose_level >= VitalsRulesEngine.GLUCOSE_SEVERE_HYPERGLYCEMIA:
            risk_level = "critical"
            findings.append({
                "code": "GLUCOSE_SEVERE_HYPER",
                "description": f"Severe hyperglycemia: {glucose_level} mg/dL",
                "severity": "critical",
            })
        elif glucose_level >= VitalsRulesEngine.GLUCOSE_DIABETIC_HIGH:
            risk_level = "high"
            findings.append({
                "code": "GLUCOSE_HIGH",
                "description": f"High blood glucose: {glucose_level} mg/dL",
                "severity": "high",
            })
        elif glucose_level >= VitalsRulesEngine.GLUCOSE_PREDIABETIC:
            risk_level = "moderate"
            findings.append({
                "code": "GLUCOSE_PREDIABETIC",
                "description": f"Pre-diabetic glucose range: {glucose_level} mg/dL",
                "severity": "moderate",
            })
        elif glucose_level < VitalsRulesEngine.GLUCOSE_SEVERE_HYPOGLYCEMIA:
            risk_level = "critical"
            findings.append({
                "code": "GLUCOSE_SEVERE_HYPO",
                "description": f"Severe hypoglycemia: {glucose_level} mg/dL",
                "severity": "critical",
            })
        elif glucose_level < VitalsRulesEngine.GLUCOSE_HYPOGLYCEMIA_WARNING:
            risk_level = "high"
            findings.append({
                "code": "GLUCOSE_LOW",
                "description": f"Low blood glucose: {glucose_level} mg/dL",
                "severity": "high",
            })
        else:
            risk_level = "normal"

        return {"risk_level": risk_level, "findings": findings}

    @staticmethod
    def assess_spo2(spo2: int) -> dict:
        """Assess oxygen saturation risk and return findings."""
        findings = []

        if spo2 < VitalsRulesEngine.SPO2_CRITICAL:
            risk_level = "critical"
            findings.append({
                "code": "SPO2_CRITICAL",
                "description": f"Critical hypoxemia: SpO2 {spo2}%",
                "severity": "critical",
            })
        elif spo2 < VitalsRulesEngine.SPO2_WARNING:
            risk_level = "high"
            findings.append({
                "code": "SPO2_LOW",
                "description": f"Low oxygen saturation: SpO2 {spo2}%",
                "severity": "high",
            })
        elif spo2 < VitalsRulesEngine.SPO2_NORMAL_MIN:
            risk_level = "moderate"
            findings.append({
                "code": "SPO2_BORDERLINE",
                "description": f"Borderline oxygen saturation: SpO2 {spo2}%",
                "severity": "moderate",
            })
        else:
            risk_level = "normal"

        return {"risk_level": risk_level, "findings": findings}

    @staticmethod
    def check_vital_trend(readings: list, vital_type: str, window_days: int = 7) -> dict:
        """
        Check trend for a vital over time.

        Args:
            readings: List of numeric vital readings in chronological order (oldest first).
            vital_type: Type of vital being checked.
            window_days: Time window for trend (informational only).

        Returns:
            Trend analysis with direction and risk assessment.
        """
        if len(readings) < 2:
            return {"trend": "insufficient_data", "risk": "unknown"}

        # Simple linear direction based on first vs last value
        first = readings[0]
        last = readings[-1]
        change_pct = ((last - first) / first * 100) if first != 0 else 0

        if change_pct > 5:
            trend = "increasing"
        elif change_pct < -5:
            trend = "decreasing"
        else:
            trend = "stable"

        # Determine if the trend direction is concerning
        rising_bad = vital_type in ("bp_systolic", "bp_diastolic", "glucose", "heart_rate")
        falling_bad = vital_type == "spo2"

        risk = "normal"
        if trend == "increasing" and rising_bad:
            risk = "warning"
        elif trend == "decreasing" and falling_bad:
            risk = "warning"
        elif trend == "decreasing" and rising_bad:
            risk = "improving"

        return {
            "trend": trend,
            "risk": risk,
            "change_pct": round(change_pct, 1),
            "window_days": window_days,
        }
