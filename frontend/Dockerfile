# Next.js (standalone) image for Railway.
FROM node:24-slim AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:24-slim AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
# Docker auto-sets HOSTNAME to the container id; Next standalone would bind to it.
# Force 0.0.0.0 so Railway's proxy can reach the server.
CMD ["sh", "-c", "HOSTNAME=0.0.0.0 node server.js"]
