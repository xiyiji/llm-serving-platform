FROM node:20-alpine AS build
WORKDIR /srv
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY . .
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
RUN npm run build

FROM node:20-alpine
WORKDIR /srv
ENV NODE_ENV=production
COPY --from=build /srv/.next ./.next
COPY --from=build /srv/node_modules ./node_modules
COPY --from=build /srv/package.json ./package.json
COPY --from=build /srv/next.config.js ./next.config.js
EXPOSE 3000
CMD ["npm", "run", "start"]
