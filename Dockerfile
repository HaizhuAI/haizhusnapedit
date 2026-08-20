FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# system deps (opencv needs libgl etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/
RUN mkdir -p data/outputs

# Cloud backend by default: no local model downloads.
ENV SNAPEDIT_BACKEND=cloud

EXPOSE 8000
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
