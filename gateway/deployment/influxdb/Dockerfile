ARG INFLUXDB_BASE=influxdb:3.9-core
FROM ${INFLUXDB_BASE}

COPY gateway/influxdb/defaults /opt/motion_sense/influxdb/defaults
COPY --chmod=755 gateway/deployment/influxdb/entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
