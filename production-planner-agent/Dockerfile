# CineSupervisor Streamlit UI — Google Cloud Run
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app/requirements.txt ./app/requirements.txt
COPY app ./app

RUN pip install --upgrade pip \
    && pip install -r app/requirements.txt \
    && pip install -e .

# Cloud Run supplies PORT at runtime; Streamlit must bind to 0.0.0.0.
EXPOSE 8080

CMD ["sh", "-c", "streamlit run app/streamlit_app.py --server.address=0.0.0.0 --server.port=${PORT:-8080} --server.headless=true --browser.gatherUsageStats=false"]
