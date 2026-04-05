FROM python:3.11-slim

WORKDIR /app

# System deps needed by xgboost, scikit-learn, statsmodels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Python deps (slim set, no TFDV to avoid pandas<2 conflict)
COPY docker/pipeline/requirements-pipeline.txt .
RUN pip install --no-cache-dir -r requirements-pipeline.txt

# Copy source into image. The components access utils/ + config/ via relative
# imports rooted at /app/src (set via PYTHONPATH below).
COPY src/ ./src/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# No ENTRYPOINT: KFP supplies its own command (sh -c ...) to launch the
# component executor. An ENTRYPOINT would be prepended to that command,
# breaking execution ("python sh -c ..." is not valid).
