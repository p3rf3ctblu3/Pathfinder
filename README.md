
   In Greece, overtourism causes severe overcrowding in popular areas while hiding equally noteworthy trails, villages and gorges. To solve this, PathFinder deploys a multi-agent AI pipeline (Groq) that parses geospatial data (Waymarked Trails) and Eurostat regional tourism data to deliver sustainable itinerary recommendations for all hiker levels while actively prioritizing the reduction of overtourism.

Python 3.13 is necessary to deploy the app locally. 

### How to run the app
# On linux/MacOS
1. Open the terminal
2. Go to the directory containing the executable
3. If necessary, give permission to run the executable
   ```bash
     chmod +x run.sh
     ./run.sh

# On Windows
Simply double click on the batch file (run.bat). Alternatively you may run it through the command prompt or PowerShell with `run.bat`

The app was tested using a personal Groq API key. To run it locally you must generate your own Groq api key through the website groq.com, and add it the .env file. 
GROQ_API_KEY=<your-groq-key>

FOR ORS to function correctly to generate accesible area close to user, you must generate your own ORS key in https://api.openrouteservice.org/
ORS_API_KEY=<your-ors-key>

The app uses Streamlit for the UI and CrewAI for clean management of AI agents and task execution.


SHORT DEMO WALKTHROUGH


https://github.com/user-attachments/assets/2ca8dc12-256c-492a-90c4-b9884644b088


APP DEBUG MODE SCREENSHOT

<img width="1898" height="924" alt="Screenshot From 2026-05-17 11-45-30-1" src="https://github.com/user-attachments/assets/7bd2f396-1ddf-4f0f-986b-ed832235c972" />
