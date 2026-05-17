from .crowding_penalty import calculate_crowding_penalty
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from agents import PathfinderAnalystCrew
# ==============================================================================
#                           TRAIL MATCH SCORES 
# ==============================================================================

def calculate_trail_match_scores(trail, profile, difficulty_mult=0.33, duration_mult=0.33, interests_mult=0.33):
    """
    Evaluates a trail's compatibility based on three parameters: 
    1. Strict binary difficulty match.
    2. Linear decay duration bounds check.
    3. Keyword interest lookup matching within the trail's long-form description text.
    
    Weights are safely adjusted via dynamic analyst multipliers.
    """
    total_weight = float(difficulty_mult) + float(duration_mult) + float(interests_mult)
    
    if total_weight == 0:
        total_weight = 1.0

    score_difficulty = 0.0
    score_duration = 0.0
    score_interests = 0.0  
    
    target_difficulty = profile.get("hiker_intent") if profile.get("hiker_intent") is not None else profile.get("hiker_expertise")
    min_user_dur = profile.get("min_trail_duration_hours")
    max_user_dur = profile.get("max_trail_duration_hours")
    user_interests = profile.get("interests", [])
    
    if isinstance(user_interests, str):
        user_interests = [user_interests]
    
    # DIFFICULTY MATCH (Strict Binary Gate)
    if target_difficulty is not None:
        if trail.get("custom_difficulty_score") == target_difficulty:
            score_difficulty = 1.0
            
    # CALCULATE TRAIL DURATION (Pace = 4 km/h)
    trail_duration = trail.get("duration_hours")
    if trail_duration is None:
        distance_km = float(trail.get("distance_km", 0.0))
        trail_duration = distance_km / 4.0 if distance_km > 0 else 0.0
    else:
        trail_duration = float(trail_duration)

    # DURATION MATCH LOGIC (Decay scaling)
    if trail_duration > 0:
        if min_user_dur is not None and max_user_dur is not None:
            min_d = float(min_user_dur)
            max_d = float(max_user_dur)
            if min_d <= trail_duration <= max_d:
                score_duration = 1.0
            elif trail_duration < min_d:
                distance_away = min_d - trail_duration
                score_duration = max(0.0, 1.0 - distance_away)
            elif trail_duration > max_d:
                distance_away = trail_duration - max_d
                score_duration = max(0.0, 1.0 - distance_away)
                
        elif max_user_dur is not None:
            max_d = float(max_user_dur)
            if trail_duration <= max_d:
                score_duration = 1.0
            else:
                distance_away = trail_duration - max_d
                score_duration = max(0.0, 1.0 - distance_away)
                
        elif min_user_dur is not None:
            min_d = float(min_user_dur)
            if trail_duration >= min_d:
                score_duration = 1.0
            else:
                distance_away = min_d - trail_duration
                score_duration = max(0.0, 1.0 - distance_away)
        else:
            score_duration = 1.0
    
    trail_description = trail.get("description", "")

    analyst_crew_instance = PathfinderAnalystCrew()

    score_interests = analyst_crew_instance.evaluate_trail_interests_with_agent(
    user_interests=user_interests, 
    trail_description=trail_description
    )
    # Extract the NUTS3 region code from the current trail data block
    trail_nuts3 = trail.get("nuts3_code") or "UNKNOWN"
    
    crowding_data = calculate_crowding_penalty(nuts3_code=trail_nuts3)
    penalty_multiplier = crowding_data["applied_match_penalty"] 

    # APPLY WEIGHT MULTIPLIERS
    base_composite_score = (
        (score_difficulty * float(difficulty_mult)) + 
        (score_duration * float(duration_mult)) + 
        (score_interests * float(interests_mult))
    )

    raw_final_score = base_composite_score - penalty_multiplier    
    final_composite_score = max(0.0, min(1.0, raw_final_score / total_weight))
    
    return {
        "composite_score": round(final_composite_score, 3),
        "difficulty_match": score_difficulty,
        "duration_match": round(score_duration, 2),
        "interests_match_score": round(score_interests, 2),
        "calculated_duration": round(trail_duration, 2),
        
        "crowding_index": crowding_data["crowding_index_1_to_5"],
        "crowding_label": crowding_data["crowding_description"],
        "penalty_subtracted": penalty_multiplier,

        "density_val": crowding_data.get("raw_density_score", 0.0)
    }
