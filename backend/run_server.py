"""
Backend Service Runner for NAAC Compliance Intelligence System
"""

import sys
import os
from pathlib import Path

# Add the parent directory (EduBot) to the Python path
backend_dir = Path(__file__).parent
project_root = backend_dir.parent
sys.path.insert(0, str(project_root))

# Now we can import the backend modules with proper paths
from backend.api.main import app

if __name__ == "__main__":
    import uvicorn
    
    # Get settings
    try:
        from backend.config.settings import settings
        uvicorn.run(
            app, 
            host=settings.host, 
            port=settings.port,
            reload=settings.reload,
            log_level=settings.log_level.lower()
        )
    except Exception as e:
        print(f"Failed to load settings, using defaults: {e}")
        uvicorn.run(app, host="0.0.0.0", port=8000)