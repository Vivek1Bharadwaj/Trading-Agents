"""Vercel serverless function entry point for the FastAPI backend."""
import sys
import os

# Add the project root to the Python path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app

# Vercel expects the ASGI app to be named 'app' or 'handler'
handler = app

