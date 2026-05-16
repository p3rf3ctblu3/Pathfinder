def get_sac_ceiling(session_intent: str) -> int:
    """
    Maps conversational intent strings to strict numerical safety ceilings (1-5)[cite: 20].
    Based on the standard Swiss Alpine Club hiking scale[cite: 75].
    """
    intent = str(session_intent).lower().strip()
    
    # Mapping Archetype boundaries to raw max permitted levels [cite: 28, 29]
    intent_mapping = {
        "casual": 1, "novice": 1, "family": 1, "easy": 1, "t1": 1, "1": 1,
        "active": 2, "intermediate": 2, "regular": 2, "moderate": 2, "t2": 2, "2": 2,
        "experienced": 3, "advanced": 3, "challenging": 3, "t3": 3, "3": 3,
        "elite": 4, "mountaineer": 4, "marathoner": 4, "t4": 4, "4": 4,
        "extreme": 5, "mountaineering": 5, "5": 5
    }
    return intent_mapping.get(intent, 1) # Default safe baseline is T1 [cite: 28]

def calculate_preference_fit(trail, profile) -> float:
    """
    Calculates the combined mathematical alignment and semantic vibe score[cite: 64, 65].
    Returns a score out of 100.0.
    """
    score = 100.0
    
    # 1. CORE METRIC: Mathematical Duration Alignment [cite: 64]
    target_hours = profile.get('custom_duration_hours', 2.0)
    duration_delta = abs(trail.duration - target_hours)
    # Deduct points the further away it scales from the perfect target duration
    score -= min(duration_delta * 15, 30) 

    # 2. CORE METRIC: Elevation / Intensity Check [cite: 64]
    # Reduce alignment score if trail matches intent ceiling but strains maximum capacity [cite: 24, 25]
    if profile.get('physical_capability') == "casual" and trail.elevation_gain > 150: [cite: 28]
        score -= 20

    # 3. SEMANTIC VIBE & TERRAIN MATCHING [cite: 65, 79]
    # ORS returns an array of surface attributes with precise percentages [cite: 73, 74]
    # e.g., trail.surface_percentages = {"dirt": 0.80, "asphalt": 0.20}
    surface_data = getattr(trail, 'surface_percentages', {})
    user_preferred_terrain = profile.get('preferred_terrain', '').lower() # e.g., "gravel path" [cite: 76, 77]
    
    # Account for implicit complaints like weak joints / ankles [cite: 78]
    has_weak_ankles = "ankle" in profile.get('implicit_clues', '').lower() or "joint" in profile.get('implicit_clues', '').lower() [cite: 78]

    for surface_type, percentage in surface_data.items():
        # High impact penalties for weak ankles [cite: 78, 80]
        if has_weak_ankles and surface_type in ["asphalt", "paved", "sand"]: [cite: 78, 80]
            score -= (percentage * 25) # Heavy penalty for prolonged high-impact surfaces [cite: 80]
            
        # Positive reinforcement for explicit preferences [cite: 77]
        if user_preferred_terrain and user_preferred_terrain in surface_type:
            score += (percentage * 15)

    return max(0.0, min(score, 100.0))


def get_tourist_penalty(trail) -> float:
    """
    Executes the proxy algorithm `estimate_trail_crowd` combining Eurostat 
    regional indices and real-time weather to penalize overtourism[cite: 36, 66].
    """
    # Fallback default values
    eurostat_index = getattr(trail, 'eurostat_regional_index', 0.5) # e.g. Attica rating [cite: 34]
    is_sunny = getattr(trail, 'is_good_weather', True) # From OpenWeatherMap [cite: 32]
    
    # Proxy estimate computation loop [cite: 36]
    crowd_estimation = eurostat_index * 1.5
    if is_sunny:
        crowd_estimation += 0.5 # Great weather shifts people onto paths [cite: 36]
        
    # Tourist Density Penalty out of a maximum of 20 points [cite: 66, 67]
    penalty = min(crowd_estimation * 10, 20.0)
    return penalty

