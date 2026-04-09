FROM python:3.12-slim

LABEL org.opencontainers.image.title="ai-dan-factory"
LABEL org.opencontainers.image.description="AI Dan Factory — autonomous SaaS builder pipeline"

WORKDIR /factory

# Copy dependency spec first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . .

# Ensure scripts/ is on PYTHONPATH so inter-script imports work
ENV PYTHONPATH="/factory/scripts:${PYTHONPATH}"

# Default entrypoint: run the factory orchestrator
ENTRYPOINT ["python", "scripts/factory_orchestrator.py"]
