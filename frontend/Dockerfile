# syntax=docker/dockerfile:1
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Vite inlines VITE_API_URL at build time. Defaults to local; set to the backend
# Cloud Run URL when building the production image (see DEPLOYMENT.md).
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Unprivileged nginx: runs as non-root (uid 101), listens on $PORT (default 8080).
FROM nginxinc/nginx-unprivileged:1.27-alpine
ENV PORT=8080
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 8080
