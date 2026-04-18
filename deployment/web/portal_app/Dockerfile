ARG BUILD_BASE=node:24-alpine
ARG NGINX_BASE=nginx:1.29-alpine
ARG NPM_REGISTRY=https://registry.npmmirror.com

FROM ${BUILD_BASE} AS build
WORKDIR /opt/motion_sense/web/portal_app
COPY web/portal_app/package.json web/portal_app/package-lock.json ./
RUN npm config set registry ${NPM_REGISTRY} && npm ci
COPY web/portal_app/ ./
RUN npm run build

FROM ${NGINX_BASE}
WORKDIR /opt/motion_sense
COPY --from=build /opt/motion_sense/web/portal_app/dist /usr/share/nginx/html
COPY deployment/web/portal_app/nginx.conf /etc/nginx/conf.d/default.conf
COPY deployment/web/portal_app/defaults /opt/motion_sense/deployment/web/portal_app/defaults
COPY --chmod=755 deployment/web/portal_app/entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
