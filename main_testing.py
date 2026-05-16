import streamlit as st
from streamlit_js_eval import streamlit_js_eval as st_js, get_geolocation
import threading
from agents import PathfinderCrew, WaymarkedDirectoryManager

@st.cache_data(show_spinner=False)
def load_directory_cached():
    """
    Safely fetches and caches Greek trails. Bypasses threading-context 
    crashes on Azure containers by using Streamlit's native caching.
    """
    try:
        trails = WaymarkedDirectoryManager.fetch_all_greek_trails()
        if trails and len(trails) > 0:
            return trails, "READY"
        return [], "FAILED: Server returned 0 trails. Check rate-limits."
    except Exception as e:
        return [], f"FAILED: {str(e)}"

def invoke_isochrone_api(lat, lon, max_time, mode):
    """Placeholder: Replace with your actual Isochrone API call (e.g., OpenRouteService)"""
    st.info(f"🛰️ Calling Isochrone API for {mode} around ({lat}, {lon}) with {max_time} min limit...")
    # Returns a dummy boundary object for safety
    return {"type": "Polygon", "coordinates": []}

def invoke_geocoding_api(location_name):
    """Placeholder: Replace with your actual Geocoding API call (e.g., Nominatim)"""
    st.info(f"🌍 Calling Geocoding API to resolve bounding box for '{location_name}'...")
    return {"type": "BoundingBox", "bounds": []}

def filter_trails_spatial(trails, strategy, profile, gps):
    """Applies your requested hard spatial filtering logic to isolate viable trails"""
    viable_trails = []
    
    if not trails:
        return []

    if strategy == "ISOCHRONE":
        if gps and "lat" in gps and "lon" in gps:
            max_time = profile.get("max_travel_time") or 60  # default backup
            mode = profile.get("travel_mode") or "vehicle"
            
            # 1. Fetch your driving/walking polygon boundary
            polygon = invoke_isochrone_api(gps['lat'], gps['lon'], max_time, mode)
            
            # 2. Hard eliminate trails outside polygon
            st.write("🔍 Filtering trails based on travel time isochrone polygon...")
            for trail in trails:
                # TODO: Implement point-in-polygon math here (e.g., using shapely)
                # if is_point_in_polygon(trail.coords, polygon):
                #     viable_trails.append(trail)
                pass
            
            # Temporary mock assignment for visual feedback until shapely is configured
            viable_trails = trails[:2] 
        else:
            st.error("❌ Isochrone filtering selected, but GPS coordinates are unavailable!")
            viable_trails = trails

    elif strategy == "GEOLOCATOR":
        location_value = profile.get("location_value")
        if location_value:
            # 1. Resolve geographic bounding box area (Ignoring user coordinates completely)
            bounding_box = invoke_geocoding_api(location_value)
            
            # 2. Hard eliminate trails outside named bounds
            st.write(f"🔍 Filtering trails to match explicit region: {location_value}...")
            for trail in trails:
                # TODO: Implement bounding-box collision detection
                # if is_point_in_bbox(trail.coords, bounding_box):
                #     viable_trails.append(trail)
                pass
                
            viable_trails = trails[:3]  # Temporary mock assignment
        else:
            st.error("❌ Geolocator filtering selected, but no location value was extracted!")
            viable_trails = trails
            
    else:
        # Fallback if no strategy or unrecognizable string is supplied
        viable_trails = trails

    return viable_trails

def main():
    st.set_page_config(page_title="PathFinder: Find what you Feel", page_icon="🌲", layout="wide")
    st.title("🌲 PathFinder: Find what you feel")
    st.caption("Discover hidden gems in Greece's undiscovered beauty.")

    # Quietly checks the browser's HTML5 Geolocation API
    gps_raw = get_geolocation()
    gps_coords = None
    if gps_raw and "coords" in gps_raw:
        gps_coords = {
            "lat": gps_raw["coords"]["latitude"], 
            "lon": gps_raw["coords"]["longitude"]
        }

    # ---------------------------------------------------------
    # Phase 1: Initialize Persistent Session State Variables
    # ---------------------------------------------------------
    trails_data, status_string = load_directory_cached()

    if "messages" not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant", 
            "content": "Γειά σου! Welcome to PathFinder. 🌲 Where in Greece are you in the mood to explore today?"
        }]
        
    if "current_profile" not in st.session_state:
        st.session_state.current_profile = {
            "sac_ability": None,
            "sac_intent": None,
            "location_value": None,
            "travel_mode": None,
            "max_travel_time": None,
            "spatial_strategy": None,
            "min_trail_duration_hours": None,
            "max_trail_duration_hours": None,
            "interests": []
        }

    # ---------------------------------------------------------
    # Phase 2: Render Clean Live Sidebar JSON Inspector Only
    # ---------------------------------------------------------
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
                "sac_ability": None,
                "sac_intent": None,
                "location_value": None,
                "travel_mode": None,
                "max_travel_time": None,
                "spatial_strategy": None,
                "min_trail_duration_hours": None,
                "max_trail_duration_hours": None,
                "interests": []
            }
            st.clear_cache()
            st.rerun()

 # ---------------------------------------------------------
    # Phase 3: Conversational Back-and-Forth UI Loop
    # ---------------------------------------------------------
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_input := st.chat_input("Tell me what you are planning..."):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing profile clues, intent, and structural constraints..."):
                full_history = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
                
                try:
                    crew_result = PathfinderCrew().run_profiling(full_history)
                    
                    if "profile" in crew_result and isinstance(crew_result["profile"], dict):
                        # 🟢 STEP 1: Build a clean base schema with all values default to None
                        base_profile = {
                            "sac_ability": None,
                            "sac_intent": None,
                            "location_value": None,
                            "travel_mode": None,
                            "max_travel_time": None,
                            "spatial_strategy": None,
                            "min_trail_duration_hours": None,
                            "max_trail_duration_hours": None,
                            "interests": []
                        }
                        
                        # 🟢 STEP 2: Filter the incoming agent result to make sure we scrub literal "null" strings
                        agent_extracted = crew_result["profile"]
                        clean_extracted = {
                            k: v for k, v in agent_extracted.items() 
                            if v not in [None, "", "null", "None"]
                        }
                        
                        # 🟢 STEP 3: Merge incoming data into our clean base template
                        base_profile.update(clean_extracted)
                        
                        # 🟢 STEP 4: Completely OVERWRITE the state. 
                        # This strips old data and forces the sidebar JSON component to redraw cleanly!
                        st.session_state.current_profile = base_profile

                        strategy = st.session_state.current_profile.get("spatial_strategy")
                            
                        viable_trails = filter_trails_spatial(
                            trails=trails_data, 
                            strategy=strategy, 
                            profile=st.session_state.current_profile, 
                            gps=gps_coords
                        )
                        
                        if viable_trails:
                            st.success(f"🎯 Isolated `{len(viable_trails)}` viable trails matching spatial rules!")
                            # To display filtered entries on screen:
                            st.write(viable_trails)
                    
                    assistant_response = crew_result.get("response", "Got it! Looking into the area options.")
                                        
                except Exception as e:
                    assistant_response = f"⚠️ **Error parsing structured output:** {str(e)}"
                
                st.markdown(assistant_response)
                st.session_state.messages.append({"role": "assistant", "content": assistant_response})
                st.rerun()

if __name__ == "__main__":
    main()