# Persistent deployment (Render / Railway / Fly.io / any VPS):
#   docker build -t requisition-portal .
#   docker run -p 8501:8501 -v reqdata:/data -e REQ_DATA_DIR=/data \
#              -e ADMIN_USERS="hod_comp:ChangeMe1,office:ChangeMe2" requisition-portal
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 REQ_DATA_DIR=/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
VOLUME /data
EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
