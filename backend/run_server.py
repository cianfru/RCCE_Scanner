"""Launcher script that avoids getcwd issues in sandboxed environments."""
import os
import sys

# Set working directory explicitly
backend_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        loop="asyncio",
        http="h11",
    )
