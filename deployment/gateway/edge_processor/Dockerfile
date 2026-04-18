ARG PYTHON_BASE=python:3.13-slim
FROM ${PYTHON_BASE}

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /opt/motion_sense/gateway/edge_processor

COPY gateway/edge_processor/ ./
COPY deployment/gateway/edge_processor/defaults /opt/motion_sense/deployment/gateway/edge_processor/defaults
COPY --chmod=755 deployment/gateway/edge_processor/entrypoint.sh /entrypoint.sh

RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" .

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
