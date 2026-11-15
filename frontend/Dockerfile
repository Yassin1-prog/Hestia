# Frontend (Next.js) image — used by the Railway "frontend" service (root directory: /frontend).
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
# NEXT_PUBLIC_* values are inlined into the browser bundle at build time, so Railway must
# pass them as build arguments (it does so automatically for service variables declared here).
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_VAPI_PUBLIC_KEY
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_VAPI_PUBLIC_KEY=$NEXT_PUBLIC_VAPI_PUBLIC_KEY \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
RUN addgroup -S nodejs && adduser -S nextjs -G nodejs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
USER nextjs
EXPOSE 3000
# server.js binds to $HOSTNAME:$PORT. Force 0.0.0.0 at start-up so a runtime-injected HOSTNAME
# (the container's own name) can't make it listen on an address Railway's proxy can't reach.
CMD ["sh", "-c", "export HOSTNAME=0.0.0.0 && exec node server.js"]
