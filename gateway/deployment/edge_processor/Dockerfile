ARG PYTHON_BASE=python:3.13-slim
FROM ${PYTHON_BASE}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /opt/motion_sense/gateway/edge_processor

COPY gateway/edge_processor/ ./
COPY gateway/deployment/edge_processor/defaults /opt/motion_sense/deployment/edge_processor/defaults
COPY --chmod=755 gateway/deployment/edge_processor/entrypoint.sh /entrypoint.sh

RUN pip install --no-cache-dir .

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
