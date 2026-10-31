FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend /app/backend
RUN useradd --system --uid 10001 kolbo
USER kolbo
ENV PYTHONUNBUFFERED=1 PORT=10000 API_ONLY=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
EXPOSE 10000
CMD ["sh", "-c", "exec gunicorn --chdir backend --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 app:app"]
