import streamlit as st
from streamlit_js_eval import streamlit_js_eval as st_js, get_geolocation
import json
from agents import PathfinderCrew, PathfinderAnalystCrew, run_gatekeeper_agent
import os 
import time 
from utils import calculate_trail_match_scores, filter_trails_spatial

TRAILS_FILE_PATH = "greek_trails_directory_enriched.json"

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

    trails_data, status_string = load_directory_cached()

    gps_raw = get_geolocation()
    gps_coords = None
    if gps_raw and "coords" in gps_raw:
        gps_coords = {
            "lat": gps_raw["coords"]["latitude"], 
            "lon": gps_raw["coords"]["longitude"]
        }

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


    st.subheader("🦉 Your Local Guide")
        
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

                # AGENT STATE DELTA INTERCEPTION LAYER
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
                

                full_history = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
                
                try:
                    # Conversational Profiling
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

                    # Calculate exactly how many questions the bot has asked so far.
                    # We count the 'assistant' roles in history, minus 1 to ignore the initial welcome message greeting.
                    questions_asked = sum(1 for m in st.session_state.messages if m["role"] == "assistant") - 1

                    # 2. Extract state variables for our strict Multi-Gate Check
                    profile = st.session_state.current_profile
                    strategy = profile.get("spatial_strategy", "NONE")
                    
                    # Fallback strategy adjustment if the LLM didn't choose one but we reached the question limit
                    if strategy == "NONE" or strategy is None:
                        strategy = "GEOLOCATOR"

                    # RECOMMEND TRAILS 
                    if questions_asked >= 5:
                        
                        # Broad Spatial Isolation Pool
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

                        # SCORING ENGINE INSIDE THE VIABLE POOL GATING 
                        if base_viable_pool:
                            # A. Kickoff Analyst Agent to evaluate priority multipliers based on text context
                            with st.spinner("Finding your myth in Greece..."):
                                weights = PathfinderAnalystCrew().extract_multipliers(full_history)
                                diff_w = weights.get("difficulty_multiplier", 0.5)
                                dur_w = weights.get("duration_multiplier", 0.5)
                                int_w = weights.get("interests_multiplier", 0.5)

                            # B. Process every base trail through the scoring math matrix
                            scored_trails_pool = []
                            for trail in base_viable_pool:
                                metrics = calculate_trail_match_scores(
                                    trail=trail, 
                                    profile=profile, 
                                    difficulty_mult=diff_w, 
                                    duration_mult=dur_w,
                                    interests_mult=int_w
                                )
                                
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

                            assistant_response += f"\n### 🥾 Your Perfect Trails list:\n"
                            
                            for trail in final_ranked_trails[:10]:  # Limit print layout rendering block to top 10 results
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


                                # Format distance text if it exists
                                distance_str = f"{distance} km" if distance != "N/A" else "Unknown distance"

                                assistant_response += (
                                    f"- **{name}** "
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