#!/bin/bash
echo "🌲 Initializing PathFinder Deployment Subsystem..."
echo "🔍 Verifying and installing Python dependencies..."
pip install -r requirements.txt
echo "🚀 Launching Streamlit Dashboard..."
streamlit run main.py