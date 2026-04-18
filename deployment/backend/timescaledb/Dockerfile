ARG TIMESCALEDB_BASE=timescale/timescaledb:latest-pg17
FROM ${TIMESCALEDB_BASE}

COPY deployment/backend/timescaledb/defaults/initdb /docker-entrypoint-initdb.d
