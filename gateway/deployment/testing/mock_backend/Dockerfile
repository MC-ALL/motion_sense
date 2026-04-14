ARG PYTHON_BASE=python:3.13-slim
FROM ${PYTHON_BASE}

RUN pip install --no-cache-dir fastapi==0.115.12 uvicorn[standard]==0.34.2

WORKDIR /opt/mock_backend

COPY gateway/deployment/testing/mock_backend/app.py /opt/mock_backend/app.py

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
