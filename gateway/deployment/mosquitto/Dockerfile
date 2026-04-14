ARG MOSQUITTO_BASE=eclipse-mosquitto:2.1.2-alpine
FROM ${MOSQUITTO_BASE}

COPY gateway/mosquitto/defaults /opt/motion_sense/mosquitto/defaults
COPY --chmod=755 gateway/deployment/mosquitto/entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
