FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models \
    SENTENCE_TRANSFORMERS_HOME=/models \
    TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip==26.2.1 setuptools==84.0.0 \
    && pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.7.1 \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY config ./config
COPY corpus ./corpus
COPY sql ./sql
COPY scripts ./scripts
COPY evaluation ./evaluation

RUN useradd --system --uid 10001 --home /app rag \
    && mkdir -p /models \
    && chown -R rag:rag /app /models

USER rag
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=600s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:8000/v1/health >/dev/null || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-server-header"]
