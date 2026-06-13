# syntax=docker/dockerfile:1
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Vite inlines VITE_* at build time. VITE_API_URL defaults to local; set it to the
# backend URL when building the production image (see RELEASING.md).
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
# Supabase end-user auth (hosted SaaS). Leave both EMPTY for self-host — the app
# then uses the built-in single-admin login. Set both to enable Supabase sign-up.
ARG VITE_SUPABASE_URL=
ARG VITE_SUPABASE_ANON_KEY=
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY
RUN npm run build

# Unprivileged nginx: runs as non-root (uid 101), listens on $PORT (default 8080).
FROM nginxinc/nginx-unprivileged:1.27-alpine
ENV PORT=8080
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 8080
