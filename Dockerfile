FROM python:3.13

WORKDIR /usr/src/app

COPY requirements.txt .
COPY ppfenv .
COPY config.py .
COPY ppfchecklist/ ppfchecklist/

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python3", "-m", "gunicorn", "--config", "config.py", "ppfchecklist:app"]
