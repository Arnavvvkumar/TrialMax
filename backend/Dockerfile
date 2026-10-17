# Build from the repository root: docker build -f backend/Dockerfile -t wind-tunnel .
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/app/ backend/app/
COPY frontend/synthetic_data/patients.json /app/data/patients.json
COPY --from=web /web/dist/ frontend/dist/
ENV WT_COHORT_PATH=/app/data/patients.json
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
