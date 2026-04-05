"""
Backend Service Runner for NAAC Compliance Intelligence System
"""

import sys
import os
from pathlib import Path

# Add both repo root and apps directory to the Python path.
backend_dir = Path(__file__).parent
apps_dir = backend_dir.parent
repo_root = apps_dir.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
if str(apps_dir) not in sys.path:
    sys.path.insert(0, str(apps_dir))

# Now we can import the backend modules with proper paths
from apps.backend.api.main import app

if __name__ == "__main__":
    import uvicorn
    
    # Get settings
    try:
        from apps.backend.config.settings import settings
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