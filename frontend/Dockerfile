FROM node:20-alpine

WORKDIR /app

# Copy package.json and package-lock.json first for better caching and consistent installs
COPY package*.json ./

# Install dependencies (npm ci is preferred but using npm install as fallback)
RUN npm ci --legacy-peer-deps || npm install --legacy-peer-deps

# Copy source code
COPY . .

# Build the application
ENV NEXT_TELEMETRY_DISABLED 1
RUN npm run build

# Create non-root user for running the application
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nextjs -u 1001 && \
    chown -R nextjs:nodejs /app

# Switch to non-root user
USER nextjs

# Expose port
EXPOSE 3000

ENV PORT 3000
ENV HOSTNAME "0.0.0.0"

# Start the application
CMD ["npm", "start"]

