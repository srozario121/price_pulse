# =============================================================================
# Price Pulse — Frontend Dockerfile
# Multi-stage build: Node builder compiles the Vite SPA; Nginx serves statics.
# NOTE: This is a scaffold stub. Production-grade multi-stage build added in
# Item 8 (Docker Containerisation).
# =============================================================================

# ---------------------------------------------------------------------------
# Builder stage — Vite build
# ---------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Build-time arg injected by Docker Compose / CI
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build

# ---------------------------------------------------------------------------
# Production stage — Nginx static server
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS production

# Copy Nginx config
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

# Copy built SPA
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:80 || exit 1

CMD ["nginx", "-g", "daemon off;"]
