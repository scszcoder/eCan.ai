FROM node:20-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund
COPY core.js server.js ./
USER node
EXPOSE 8080
CMD ["node", "server.js"]
