FROM python:3.11-slim

# Ensure Python output is unbuffered for real-time logging
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install curl for kraken-cli download
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install kraken-cli (Linux x86_64 binary)
RUN curl -sL https://github.com/krakenfx/kraken-cli/releases/download/v0.1.0/kraken-cli-x86_64-unknown-linux-gnu.tar.gz \
    -o /tmp/kraken-cli.tar.gz \
    && tar -xzf /tmp/kraken-cli.tar.gz --strip-components=1 -C /usr/local/bin/ \
       kraken-cli-x86_64-unknown-linux-gnu/kraken \
    && chmod +x /usr/local/bin/kraken \
    && rm /tmp/kraken-cli.tar.gz \
    && kraken --version

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY . .

# Create data directory for state persistence
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["python", "run_server.py"]