def sort_and_curate(trails) -> dict:
    """
    Sorts all evaluated options and organizes them into the mandatory three-tier layout,
    guaranteeing a less crowded "Hidden Gem" option surfaces directly near the top.
    """
    # Sort purely by calculated final score descending [cite: 67]
    sorted_trails = sorted(trails, key=lambda t: t.final_score, reverse=True)
    
    if not sorted_trails:
        return {"perfect_match": None, "hidden_gem": None, "scenic_alternative": None}
        
    curated_output = {
        "perfect_match": sorted_trails[0], # The absolute highest mathematically aligned match [cite: 99]
        "hidden_gem": None,
        "scenic_alternative": None
    }
    
    # Scan the remaining pool to find a "Hidden Gem" (Low tourist crowd, high experience score) 
    remaining_pool = sorted_trails[1:]
    
    for potential_gem in remaining_pool:
        # Lower baseline tourist penalty proves it is lesser known and uncrowded [cite: 66, 68]
        if getattr(potential_gem, 'eurostat_regional_index', 1.0) < 0.4:
            curated_output["hidden_gem"] = potential_gem
            remaining_pool.remove(potential_gem)
            break
            
    # Fallback if no specific low-tourist destination was captured in the dataset
    if not curated_output["hidden_gem"] and remaining_pool:
        curated_output["hidden_gem"] = remaining_pool.pop(0)
        
    # Extract the next high-scoring variant as the alternative path choice [cite: 99]
    if remaining_pool:
        curated_output["scenic_alternative"] = remaining_pool[0]
        
    return curated_output

def calculate_final_rankings(trails, profile) -> dict:
    # Final Match Score = Preference Alignment Score - Tourist Density Penalty [cite: 67]
    for trail in trails:
        pref_score = calculate_preference_fit(trail, profile)
        penalty = get_tourist_penalty(trail)
        trail.final_score = pref_score - penalty
        
    # Returns the finalized structured dictionary map [cite: 99]
    return sort_and_curate(trails)

def is_within_duration_buffer(trail_duration, profile_duration, mode="around"):
    """
    Determines if a trail's duration is within acceptable user-defined bounds.
    
    Parameters:
    - trail_duration (float): The actual trail duration in hours.
    - profile_duration (float): The user's target duration in hours.
    - mode (str): 'around', 'at_most', or 'at_least' based on chat parsing.
    """
    # Note 1: Hard floor baseline. Never recommend paths shorter than 10 minutes
    if trail_duration < 0.1:
        return False

    # Standard 15-minute buffer in hours for 'at_most' and 'at_least' bounds
    fixed_buffer = 0.25

    if mode == "at_most":
        # Eliminate options above xh + 15min
        return trail_duration <= (profile_duration + fixed_buffer)

    elif mode == "at_least":
        # Eliminate options below xh - 15min
        return trail_duration >= (profile_duration - fixed_buffer)

    elif mode == "around":
        # Dynamic calculation: 10 mins * target hours
        dynamic_buffer_minutes = 10 * profile_duration
        dynamic_buffer_hours = dynamic_buffer_minutes / 60

        # Note 2: Cap the maximum tolerance buffer at 60 minutes (1.0 hour)
        buffer = min(dynamic_buffer_hours, 1.0)

        lower_bound = profile_duration - buffer
        upper_bound = profile_duration + buffer

        return lower_bound <= trail_duration <= upper_bound

    return True


def apply_hard_filters(trails, profile):
    viable = []
    intent_ceiling = get_sac_ceiling(profile['session_intent'])
    
    # Grab the duration constraint type from the profile (default to 'around')
    duration_mode = profile.get('duration_mode', 'around')
    target_hours = profile.get('custom_duration_hours', 2.0)
    
    for trail in trails:
        # 1. SAC Scale Check
        if trail.sac_scale > intent_ceiling:
            continue
            
        # 2. Duration Buffer Check (Passing target and behavior type)
        if not is_within_duration_buffer(trail.duration, target_hours, mode=duration_mode):
            continue
            
        # 3. Safety/Visibility Filter
        if trail.visibility == "horrible":
            continue
            
        viable.append(trail)
        
    return viable

def calculate_final_rankings(trails, profile):
    # Final Match Score = Preference Alignment - Tourist Penalty [cite: 67]
    for trail in trails:
        pref_score = calculate_preference_fit(trail, profile) # Vibe/Terrain [cite: 65]
        penalty = get_tourist_penalty(trail) # Eurostat/Proxy data [cite: 36, 66]
        trail.final_score = pref_score - penalty
        
    # Ensure a "Hidden Gem" is promoted in the top 3 [cite: 68, 99]
    return sort_and_curate(trails)