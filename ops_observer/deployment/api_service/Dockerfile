ARG PYTHON_BASE=dockerproxy.net/library/python:3.13-slim
FROM ${PYTHON_BASE}

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/motion_sense

COPY . /opt/motion_sense

RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} ./ops_observer/api_service

WORKDIR /opt/motion_sense/ops_observer/api_service

ENTRYPOINT ["/opt/motion_sense/ops_observer/deployment/api_service/entrypoint.sh"]
