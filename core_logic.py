def apply_hard_filters(trails, profile):
    viable = []
    # Capability vs Intent check [cite: 23, 25]
    intent_ceiling = get_sac_ceiling(profile['session_intent'])
    
    for trail in trails:
        # 1. SAC Scale Check [cite: 54, 75]
        if trail.sac_scale > intent_ceiling:
            continue
            
        # 2. Duration Buffer Check [cite: 55, 60]
        # Logic: target_hours +/- (10min * hours), cap at 60min [cite: 55, 59]
        if not is_within_duration_buffer(trail.duration, profile['custom_duration_hours']):
            continue
            
        # 3. Safety/Visibility Filter [cite: 62]
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