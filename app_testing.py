import streamlit as st
from streamlit_js_eval import streamlit_js_eval as st_js, get_geolocation
from agents import PathfinderCrew, PathfinderAnalystCrew, run_gatekeeper_agent
from shapely.geometry import shape, Point
import openrouteservice
from geopy.geocoders import Nominatim
import os 
import time 
import math
import re
import json

# INCLUDES LIVE JSON SIDE WINDOW AND PRINTS MULTIPLIERS AND SCORES FOR ALL RECOMMENDED TRAILS

# =========================================
# PROCESS EUROSTAT DATA FOR TOURISM PENALTY
# =========================================

# Raw dataset mappings derived from Eurostat table [tour_occ_nin3] / [reg_area3]
EUROSTAT_GREEK_DENSITY_MAP = {
    "EL305": 1142.1,  # East Attica (Parnitha paths, regional concentration)
    "EL303": 8940.4,  # Central Athens (Extreme urban concentration)
    "EL522": 412.3,   # Thessaloniki (Moderate urban spread)
    "EL542": 182.4,   # Pieria / Mount Olympus (Low base footprint, isolated peaks)
    "EL623": 6240.8,  # Corfu Island (Massive island tourism pressure spike)
    "EL431": 3890.2,  # Heraklion / Crete (High coastal resort saturation)
    "EL531": 42.1,    # Ioannina / Vikos Gorge (Tranquil, vast natural territory)
}

