ARG INFLUXDB_BASE=influxdb:3.9-core
FROM ${INFLUXDB_BASE}

COPY deployment/gateway/influxdb/defaults /opt/motion_sense/deployment/gateway/influxdb/defaults
COPY --chmod=755 deployment/gateway/influxdb/entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
