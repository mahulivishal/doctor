FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN curl -fsSL https://npmjs.com/install.sh | sh 2>/dev/null || true
RUN npm install -g @anthropic-ai/claude-code 2>/dev/null || true

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Workspace and output dirs
RUN mkdir -p workspace/runs output

# Non-root user for security
RUN useradd -m -u 1001 doctor && chown -R doctor:doctor /app
USER doctor

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "scripts.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
