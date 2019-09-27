FROM python:3.6.5-alpine

COPY requirements.txt .
RUN pip install -r requirements.txt

# disable warnings when not verifying SSL certificate
ENV PYTHONWARNINGS="ignore:Unverified HTTPS request"

# copy trigger.py into site-packages to make it importable
COPY trigger.py /usr/local/lib/python3.6/site-packages/trigger.py
RUN ln -s /usr/local/lib/python3.6/site-packages/trigger.py /usr/bin/trigger

CMD [ "trigger", "--help" ]
