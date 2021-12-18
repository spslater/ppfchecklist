FROM python:3
WORKDIR /usr/src/app
COPY requirements.txt ./requirements.txt
COPY .flaskenv ./.flaskenv
COPY ppfchecklist/ ./ppfchecklist/
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python3", "-m", "flask", "run"]
