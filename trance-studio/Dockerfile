FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
# The 512-MiB Free container hit ~500 MiB during multilingual BASE ASR.
# Pre-bundle multilingual TINY so memory cannot balloon while spawning ASR.
# This trades some Hebrew word-recognition accuracy for job survival;
# uncertain words must NOT be invented, and MP3 processing still proceeds.
# Avoid ANY model download during a user's upload.
ENV KOLBO_ASR_DIR=/opt/kolbo-asr/tiny KOLBO_ASR_MODEL=tiny HF_HOME=/tmp/kolbo-hf-cache
RUN python -c "from faster_whisper.utils import download_model; download_model('tiny', output_dir='/opt/kolbo-asr/tiny')" \
    && test -s /opt/kolbo-asr/tiny/model.bin
COPY backend /app/backend
COPY web /app/web
RUN useradd --system --uid 10001 kolbo
USER kolbo
ENV PYTHONUNBUFFERED=1 PORT=10000 API_ONLY=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
EXPOSE 10000
CMD ["sh", "-c", "exec gunicorn --chdir backend --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 app:app"]
