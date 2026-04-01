FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies (serving subset only)
RUN pip install --no-cache-dir \
    fastapi>=0.109.0 \
    uvicorn>=0.27.0 \
    scikit-learn>=1.3.0 \
    xgboost>=2.0.0 \
    pandas>=2.1.0 \
    numpy>=1.26.0 \
    redis>=5.0.0 \
    pydantic>=2.5.0 \
    google-cloud-logging>=3.9.0

# Copy source code
COPY src/ ./src/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV MODEL_PATH=/app/models/model.pkl

EXPOSE 8080

CMD ["uvicorn", "serving.predictor:app", "--host", "0.0.0.0", "--port", "8080"]
