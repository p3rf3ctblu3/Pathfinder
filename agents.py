import json
import os
import requests
from typing import List, Optional
from pydantic import BaseModel, Field
from crewai import Agent, Crew, Process, Task, LLM
from dotenv import load_dotenv

load_dotenv()

gemini_key = os.environ.get("GEMINI_API_KEY")

shared_llm = LLM(
    model="gemini/gemini-2.5-flash", 
    temperature=0.0, # 🟢 CRITICAL: Set to 0.0 to eliminate ALL creative guessing/hallucinations
    api_key=gemini_key 
)

# ==============================================================================
# PHASE 1: Zero-Hallucination User Profile Schema
# ==============================================================================
class UserProfileSchema(BaseModel):
    # 🟢 FORCE default=None and explicit "MUST be null" instructions inside descriptions
    sac_ability: Optional[int] = Field(
        default=None, 
        description="The hiker's permanent fitness ceiling (1-6). CRITICAL: If the chat history does not explicitly state or clearly imply their experience level, you MUST output null."
    )
    sac_intent: Optional[int] = Field(
        default=None, 
        description="The target difficulty for this specific session (1-6). CRITICAL: If they haven't requested a specific difficulty or intensity yet, you MUST output null."
    )
    
    # SPATIAL TRACKING ATTRIBUTES
    location_value: Optional[str] = Field(
        default=None, 
        description="A explicit place or region name mentioned by the user (e.g., 'Attica', 'Thessaloniki')."
    )
    max_travel_time: Optional[int] = Field(
        default=None, 
        description="The maximum transit duration specified by the user in minutes (e.g., '30 minutes')."
    )
    travel_mode: Optional[str] = Field(
        default=None, 
        description="Must be some vehicle (e.g. car) or 'foot' ONLY if a relative transit limit was explicitly requested."
    )
    spatial_strategy: Optional[str] = Field(
        default=None, 
        description=(
            "CRITICAL DETERMINATION. Must be strictly one of these string literal tokens:\n"
            "- 'ISOCHRONE': If the user requests a time/distance limitation relative to their location (e.g., '30 mins from here').\n"
            "- 'GEOLOCATOR': If they named a static destination territory without relative constraints (e.g., 'I want to hike in Attica').\n"
            "- null: If they have not given any geographic hints yet."
        )
    )

    min_trail_duration_hours: Optional[float] = Field(
        default=None, 
        description="The lowest acceptable hike time limit in hours. If not specified, you MUST output null."
    )
    max_trail_duration_hours: Optional[float] = Field(
        default=None, 
        description="The absolute upper hike time limit in hours. If not specified, you MUST output null."
    )
    interests: List[str] = Field(
        default_factory=list, 
        description="List of explicit string keywords representing user interests/features. If none are mentioned, return an empty array []."
    )

class ExtractionResultSchema(BaseModel):
    profile: UserProfileSchema
    response: str = Field(
        ..., 
        description="A warm, casual 1-2 sentence response. Acknowledge what they said, then naturally ask for just ONE missing piece of info."
    )

# ==============================================================================
# PHASE 2: Waymarked Master Directory Generator (Direct Cache Builder)
# ==============================================================================
class WaymarkedDirectoryManager:
    @staticmethod
    def build_local_directory_cache() -> str:
        """
        Queries the Overpass API once to fetch every official waymarked hiking route 
        within the national borders of Greece and compiles them into a local JSON cache.
        """
        cache_filename = "greek_trails_directory.json"
        
        # Pulling exact relations matching waymarkedtrails.org hiking specifications
        overpass_query = """
        [out:json][timeout:90];
        area["ISO3166-1"="GR"]["admin_level"="2"]->.greece;
        (relation["type"="route"]["route"~"hiking|foot|walking"](area.greece););
        out tags center;
        """
        url = "https://overpass-api.de/api/interpreter"
        
        try:
            response = requests.post(url, data={"data": overpass_query}, timeout=60)
            if response.status_code == 200:
                elements = response.json().get("elements", [])
                processed_directory = []
                
                for el in elements:
                    tags = el.get("tags", {})
                    center = el.get("center", {})
                    
                    processed_directory.append({
                        "osm_id": el.get("id"),
                        "name": tags.get("name", tags.get("ref", f"Waymarked Route {el.get('id')}")),
                        "sac_scale": tags.get("sac_scale", "hiking"),
                        "distance_km": float(tags.get("distance")) if tags.get("distance") else None,
                        "lat": center.get("lat"),
                        "lon": center.get("lon"),
                        "description": tags.get("description", "")
                    })
                
                with open(cache_filename, "w", encoding="utf-8") as f:
                    json.dump(processed_directory, f, ensure_ascii=False, indent=2)
                return f"SUCCESS_CREATED_{len(processed_directory)}_ENTRIES"
        except Exception as e:
            return f"CACHE_GENERATION_FAILED: {str(e)}"
        return "NO_DATA_RETURNED"


