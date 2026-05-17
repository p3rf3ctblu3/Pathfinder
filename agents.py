import json
import os
import requests
from typing import List, Optional, Dict, Any
from crewai import Agent, Crew, Process, Task, LLM
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

# groq_key = os.environ.get("GROQ_API_KEY")

# shared_llm = LLM(
#     model="groq/llama-3.3-70b-versatile",
#     temperature=0.0,                   
#     api_key=groq_key 
# )

gemini_key = os.environ.get("GEMINI_API_KEY")

shared_llm = LLM(
    model="gemini/gemini-2.5-flash",    
    temperature=0.0,                    
    api_key=gemini_key 
)

#  User Profile Schema
class UserProfileSchema(BaseModel):
    hiker_expertise: Optional[int] = Field(
        default=None, 
        description="The hiker's permanent fitness ceiling (1-6). CRITICAL: If the chat history does not explicitly state or clearly imply their experience level, you MUST output null."
    )
    hiker_intent: Optional[int] = Field(
        default=None, 
        description="The target difficulty for this specific session (1-6). CRITICAL: If they haven't requested a specific difficulty or intensity yet, you MUST output null."
    )
    location_value: Optional[str] = Field(
        default=None, 
        description="An explicit place or region name mentioned by the user (e.g., 'Attica', 'Thessaloniki')."
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
        description="A warm, rich, enthusiastic response! Acknowledge what they said without repeating explicitly, then naturally ask for just ONE missing piece of info."
    )

class WeightAnalysisSchema(BaseModel):
    difficulty_multiplier: float = Field(..., description="A float value between 0.0 and 1.0 reflecting how strictly the trail difficulty matters to the user.")
    duration_multiplier: float = Field(..., description="A float value between 0.0 and 1.0 reflecting how strictly the duration window matters to the user.")
    interests_multiplier: float = Field(..., description="A float value between 0.0 and 1.0 reflecting how heavily specific thematic preferences, historical interests, or niche scenery features should weight the match.")

class ProfileUpdateSchema(BaseModel):
    updated_profile_fields: Dict[str, Any] = Field(
        description="Dictionary of keys and values to add or update in the user profile."
    )
    fields_to_remove: List[str] = Field(
        description="List of profile keys that conflict with the new user intent and must be deleted."
    )
    reset_gps: bool = Field(
        description="Set to True if the user changed the physical location/region of their hike."
    )

# AGENTS

def run_gatekeeper_agent(user_input: str, current_profile: dict) -> ProfileUpdateSchema:
    """
    An isolated, specialized agent task that handles user state mutations.
    """
    gatekeeper_prompt = f"""
    You are a precise Profile Gatekeeper Agent for a hiking application.
    Your sole task is to compare a user's new message against their current profile state
    and determine if they are changing their mind, correcting a parameter, or pivoting destinations.

    Current Profile State: {current_profile}
    New User Message: "{user_input}"

    Instructions:
    - If they change location (e.g., 'Athens instead of Corfu'), update target_region and set reset_gps to True.
    - If they change duration (e.g., 'make it shorter'), update max_trail_duration_hours and list 'min_trail_duration_hours' in fields_to_remove if they conflict.
    - If they change difficulty, adjust hacker_expertise or hiker_intent.
    """
    
    structured_llm = shared_llm.with_structured_output(ProfileUpdateSchema)
    
    try:
        agent_delta = structured_llm.invoke(gatekeeper_prompt)
        return agent_delta
    except Exception:
        return ProfileUpdateSchema(updated_profile_fields={}, fields_to_remove=[], reset_gps=False)


