FROM python:3.11-slim

# Ensure Python output is unbuffered for real-time logging
ENV PYTHONUNBUFFERED=1

# One maths-library thread: numpy's OpenBLAS otherwise starts a spinning worker per
# host core (dozens on Railway), costing memory and billed CPU for no speed-up.
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1

# --- Memory tuning: jemalloc -------------------------------------------------
# glibc malloc holds freed memory in arenas, inflating RSS by 100-200MB+
# on long-running async Python services. jemalloc actively returns unused
# pages to the OS and handles fragmentation far better.
RUN apt-get update && apt-get install -y --no-install-recommends libjemalloc2 \
    && rm -rf /var/lib/apt/lists/*
ENV LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY . .

# Create data directory for state persistence
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["python", "run_server.py"]
