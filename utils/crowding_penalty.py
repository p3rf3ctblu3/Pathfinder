import math

EUROSTAT_GREEK_DENSITY_MAP = {
    "EL305": 1142.1, "EL303": 8940.4, "EL522": 412.3,
    "EL542": 182.4,  "EL623": 6240.8, "EL431": 3890.2, "EL531": 42.1
}

def calculate_crowding_penalty(nuts3_code: str, sensitivity_k: float = 0.0005) -> dict:
    """Calculates exponential overtourism saturation scores and UI labels."""
    density = EUROSTAT_GREEK_DENSITY_MAP.get(nuts3_code, 150.0)
    raw_penalty = 1.0 - math.exp(-sensitivity_k * density)
    
    if density < 200:
        crowd_label, index_rating = "Low Crowding (Remote/Wilderness)", 1
    elif density < 1000:
        crowd_label, index_rating = "Moderate Crowding (Active Local Hub)", 2
    elif density < 2500:
        crowd_label, index_rating = "High Crowding (Popular Excursion Zone)", 3
    elif density < 5000:
        crowd_label, index_rating = "Very High Crowding (Heavy Tourism Load)", 4
    else:
        crowd_label, index_rating = "Extreme Crowding (Overtourism Saturated)", 5

    return {
        "raw_density_score": density,
        "crowding_index_1_to_5": index_rating,
        "crowding_description": crowd_label,
        "applied_match_penalty": round(min(1.0, max(0.0, raw_penalty)), 3)
    }