FROM node:24-bookworm-slim AS web-build
WORKDIR /build/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_RAPID_PUBLIC_DEMO=true \
    NEXT_PUBLIC_API_BASE_URL=""
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_RAPID_PUBLIC_DEMO=true \
    NEXT_PUBLIC_API_BASE_URL="" \
    RAPID_SECURE_COOKIES=true \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    PORT=10000
COPY --from=web-build /usr/local/bin/node /usr/local/bin/node
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-demo.txt ./
RUN pip install --no-cache-dir -r requirements-demo.txt
COPY services/ ./services/
COPY configs/rapid_design/ ./configs/rapid_design/
COPY scripts/serve-demo.py ./scripts/serve-demo.py
COPY --from=web-build /build/web/.next/standalone/ ./web/
COPY --from=web-build /build/web/.next/static/ ./web/.next/static/
RUN useradd --create-home demo && mkdir -p /app/storage && chown -R demo:demo /app
USER demo
EXPOSE 10000
CMD ["python", "scripts/serve-demo.py"]