class PathfinderAgents:
    def user_profiler(self) -> Agent:
        return Agent(
            role="Expert Local Greek Hiking Guide",
            goal=(
                "Engage the hiker in a warm, enthusiastic conversation to naturally discover "
                "their trail preferences (intent, expertise, scenic interests, duration, and location) "
                "while extracting accurate profile data behind the scenes."
            ),
            backstory=(
                "You are an incredibly warm, creative, and enthusiastic local Greek hiking guide. "
                "You treat every hiker like an old friend visiting your homeland. You don't interrogate "
                "people; instead, you weave your questions into narrative warmth.\n"
                "While your conversational heart is bursting with hospitality and creativity, your analytical "
                "mind is sharp: you carefully map their answers to the structured profile fields. If a user "
                "explicitly mentions they don't care about a specific metric, you gracefully leave it as null. "
                "You never stop asking charming, engaging questions until you have successfully explored all "
                "four core pillars of their dream hike. Don't be overly verbose."
            ),
            llm=shared_llm,
            verbose=True
        )

    def intent_analyst(self) -> Agent:
        return Agent(
            role="Hiker Intent Analyst",
            goal="Analyze conversation history to determine user preferences and calculate importance multipliers.",
            backstory=(
                "You are an analytical psychologist specializing in outdoor recreation behavior. "
                "Your job is to read the entire chat transcript and determine how uncompromising the user is "
                "about different variables. For example, if a user emphasizes 'I absolutely cannot hike "
                "more than 2 hours' but says 'I don't really care about the difficulty', you will assign a "
                "much higher multiplier weight to duration than difficulty. You output precise importance "
                "multipliers between 0.0 and 1.0."
            ),
            llm=shared_llm,
            verbose=True
        )


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
                "Your Rules for Mapping Implicit Data & Setting Conversational Attitude:\n\n"
                "1. TONAL IDENTITY, CREATIVITY, & EMPATHY (THE 'LOCAL GUIDE' PERSONA):\n"
                "   - You are an incredibly friendly, warm, and highly creative local Greek hiking guide. You are NOT an interrogation machine.\n"
                "   - NEVER parrot back what the user says verbatim. Acknowledge choices with narrative warmth: 'Ah, an afternoon stroll among the gnarled olive groves sounds like absolute magic! Let's find you that perfect breeze...'\n"
                "   - READ BETWEEN THE LINES (IMPLICIT STATEMENT PARSING):\n"
                "     * If the user says 'My feet are killing me' or 'I'm recovering from a knee injury', immediately deduce that they need gentle terrain. Set `hiker_intent` and `hiker_expertise` to 1, and offer comfort.\n"
                "     * If they say 'I want to capture the perfect golden hour light over the sea', instantly tag their `interests` as ['photography'].\n\n"
                "2. HARD OVERRIDES FOR DIFFICULTIES & ABILITIES:\n"
                "   - If the user explicitly requests a specific difficulty style (e.g., 'I want an easy hike'), DO NOT ask them about their baseline capability or background.\n"
                "   - RULE: An explicit request for an easy trail completely bypasses dynamic ability checking. Instantly set BOTH `hiker_intent` and `hiker_expertise` to the exact same low-tier level (Level 1 or 2 depending on context).\n"
                "   - TRANSLATION MATRIX:\n"
                "     * Beginner, amateur, casual walker, 'done 1-3 hikes' -> Level 1 or 2.\n"
                "     * Regular hiker, good fitness -> Level 3 or 4.\n"
                "     * Advanced, alpine, elite climber -> Level 5 or 6.\n"
                "   - INTENT ADJUSTMENT: If an amateur (expertise 1-2) explicitly requests a 'massive challenge', keep expertise at 1-2, but set `hiker_intent` to 3 or 4.\n\n"
                "3. SPATIAL OVERRIDE HIERARCHY & REDUNDANCY SILENCING:\n"
                "   - If the user provides a relative restriction based on time or distance (e.g., 'Give me something 45 minutes from here by car'), DO NOT ASK THEM WHERE THEY ARE.\n"
                "     * For time expressions ('X minutes from here'): Set `spatial_strategy` = 'ISOCHRONE', capture `max_travel_time` = X, and extract `travel_mode` ('car', 'foot').\n"
                "   - If they state they do not care about the location or say 'anywhere in Greece', set `spatial_strategy` = 'GEOLOCATOR'. Keep a field value explicitly as `null` if they state they 'don't care' about that specific metric.\n\n"
                "4. COMPULSORY CORE ACQUISITION GATES:\n"
                "   - CRITICAL: You must explicitly ask about or address all 5 pillars of the hike profile at least once during the conversation:\n"
                "     A) Hiker Intent, B) Hiker Expertise, C) Scenic Interests, D) Desired Duration, E) Starting Location.\n"
                "   - If the user says 'I don't care', leave that field value as null, but count it as successfully asked/addressed.\n\n"
                "5. STRICT CONVERSATIONAL DYNAMICS & COMPLETION SIGNAL:\n"
                "   - Keep asking warm, creative, and enthusiastic questions until you have brought up all 5 dimensions listed in Rule 4."
            ),
            expected_output="Structured JSON matching the profile schema, along with a warm, friendly response (1-3 sentences max) prompting ONLY for fields that haven't been discussed yet.",
            agent=profiler,
            output_json=ExtractionResultSchema
        )

        crew = Crew(agents=[profiler], tasks=[profiling_task], process=Process.sequential)

        try:
            result = crew.kickoff()
            if hasattr(result, 'json_output') and result.json_output:
                raw_data = result.json_output
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


class PathfinderAnalystCrew:
    def __init__(self):
        self.agent_factory = PathfinderAgents()

    def extract_multipliers(self, chat_history: str) -> dict:
        analyst = self.agent_factory.intent_analyst()

        analysis_task = Task(
            description=(
            f"Analyze the following chat history transcript between our guide and a hiker:\n"
                f"--------------------------------------------------\n"
                f"{chat_history}\n"
                f"--------------------------------------------------\n\n"
                "Evaluate how uncompromising or flexible the user is about their requested hiking variables:\n"
                "1. If they stress strict constraints on distance/time thresholds, raise the duration_multiplier.\n"
                "2. If they stress fitness thresholds, steep inclines, or basic walking limits, raise the difficulty_multiplier.\n"
                "3. If they express strong enthusiasm, specific thematic desires (e.g., mythology, archaeology, coastal views), "
                "or strict dealbreakers regarding trail features, raise the interests_multiplier.\n\n"
                "Output rules:\n"
                "- You MUST output a raw structured JSON object matching the requested schema.\n"
                "- The difficulty_multiplier, duration_multiplier, and interests_multiplier values must be floats between 0.0 and 1.0."
            ),
            expected_output="A structured JSON format payload holding keys 'difficulty_multiplier' and 'duration_multiplier'.",
            agent=analyst,
            output_json=WeightAnalysisSchema
        )

        crew = Crew(agents=[analyst], tasks=[analysis_task], process=Process.sequential)

        try:
            result = crew.kickoff()
            if hasattr(result, 'json_output') and result.json_output:
                return result.json_output
            
            if isinstance(result.raw, str):
                return json.loads(result.raw)
        except Exception as e:
            print(f"Analyst extraction parsing error: {e}")
            
        # Standard fallback weights if processing hits an exceptional network block
        return {"difficulty_multiplier": 0.5, "duration_multiplier": 0.5, "interests_multiplier": 0.5}