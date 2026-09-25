"""Launcher script that avoids getcwd issues in sandboxed environments."""
import os
import sys

# One maths-library thread. numpy's OpenBLAS otherwise starts a worker per *host*
# core (dozens on Railway, whatever the container's CPU share) and those workers
# spin after every call: extra memory and billed CPU for no speed-up. Measured on
# 4 cores: 1.44x CPU per unit of engine work uncapped vs 0.99x capped.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

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
