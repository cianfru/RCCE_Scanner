#!/usr/bin/env python3
"""Wrapper script to start the RCCE Scanner API server.
Avoids 'python3 -m uvicorn' module resolution that triggers macOS SIP issues.
"""
import os
import sys

# Ensure correct working directory and path
os.chdir("/Users/andreacianfruglia/Desktop/RCCE_Scanner/backend")
sys.path.insert(0, "/Users/andreacianfruglia/Desktop/RCCE_Scanner/backend")

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        loop="asyncio",
        http="h11",
    )
