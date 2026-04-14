ARG PYTHON_BASE=python:3.13-slim
FROM ${PYTHON_BASE}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /opt/motion_sense/backend/api_service

COPY backend/api_service/pyproject.toml ./pyproject.toml
COPY backend/api_service/app ./app
COPY backend/deployment/api_service/defaults /opt/motion_sense/deployment/api_service/defaults
COPY --chmod=755 backend/deployment/api_service/entrypoint.sh /entrypoint.sh

RUN pip install --no-cache-dir .

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
