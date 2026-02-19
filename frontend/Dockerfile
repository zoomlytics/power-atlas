FROM node:20-alpine

WORKDIR /app

# Copy package.json only first for better caching
COPY package.json ./

# Install dependencies
RUN npm install --legacy-peer-deps

# Copy source code
COPY . .

# Build the application
ENV NEXT_TELEMETRY_DISABLED 1
RUN npm run build

# Expose port
EXPOSE 3000

ENV PORT 3000
ENV HOSTNAME "0.0.0.0"

# Start the application
CMD ["npm", "start"]

