
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
GROQ_API_KEY=<your-api-key>

The app uses Streamlit for the UI and CrewAI for clean management of AI agents and task execution.
