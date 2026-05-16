import streamlit as st
from streamlit_js_eval import streamlit_js_eval as st_js, get_geolocation
import threading
from agents import PathfinderCrew, WaymarkedDirectoryManager

def load_directory_async():
    """Worker function to scrape all Greek trails concurrently without stalling the UI thread"""
    # 🟢 Safety check: If already ready, do not spawn another request
    if st.session_state.get("directory_status") == "READY":
        return
        
    try:
        trails = WaymarkedDirectoryManager.fetch_all_greek_trails()
        
        if trails and len(trails) > 0:
            st.session_state.master_trail_directory = trails
            st.session_state.directory_status = "READY"
        else:
            # 🟢 Handles empty API returns gracefully
            st.session_state.directory_status = "FAILED: Server returned 0 trails. Check rate-limits."
            
    except Exception as e:
        # 🟢 Catch any network drops or timeouts and show them in the sidebar
        st.session_state.directory_status = f"FAILED: {str(e)}"

def main():
    st.set_page_config(page_title="PathFinder: Find what you Feel", page_icon="🌲", layout="wide")
    st.title("🌲 PathFinder: Find what you feel")
    st.caption("Discover hidden gems in Greece's undiscovered beauty.")

    if "directory_status" not in st.session_state:
        st.session_state.master_trail_directory = []
        st.session_state.directory_status = "INITIALIZING"
        
        # Launch background execution
        t = threading.Thread(target=load_directory_async, daemon=True)
        t.start()
    # Quietly checks the browser's HTML5 Geolocation API
    gps_coords = get_geolocation()

    # ---------------------------------------------------------
    # Phase 1: Initialize Persistent Session State Variables
    # ---------------------------------------------------------
    if "messages" not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant", 
            "content": "Γειά σου! Welcome to PathFinder. 🌲 Where in Greece are you in the mood to explore today?"
        }]
        
    if "current_profile" not in st.session_state:
        # 🟢 UPDATED: Reflects the updated state parameters starting entirely clean/null
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
        if st.session_state.directory_status == "INITIALIZING":
            st.warning("🔄 Fetching all Greek Waymarked Trails in background...")
        elif "FAILED" in st.session_state.directory_status:
            st.error(f"❌ {st.session_state.directory_status}")
        else:
            st.success(f"✅ Loaded `{len(st.session_state.master_trail_directory)}` Active Greek Trails!")
            
        st.divider()

        st.markdown("### 🛰️ Live Hardware GPS")
        if gps_coords and "coords" in gps_coords:
            lat = gps_coords["coords"]["latitude"]
            lon = gps_coords["coords"]["longitude"]
            st.success(f"**Latitude (Lat):** `{lat:.5f}`\n\n**Longitude (Lon):** `{lon:.5f}`")
            
            # Map values explicitly so your backend mapping pipeline variables are ready
            gps_coords = {"lat": lat, "lon": lon}
        else:
            st.warning("⚠️ **GPS Coordinates:** `null`\n\n*(Check browser permissions or allow location access if prompted)*")
        
        # Displaying exclusively the raw structural JSON inspector data block
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
                        
                        if strategy == "ISOCHRONE" and gps_coords:
                            # This block triggers the override logic
                            st.info(f"⚡ Pipeline Trigger: Generating Isochrone boundary polygon from baseline coordinates [{gps_coords['lat']}, {gps_coords['lon']}] for a {st.session_state.current_profile['max_travel_time']}-minute drive.")
                            # boundary_polygon = invoke_isochrone_api(gps_coords['lat'], gps_coords['lon'], st.session_state.current_profile['max_travel_time'], st.session_state.current_profile['travel_mode'])
                            
                        elif strategy == "GEOLOCATOR":
                            st.info(f"🌍 Pipeline Trigger: Isochrone bypassed. Resolving bounding box for explicit static named region: '{st.session_state.current_profile['location_value']}'.")
                            # boundary_polygon = invoke_geocoding_api(st.session_state.current_profile['location_value'])
                    
                    assistant_response = crew_result.get("response", "Got it! Looking into the area options.")
                                        
                except Exception as e:
                    assistant_response = f"⚠️ **Error parsing structured output:** {str(e)}"
                
                st.markdown(assistant_response)
                st.session_state.messages.append({"role": "assistant", "content": assistant_response})
                st.rerun()

if __name__ == "__main__":
    main()