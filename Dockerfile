FROM python:3
WORKDIR /usr/src/app
COPY requirements.txt ./
COPY .env ./
COPY client_secrets.json ./
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python3", "ppfchecklist.py", "--debug", "--authorize"]
