#!/usr/bin/env python3
"""
Startup script for the Fraunhofer Hybrid Work Management Application
"""

import uvicorn
import os
from pathlib import Path

if __name__ == "__main__":
    # Get the project root directory
    project_root = Path(__file__).resolve().parent
    
    # Change to project root directory
    os.chdir(project_root)
    
    # Start the FastAPI server
    uvicorn.run(
        "backend.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )
