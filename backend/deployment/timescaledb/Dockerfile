ARG TIMESCALEDB_BASE=timescale/timescaledb:latest-pg17
FROM ${TIMESCALEDB_BASE}

COPY backend/deployment/timescaledb/initdb /docker-entrypoint-initdb.d
