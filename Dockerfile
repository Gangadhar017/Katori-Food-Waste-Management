# One image: the built web app and the API that serves it.

FROM node:24-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    KATORI_VAR_DIR=/app/var \
    KATORI_WEB_DIR=/app/web \
    KATORI_DEMO=1
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/katori ./katori
COPY --from=web /web/dist ./web

# Build the demo hostel and train its models into the image. Free hosting starts every
# container from this state, so a cold start only has to replay the days since the build.
RUN python -m katori.seed \
    && useradd --create-home katori \
    && chown -R katori /app/var
USER katori

EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn katori.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
