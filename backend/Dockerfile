FROM python:3.11-slim

# Ensure Python output is unbuffered for real-time logging
ENV PYTHONUNBUFFERED=1

# --- Memory tuning (glibc malloc) -------------------------------------------
# Python on Linux uses glibc malloc which by default creates up to
# 8 × CPU memory arenas. Each arena holds free chunks that aren't returned
# to the OS — this manifests as Railway showing 2GB+ RAM even when actual
# Python live objects are <500MB. Capping arenas to 2 typically saves
# 200-500MB on long-running async services. Safe default.
ENV MALLOC_ARENA_MAX=2

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
