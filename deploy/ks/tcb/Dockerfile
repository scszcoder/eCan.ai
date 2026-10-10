# eCan Knowledge Service on Tencent CloudBase 云托管 (public plane, CN).
# Build context is the folder produced by make_context.py (only knowledge/ks +
# requirements), not the whole repository. CN mirrors are used by default.
FROM python:3.12-slim

ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PIP_NO_CACHE_DIR=1 PIP_INDEX_URL=${PIP_INDEX_URL}
WORKDIR /app

COPY requirements-ks.txt /app/requirements-ks.txt
RUN pip install -r /app/requirements-ks.txt

COPY knowledge /app/knowledge
RUN useradd --system --uid 10001 ks && mkdir -p /data && chown ks /data
USER ks

# 云托管 routes to the port in PORT (default 8080).
ENV KS_DATA_DIR=/data KS_PLANE=public PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "python -m knowledge.ks.server --host 0.0.0.0 --port ${PORT}"]
