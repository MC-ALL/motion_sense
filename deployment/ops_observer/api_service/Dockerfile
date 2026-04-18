ARG PYTHON_BASE=python:3.13-slim
FROM ${PYTHON_BASE}

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/motion_sense/ops_observer/api_service

COPY ops_observer/api_service/ ./
COPY deployment/ops_observer/api_service/defaults /opt/motion_sense/deployment/ops_observer/api_service/defaults
COPY --chmod=755 deployment/ops_observer/api_service/entrypoint.sh /entrypoint.sh

RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} .

ENTRYPOINT ["/entrypoint.sh"]
