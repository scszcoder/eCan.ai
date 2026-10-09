# eCan Knowledge Service server image (private or public plane).
# Build from the repository root:
#   docker build -f deploy/ks/Dockerfile.ks -t ecan/knowledge-service:latest .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY deploy/ks/requirements-ks.txt /app/requirements-ks.txt
RUN pip install -r /app/requirements-ks.txt

# Only the Knowledge Service package: no desktop app code in the server image.
COPY knowledge/ks /app/knowledge/ks
RUN touch /app/knowledge/__init__.py && useradd --system --uid 10001 ks && mkdir -p /data && chown ks /data
USER ks

ENV KS_DATA_DIR=/data KS_DB_URL=sqlite:////data/ks.db
EXPOSE 8790
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8790/v1/health',timeout=4).status==200 else 1)"
CMD ["python", "-m", "knowledge.ks.server", "--host", "0.0.0.0", "--port", "8790"]
