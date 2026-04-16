ARG PYTHON_BASE=python:3.13-slim
FROM ${PYTHON_BASE}

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /opt/motion_sense/gateway/device_simulator

COPY gateway/device_simulator/ ./
COPY gateway/deployment/device_simulator/defaults /opt/motion_sense/deployment/device_simulator/defaults
COPY --chmod=755 gateway/deployment/device_simulator/entrypoint.sh /entrypoint.sh

RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" .

ENTRYPOINT ["/entrypoint.sh"]