def calculate_crowding_penalty(nuts3_code: str, sensitivity_k: float = 0.0005) -> dict:
    """
    Looks up a region's Eurostat density metric and returns a crowding factor
    along with an exponential penalty score capped strictly between 0.0 and 1.0.
    """
    # 1. Fetch the raw density from our Eurostat lookup map
    density = EUROSTAT_GREEK_DENSITY_MAP.get(nuts3_code, 150.0) # 150 is a safe fallback
    
    # 2. Run the exponential saturation math formula
    # Sensitivity_k tuned to 0.0005 means:
    # - Density of 42 (Vikos): ~2% penalty (Very quiet)
    # - Density of 1142 (Parnitha): ~43% penalty (Busy)
    # - Density of 6000+ (Corfu): ~95% penalty (Overcrowded)
    raw_penalty = 1.0 - math.exp(-sensitivity_k * density)
    
    # 3. Quantize into a readable 1-5 Descriptive Index for the UI
    if density < 200:
        crowd_label = "Low Crowding (Remote/Wilderness)"
        index_rating = 1
    elif density < 1000:
        crowd_label = "Moderate Crowding (Active Local Hub)"
        index_rating = 2
    elif density < 2500:
        crowd_label = "High Crowding (Popular Excursion Zone)"
        index_rating = 3
    elif density < 5000:
        crowd_label = "Very High Crowding (Heavy Tourism Load)"
        index_rating = 4
    else:
        crowd_label = "Extreme Crowding (Overtourism Saturated)"
        index_rating = 5

    return {
        "raw_density_score": density,
        "crowding_index_1_to_5": index_rating,
        "crowding_description": crowd_label,   # USE LABEL TO FLAG OVERCROWDED TRAILS
        "applied_match_penalty": round(min(1.0, max(0.0, raw_penalty)), 3)
    }


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

    score_interests = PathfinderAnalystCrew.evaluate_trail_interests_with_agent(
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

    final_composite_score = max(0.0, base_composite_score - penalty_multiplier)
    
    return {
        "composite_score": round(final_composite_score, 3),
        "difficulty_match": score_difficulty,
        "duration_match": round(score_duration, 2),
        "interests_match_score": round(score_interests, 2),
        "calculated_duration": round(trail_duration, 2),
        
        "crowding_index": crowding_data["crowding_index_1_to_5"],
        "crowding_label": crowding_data["crowding_description"],
        "penalty_subtracted": penalty_multiplier
    }


# ==================================
# SPATIAL ROUTING ENGINE FUNCTIONS
# ==================================
def invoke_isochrone_api(lat, lon, max_time, mode):
    """Calls OpenRouteService to generate a dynamic travel-time polygon boundary."""
    api_key = os.getenv("ORS_API_KEY")
    if not api_key:
        st.error("⚠️ Missing 'ORS_API_KEY' in your .env file!")
        return None
    try:
        client = openrouteservice.Client(key=api_key)
        ors_profile = "driving-car"
        if mode in ["foot", "walking", "hiking"]:
            ors_profile = "foot-hiking"
            
        time_seconds = int(max_time) * 60
        response = client.isochrones(
            locations=[[float(lon), float(lat)]], # ORS expects [LON, LAT]
            profile=ors_profile,
            range=[time_seconds],
            range_type='time'
        )
        return response['features'][0]['geometry']
    except Exception as e:
        st.error(f"❌ Isochrone API Failure: {str(e)}")
        return None


def invoke_geocoding_api(location_name):
    """Resolves a named regional string into a standard bounding box payload."""
    try:
        geolocator = Nominatim(user_agent="pathfinder_greece_trail_explorer")
        query_string = f"{location_name}, Greece"
        location = geolocator.geocode(query_string, geometry='geojson')
        
        if location and "boundingbox" in location.raw:
            bbox_raw = location.raw["boundingbox"]
            return {
                "min_lat": float(bbox_raw[0]),
                "max_lat": float(bbox_raw[1]),
                "min_lon": float(bbox_raw[2]),
                "max_lon": float(bbox_raw[3])
            }
        return None
    except Exception as e:
        st.error(f"❌ Geocoding API Failure: {str(e)}")
        return None


def filter_trails_spatial(trails, strategy, profile, gps):
    """Applies your requested hard spatial filtering logic using Shapely point containment."""
    viable_trails = []
    if not trails:
        return []

    if strategy == "ISOCHRONE":
        if gps and "lat" in gps and "lon" in gps:
            max_time = profile.get("max_travel_time") or 60  
            mode = profile.get("travel_mode") or "vehicle"
            polygon_geo = invoke_isochrone_api(gps['lat'], gps['lon'], max_time, mode)
            
            if polygon_geo:
                isochrone_shape = shape(polygon_geo)
                st.info("🛰️ Filtering trails based on travel-time isochrone...")
                for trail in trails:
                    if trail.get("lat") and trail.get("lon"):
                        trail_point = Point(float(trail["lon"]), float(trail["lat"]))
                        if isochrone_shape.contains(trail_point):
                            viable_trails.append(trail)
            else:
                viable_trails = trails
        else:
            st.error("❌ Isochrone filtering selected, but GPS coordinates are unavailable!")
            viable_trails = trails

    elif strategy == "GEOLOCATOR":
        location_value = profile.get("location_value")
        if location_value:
            bbox = invoke_geocoding_api(location_value)
            if bbox:
                st.info(f"🌍 Filtering trails inside region boundary: {location_value}...")
                for trail in trails:
                    t_lat = trail.get("lat")
                    t_lon = trail.get("lon")
                    if t_lat and t_lon:
                        lat_match = bbox["min_lat"] <= float(t_lat) <= bbox["max_lat"]
                        lon_match = bbox["min_lon"] <= float(t_lon) <= bbox["max_lon"]
                        if lat_match and lon_match:
                            viable_trails.append(trail)
            else:
                viable_trails = trails
        else:
            viable_trails = trails
    else:
        viable_trails = trails

    return viable_trails

TRAILS_FILE_PATH = "trail_dir/greek_trails_directory_enriched.json"

@st.cache_data(show_spinner=False)
def load_directory_cached():
    """
    Directly loads the static pre-compiled JSON trails registry database.
    Returns a tuple: (dict/list of trails_data, status_string)
    """
    try:
        if not os.path.exists(TRAILS_FILE_PATH):
            raise FileNotFoundError(f"Missing core database asset file target: '{TRAILS_FILE_PATH}'")
            
        with open(TRAILS_FILE_PATH, "r", encoding="utf-8") as f:
            trails_data = json.load(f)
            
        status_string = "READY"
        return trails_data, status_string
        
    except Exception as e:
        status_string = f"FAILED: Unexpected systemic read interruption. Error: {str(e)}"
        return [], status_string


def main():
    st.set_page_config(page_title="PathFinder: Find what you Feel", page_icon="🌲", layout="wide")
    st.title("🌲 PathFinder: Find what you feel")
    st.caption("Discover hidden gems in Greece's undiscovered beauty.")

    gps_raw = get_geolocation()
    gps_coords = None
    if gps_raw and "coords" in gps_raw:
        gps_coords = {
            "lat": gps_raw["coords"]["latitude"], 
            "lon": gps_raw["coords"]["longitude"]
        }

    trails_data, status_string = load_directory_cached()

    # Initialize Persistent Session State Variables
    if "messages" not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant", 
            "content": "Γειά σου! Welcome to PathFinder. 🌲 Where in Greece are you in the mood to explore today?"
        }]
        
    if "current_profile" not in st.session_state:
        st.session_state.current_profile = {
            "hiker_expertise": None,
            "hiker_intent": None,
            "location_value": None,
            "travel_mode": None,
            "max_travel_time": None,
            "spatial_strategy": "NONE", 
            "min_trail_duration_hours": None,
            "max_trail_duration_hours": None,
            "interests": []
        }

    # Live Sidebar JSON Inspector
    with st.sidebar:
        profile = st.session_state.current_profile

        st.subheader("🌐 Global Waymarked Registry")
        if "FAILED" in status_string:
            st.error(f"❌ {status_string}")
        else:
            st.success(f"✅ Loaded `{len(trails_data)}` Active Greek Trails!")
            
        st.divider()

        st.markdown("### 🛰️ Live Hardware GPS")
        if gps_coords:
            st.success(f"**Latitude (Lat):** `{gps_coords['lat']:.5f}`\n\n**Longitude (Lon):** `{gps_coords['lon']:.5f}`")
        else:
            st.warning("⚠️ **GPS Coordinates:** `null`\n\n*(Allow browser location access if prompted)*")
        
        st.markdown("### 🔍 Live JSON Data")
        st.json(profile)

        st.divider()
        if st.button("Reset Chat Session"):
            st.session_state.messages = [{
                "role": "assistant", 
                "content": "Γειά σου! Welcome to PathFinder. 🌲 Where in Greece are you in the mood to explore today?"
            }]
            st.session_state.current_profile = {
                "hiker_expertise": None, "hiker_intent": None, "location_value": None,
                "travel_mode": None, "max_travel_time": None, "spatial_strategy": "NONE",
                "min_trail_duration_hours": None, "max_trail_duration_hours": None, "interests": []
            }
            st.clear_cache()
            st.rerun()


    st.subheader("💬 Trail Profiler Chat")
        
    # Stream historical transcript logs visually inside the chat layout
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_input := st.chat_input("Tell me what you are planning..."):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("🕵️ Local Guide is thinking..."):

                # ==============================================================================
                # AGENT STATE DELTA INTERCEPTION LAYER
                # ==============================================================================
                try:
                    # Run your specialized gatekeeper agent task to spot pivots / mind-changes
                    state_delta = run_gatekeeper_agent(
                        user_input=user_input, 
                        current_profile=st.session_state.current_profile
                    )
                    
                    # 1. Execute state deletion for conflicting fields flagged by the agent
                    for field in state_delta.fields_to_remove:
                        st.session_state.current_profile.pop(field, None)
                        
                    # 2. Apply new modifications instantly
                    st.session_state.current_profile.update(state_delta.updated_profile_fields)
                    
                    # 3. Handle coordinate dropping if a geographic location pivot happened
                    if state_delta.reset_gps:
                        gps_coords = None  # Wipes local execution variable
                        if "gps_coords" in st.session_state:
                            st.session_state["gps_coords"] = None
                        
                        # Clear old cached files so stale results disappear from view
                        if "active_viable_trails" in st.session_state:
                            st.session_state["active_viable_trails"] = []
                            
                except Exception as e:
                    print(f"⚠️ Gatekeeper failed or skipped, running normal flow: {e}")
                
                # ==============================================================================

                full_history = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
                
                try:
                    # 1. Conversational Profiling: Extract what we can from this turn
                    crew_result = PathfinderCrew().run_profiling(full_history)
                    
                    if "profile" in crew_result and isinstance(crew_result["profile"], dict):
                        agent_extracted = crew_result["profile"]
                        
                        # Clean out null string placeholders
                        clean_extracted = {
                            k: v for k, v in agent_extracted.items() 
                            if v not in [None, "", "null", "None"]
                        }
                        
                        # Incremental state merge
                        st.session_state.current_profile.update(clean_extracted)

                        if isinstance(st.session_state.current_profile.get("interests"), str):
                            st.session_state.current_profile["interests"] = [st.session_state.current_profile["interests"]]

                    
                    questions_asked = sum(1 for m in st.session_state.messages if m["role"] == "assistant") - 1

                    profile = st.session_state.current_profile
                    strategy = profile.get("spatial_strategy", "NONE")
                    
                    if strategy == "NONE" or strategy is None:
                        strategy = "GEOLOCATOR"

                    # RECOMMEND TRAILS 
                   
                    if questions_asked >= 5:

                        # 1. Broad Spatial Isolation Pool
                        spatial_filtered_trails = filter_trails_spatial(
                            trails=trails_data, 
                            strategy=strategy, 
                            profile=profile, 
                            gps=gps_coords
                        )
                        
                        # Gather targeting parameters
                        target_score = profile.get("hiker_intent") if profile.get("hiker_intent") is not None else profile.get("hiker_expertise")
                        min_duration = profile.get("min_trail_duration_hours")
                        max_duration = profile.get("max_trail_duration_hours")
                        
                        # FILTER OUT BASED ON DISTANCE AND DIFFICULTY
                        base_viable_pool = []
                        for trail in spatial_filtered_trails:
                            
                            # Rough Filter: Keep trails close to difficulty target (tolerance buffer of 1 unit)
                            if target_score is not None and (abs(trail.get("custom_difficulty_score", 1) - target_score) > 1):
                                continue

                            # Parse trail duration features safely
                            trail_duration = trail.get("duration_hours")
                            if trail_duration is None:
                                dist_km = trail.get("distance_km", 0.0)
                                trail_duration = dist_km / 4.0 if dist_km > 0 else None

                            if trail_duration is not None:
                                trail_duration = float(trail_duration)
                                
                                # Dynamic Time Boundary Evaluation Check
                                if min_duration is not None and max_duration is not None:
                                    min_dur_val, max_dur_val = float(min_duration), float(max_duration)
                                    min_deviation, max_deviation = min(1.0, min_dur_val / 6.0), min(1.0, max_dur_val / 6.0)
                                    
                                    if not ((min_dur_val - min_deviation) <= trail_duration <= (max_dur_val + max_deviation)):
                                        continue
                                
                                elif max_duration is not None and trail_duration > float(max_duration):
                                    continue
                                        
                                elif min_duration is not None and trail_duration < float(min_duration):
                                    continue
                                
                            base_viable_pool.append(trail)

                        assistant_response = "Finding your ideal hike!"

                        # ==============================================================================
                        # SCORING ENGINE INSIDE THE VIABLE POOL GATING CHECK
                        # ==============================================================================
                        if base_viable_pool:
                            # A. Kickoff Analyst Agent to evaluate priority multipliers based on text context
                            with st.spinner("🧠 Analyst is calculating priority weights..."):
                                weights = PathfinderAnalystCrew().extract_multipliers(full_history)
                                diff_w = weights.get("difficulty_multiplier", 0.5)
                                dur_w = weights.get("duration_multiplier", 0.5)

                            # B. Process every base trail through the strict scoring math matrix
                            scored_trails_pool = []
                            for trail in base_viable_pool:
                                # Run the scoring logic function
                                metrics = calculate_trail_match_scores(
                                    trail=trail, 
                                    profile=profile, 
                                    difficulty_mult=diff_w, 
                                    duration_mult=dur_w
                                )

                                raw_penalty = metrics.get("raw_penalty", 0.0)
                                metrics["composite_score"] = metrics["composite_score"] - raw_penalty
                                
                                scored_trail = trail.copy()
                                scored_trail["match_analysis"] = metrics
                                scored_trails_pool.append(scored_trail)

                            # C. Sort the final pool in descending order based on composite matching values
                            final_ranked_trails = sorted(
                                scored_trails_pool, 
                                key=lambda x: x["match_analysis"]["composite_score"], 
                                reverse=True
                            )

                            # Commit structured data array back to operational session states
                            st.session_state["active_viable_trails"] = final_ranked_trails

                            assistant_response += f"\n\n**Analyst Multipliers Applied:**\n- Difficulty Weight: `{diff_w}`\n- Duration Weight: `{dur_w}`\n"
                            assistant_response += f"\n### 🥾 Ranked Trails list:\n"
                            
                            for trail in final_ranked_trails[:10]:  
                                name = trail.get("name", "Unnamed Route")
                                analysis = trail["match_analysis"]

                                # Fetch raw database values for display clarity
                                difficulty_num = trail.get("custom_difficulty_score", 1)
                                distance = trail.get("distance_km", "N/A")
                                density = analysis.get("density_val") or trail.get("regional_tourist_density", 0.0)
                                crowd_flag = ""
                                
                                if 1000 <= density < 2500:
                                    crowd_flag = " ⚠️ **[FLAG: High Crowding - Popular Excursion Zone]**"
                                elif 2500 <= density < 5000:
                                    crowd_flag = " 🚨 **[FLAG: Very High Crowding - Heavy Tourism Load]**"
                                elif density >= 5000:
                                    crowd_flag = " 🛑 **[FLAG: Extreme Crowding - Overtourism Saturated]**"


                                distance_str = f"{distance} km" if distance != "N/A" else "Unknown distance"

                                assistant_response += (
                                    f"- **{name}** ➔ **Match: {analysis['composite_score']*100:.1f}%**{crowd_flag}\n"
                                    f"(Diff Match: `{analysis['difficulty_match']}`, "
                                    f"Dur Match: `{analysis['duration_match']}` | est: `{analysis['calculated_duration']} hrs`)\n"
                                    f"  * *Trail Specs:* Difficulty Score: {difficulty_num}/6 | Est. Duration: `{analysis['calculated_duration']} hrs` ({distance_str}){crowd_flag}\n"
                                )
                        else:
                            st.session_state["active_viable_trails"] = []
                            
                            fallback_text = (
                                "🌲 Ach! Even the best explorers hit a dead end sometimes. "
                                "I cudgeled my local guide brain, but your current combination of "
                                "difficulty, duration, and regional constraints didn't turn up any "
                                "matches in our database.\n\n"
                                "Let's widen the horizon! If you are willing to look a little further "
                                "outside your target zone, or if we adjust your hiking time, I can "
                                "unlock a fresh batch of trails. **Let me know what you'd like to adjust!**"
                            )
                            
                            st.session_state.messages.append({"role": "assistant", "content": fallback_text})
                            st.markdown(fallback_text)
                    
                    else:
                        st.session_state["active_viable_trails"] = []
                        assistant_response = crew_result.get("response", "Tell me more about your ideal hike!")
                                        
                except Exception as e:
                    assistant_response = f"**Processing Error:** {str(e)}"
                
                st.markdown(assistant_response)
                st.session_state.messages.append({"role": "assistant", "content": assistant_response})
                time.sleep(0.1)
                st.rerun()


if __name__ == "__main__":
    main()