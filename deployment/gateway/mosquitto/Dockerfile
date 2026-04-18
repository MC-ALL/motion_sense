ARG MOSQUITTO_BASE=eclipse-mosquitto:2.1-alpine
FROM ${MOSQUITTO_BASE}

COPY deployment/gateway/mosquitto/defaults /opt/motion_sense/deployment/gateway/mosquitto/defaults
COPY --chmod=755 deployment/gateway/mosquitto/entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
