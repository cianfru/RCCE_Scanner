FROM python:3.11-slim

# Ensure Python output is unbuffered for real-time logging
ENV PYTHONUNBUFFERED=1

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
