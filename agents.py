from crewai import Agent

class PathfinderAgents:
    def user_profiler(self):
        return Agent(
            role="User Profiling Specialist",
            goal="Extract fitness, intent, and location context into JSON.",
            backstory="Expert in human physiology and conversational analysis.", # [cite: 19, 21]
            verbose=True
        )

    def conditions_analyst(self):
        return Agent(
            role="Real-Time Conditions Analyst",
            goal="Verify trail safety via Reddit, news, and weather APIs.", # [cite: 30, 35]
            backstory="A safety officer who cross-references web reports with RAG logic." # [cite: 83, 97]
        )

    def recommender(self):
        return Agent(
            role="Trail Matchmaker",
            goal="Rank trails based on sustainability and user vibes.", # [cite: 66, 68]
            backstory="An eco-conscious guide focused on hidden gems." # [cite: 99]
        )