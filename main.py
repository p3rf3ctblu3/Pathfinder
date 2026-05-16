import streamlit as st
from agents import PathfinderCrew
from core_logic import apply_hard_filters, calculate_final_rankings
from utils import load_initial_cache  # Assuming load_initial_cache handles cached database loading

def main():
    st.set_page_config(page_title="PathFinder: Find what you Feel", page_icon="🌲", layout="wide")
    st.title("🌲 PathFinder: Find what you Feel")
    
    # ---------------------------------------------------------
    # Phase 1: Initialize Persistent Session State Variables
    # ---------------------------------------------------------
    if "messages" not in st.session_state:
        st.session_state.messages = []
        
    if "raw_trails_pool" not in st.session_state:
        # Load your master local cache once so we don't spam APIs on every chat keystroke
        st.session_state.raw_trails_pool = load_initial_cache()   # CALL WAYMARKED TRAIL API 
        
    if "current_profile" not in st.session_state:
        # Balanced defaults incorporating the flexible transport metrics
        st.session_state.current_profile = {
            "sac_ceiling": 2,
            "location_type": "region",
            "location_value": "Attica",
            "travel_mode": "car",        # Dynamic: 'car', 'foot', 'bicycle'
            "max_travel_time": 60,       # In minutes
            "min_time": 0.5,
            "max_time": 4.0,
            "interests": []
        }

    # ---------------------------------------------------------
    # Phase 2: Render Live Deterministic Sidebar Dashboard
    # ---------------------------------------------------------
    with st.sidebar:
        st.subheader("⚙️ Active Deterministic Filters")
        profile = st.session_state.current_profile
        
        # Dynamically set transport emojis and labels based on active user state
        mode_labels = {"car": "🚗 Drive Time", "foot": "🥾 Walk Time", "bicycle": "🚲 Bike Time"}
        active_label = mode_labels.get(profile.get('travel_mode', 'car'), "🕒 Travel Time")
        
        st.write(f"**Target Location:** {profile.get('location_value', 'Not Specified')}")
        st.write(f"**Location Type:** {profile.get('location_type', 'region')}")
        st.write(f"**{active_label}:** {profile.get('max_travel_time', 60)} mins")
        st.write(f"**SAC Safety Limit:** T{profile.get('sac_ceiling', 2)}")
        if profile.get("interests"):
            st.write(f"**Tracked Interests:** {', '.join(profile['interests'])}")

    # ---------------------------------------------------------
    # Phase 3: Main Chat Interface Component
    # ---------------------------------------------------------
    # Render all historic messages inside the scrollable chat frame
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Collect conversational multi-turn user prompt
    if user_input := st.chat_input("Tell me about your ideal hike..."):
        # Append and render user statement instantly
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Process conversation using a flexible Profiler Agent
        with st.chat_message("assistant"):
            with st.spinner("Processing context changes..."):
                # Pass the complete conversation sequence to catch context corrections
                full_history = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
                
                # Kick off the extraction task, updating requirements and tracking transport modes
                crew_result = PathfinderCrew().run_profiling(full_history)  # -----------IMPLEMENT TASK !!!-------------
                
                # Merge the extracted intelligence dynamically straight into your session profile!
                if "profile" in crew_result:
                    st.session_state.current_profile.update(crew_result["profile"])
                
                # Print assistant text or request clarification
                assistant_response = crew_result.get("response", "Analyzing constraints...")
                st.markdown(assistant_response)
                st.session_state.messages.append({"role": "assistant", "content": assistant_response})
                
                # Force a page rerun to update the sidebar values instantly if profile states shifted
                st.rerun()

    # ---------------------------------------------------------
    # Phase 4: Parallel Deterministic Extraction Loop
    # ---------------------------------------------------------
    # This runs seamlessly in the background on every structural script reload.
    # It continuously filters against your local cached library.
    viable_trails = apply_hard_filters(
        st.session_state.raw_trails_pool, 
        st.session_state.current_profile
    )

# ---------------------------------------------------------
    # Phase 5: Soft-Weight Scoring Engine & Intelligent Presentation
    # ---------------------------------------------------------
    final_shortlist = calculate_final_rankings(viable_trails, st.session_state.current_profile)

    if final_shortlist:
        st.subheader(f"📍 Top Recommendations matched to your 'Vibe'")
        # render_ui_cards(final_shortlist)
    else:
        # WE NEVER ACTUALLY WANT TO SEE THIS IN THE DEMO
        st.warning("⚠️ No trails perfectly match your active criteria.")
        
        # Pull current profile constraints to calculate relative adjustments
        profile = st.session_state.current_profile
        current_travel_time = profile.get("max_travel_time", 60)
        current_min_time = profile.get("min_time", 0.5)
        current_max_time = profile.get("max_time", 4.0)
        current_sac = profile.get("sac_ceiling", 2)
        mode_noun = "walk" if profile.get("travel_mode") == "foot" else "drive"
        
        # 1. Calculate relative scaling buffers instead of hardcoding
        suggested_travel_time = int(current_travel_time * 1.5)  # Scale out by 50%
        suggested_min_time = max(0.0, current_min_time - 0.5)  # Lower the floor slightly
        suggested_max_time = current_max_time + 1.5            # Raise the ceiling
        
        suggestions = []
        
        # 2. Build recommendations dynamically based on active values
        suggestions.append(
            f"• **Expand your travel window:** You currently have a maximum {mode_noun} time of **{current_travel_time} minutes**. "
            f"Would you be open to expanding that to **{suggested_travel_time} minutes** to find trails a bit further out?"
        )
        
        suggestions.append(
            f"• **Loosen duration constraints:** Your current timeframe is set between **{current_min_time} and {current_max_time} hours**. "
            f"Widen your flexibility to something like **{suggested_min_time} to {suggested_max_time} hours** to reveal more tracks."
        )
        
        if current_sac < 4:
            suggestions.append(
                f"• **Adjust trail difficulty:** Your current ceiling is locked at an SAC **T{current_sac}** limit. "
                f"Letting me include **T{current_sac + 1}** routes would open up additional terrain choices in this area."
            )

        # Present the customized conversational feedback
        st.markdown(f"""
        The trail network around **{profile.get('location_value', 'your area')}** is proving to be a bit tight for these exact constraints. 
        
        No worries though! Just tell me what you want to change right here in the chat. You could say something like:
        """)
        
        for sug in suggestions:
            st.markdown(sug)

if __name__ == "__main__":
    main()--