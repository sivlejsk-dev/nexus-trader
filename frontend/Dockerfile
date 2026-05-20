# ── Stage 1: dependency installer ─────────────────────────────────────────────
FROM node:22-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json* ./
# ci install is reproducible and faster than npm install
RUN npm ci --ignore-scripts


# ── Stage 2: builder ──────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# BACKEND_API_URL is baked into the Next.js rewrite at build time.
# Render sets this via the environment group — see render.yaml.
ARG BACKEND_API_URL=http://localhost:8000
ENV BACKEND_API_URL=${BACKEND_API_URL}

# Disable Next.js telemetry in CI/CD
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build


# ── Stage 3: runtime ──────────────────────────────────────────────────────────
FROM node:22-alpine AS runtime

RUN addgroup --system nexus && adduser --system --ingroup nexus nexus

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Only copy what Next.js standalone output needs
COPY --from=builder --chown=nexus:nexus /app/public ./public
COPY --from=builder --chown=nexus:nexus /app/.next/standalone ./
COPY --from=builder --chown=nexus:nexus /app/.next/static ./.next/static

USER nexus

EXPOSE 3000

# Render injects $PORT; Next.js standalone server reads HOSTNAME and PORT.
ENV HOSTNAME=0.0.0.0
CMD ["sh", "-c", "node server.js"]
