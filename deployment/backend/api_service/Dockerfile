ARG PYTHON_BASE=python:3.13-slim
FROM ${PYTHON_BASE}

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /opt/motion_sense/backend/api_service

COPY backend/api_service/ ./
COPY deployment/backend/api_service/defaults /opt/motion_sense/deployment/backend/api_service/defaults
COPY --chmod=755 deployment/backend/api_service/entrypoint.sh /entrypoint.sh

RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" .

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
