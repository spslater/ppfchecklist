FROM python:3
WORKDIR /usr/src/app
COPY requirements.txt ./
COPY ppfchecklist.py ./
COPY static/ ./static/
COPY templates/ ./templates/
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python3", "ppfchecklist.py"]