# ==============================================================================
# PHASE 3: Define your Factory Agent
# ==============================================================================
class PathfinderAgents:
    def user_profiler(self):
        return Agent(
            role="User Profiler",
            goal="Extract real-time filtering parameters from text transcripts without inventing or assuming details.",
            backstory=(
                "You are a strict data verification engine. You have zero imagination. "
                "If the user has not explicitly typed information or clearly implied it during the chat history, "
                "you consider filling that field to be a system failure. You default to null for every value "
                "unless proof exists in the transcript."
            ),
            llm=shared_llm,
            verbose=True
        )


# ==============================================================================
# PHASE 4: The Crew Orchestrator Called by main.py
# ==============================================================================
class PathfinderCrew:
    def __init__(self):
        self.agent_factory = PathfinderAgents()

    def run_profiling(self, full_history: str) -> dict:
        profiler = self.agent_factory.user_profiler()

        profiling_task = Task(
            description=(
                "Read through the current conversation history with the hiker:\n"
                "--------------------------------------------------\n"
                f"{full_history}\n"
                "--------------------------------------------------\n\n"
                "Your Rules for Mapping Implicit Data:\n"
                "1. STRICT ZERO-HALLUCINATION GUARDRAILS:\n"
                "   - You are generating search query parameters. Guessing or inventing values will completely ruin the search results.\n"
                "   - If the user explicitly states they do not care about the location, or says 'anywhere in Greece', set `location_value` = 'Greece' and set `spatial_strategy` = 'GEOLOCATOR'.\n"
                "   - If the user ONLY says a location like 'Attica', then `location_value` must be 'Attica', and EVERY other parameter inside the profile block MUST BE null (interests should be []).\n"
                "   - Do not guess transit modes, do not guess default hiking capabilities, and do not fill out duration hours unless words about time were explicitly typed.\n\n"
                "2. SAC_ABILITY VS SAC_INTENT CALCULATOR:\n"
                "   - Only map these if they mention experience or difficulty. Otherwise leave as null.\n"
                "   - If an elite/advanced hiker explicitly asks for something 'easy', 'flat', or 'relaxing', set `sac_intent` to exactly one or two levels BELOW their `sac_ability` (e.g., ability=6, intent=4).\n"
                "   - If a beginner explicitly requests a 'big challenge', set `sac_intent` exactly one level ABOVE their true `sac_ability` (e.g., ability=2, intent=3).\n\n"
                "3. DURATION RANGE PARSING RULES:\n"
                "   - If the user explicitly states they do not care about the duration, or says 'any duration' / 'no limit', set `min_trail_duration_hours` = 0.0 and `max_trail_duration_hours` = 16.0.\n"
                "   - 'around 1-2 hours' -> min_trail_duration_hours = 1.0, max_trail_duration_hours = 2.0.\n"
                "   - 'around 2 hours' -> min_trail_duration_hours = 1.5, max_trail_duration_hours = 2.5.\n"
                "   - 'at most X hours' -> min_trail_duration_hours=null, max_trail_duration_hours=X.\n"
                "   - 'at least X hours' -> min_trail_duration_hours=X, max_trail_duration_hours=null."
                "4. SPATIAL OVERRIDE HIERARCHY RULES:\n"
                "   - If the user says '30 minutes from here by car', set `max_travel_time` = 30, `travel_mode` = 'car', and set `spatial_strategy` = 'ISOCHRONE'.\n"
                "   - If the user only mentions a static area like 'Attica', set `location_value` = 'Attica', and set `spatial_strategy` = 'GEOLOCATOR'.\n"
                "   - OVERRIDE RULE: If the user names an area AND requests a time boundary relative to 'here' simultaneously (e.g., 'I am in Attica, look for things 30 mins from here')\n" 
                "   -, the Isochrone parameter takes complete precedent. Set `spatial_strategy` = 'ISOCHRONE', capture the time constraints, and keep the location string.\n"
            ),
            expected_output="Structured JSON matching the updated profile blueprint and a concise 1-2 sentence response.",
            agent=profiler,
            output_json=ExtractionResultSchema
        )

        crew = Crew(
            agents=[profiler],
            tasks=[profiling_task],
            process=Process.sequential
        )

        try:
            result = crew.kickoff()
            
            if hasattr(result, 'json_output') and result.json_output:
                raw_data = result.json_output
                # Keep fields explicitly clean for Streamlit parsing
                if "profile" in raw_data and raw_data["profile"]:
                    raw_data["profile"] = {k: v for k, v in raw_data["profile"].items() if v not in [None, "null", "None"]}
                return raw_data
            
            if isinstance(result.raw, str):
                raw_data = json.loads(result.raw)
                if "profile" in raw_data and raw_data["profile"]:
                    raw_data["profile"] = {k: v for k, v in raw_data["profile"].items() if v not in [None, "null", "None"]}
                return raw_data
                
        except Exception as e:
            print(f"Extraction parsing error: {e}")
            
        return {
            "profile": {}, 
            "response": "That sounds like an adventure! Tell me, how much time do you have for this hike?"
        }