from __future__ import annotations


def compute_risk(cape: float, li: float, cin: float, shear_mph: float) -> tuple[int, str]:
    """
    Composite severe weather risk score 0–10.
    Based on standard meteorological thresholds.
    
    Returns:
        tuple[int, str]: (risk_score, risk_label)
        risk_label is "Low", "Moderate", "High", or "Extreme"
    """
    score = 0.0

    # CAPE contribution (0–4 pts)
    if cape >= 3000:
        score += 4.0
    elif cape >= 2000:
        score += 3.0
    elif cape >= 1000:
        score += 2.0
    elif cape >= 500:
        score += 1.0

    # Lifted Index contribution (0–3 pts); more negative = more unstable
    if li <= -6:
        score += 3.0
    elif li <= -4:
        score += 2.0
    elif li <= -2:
        score += 1.0

    # Wind shear contribution (0–2 pts)
    if shear_mph >= 50:
        score += 2.0
    elif shear_mph >= 30:
        score += 1.0

    # CIN penalty: high CIN inhibits storms even with good CAPE
    if cin <= -200:
        score *= 0.5

    int_score = min(10, round(score))

    if int_score <= 2:
        label = "Low"
    elif int_score <= 5:
        label = "Moderate"
    elif int_score <= 7:
        label = "High"
    else:
        label = "Extreme"

    return int_score, label
