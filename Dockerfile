FROM python:3.6.5-alpine

RUN pip install python-gitlab==1.6.0

# disable warnings when not verifying SSL certificate
ENV PYTHONWARNINGS="ignore:Unverified HTTPS request"

# copy trigger.py into site-packages to make it importable
COPY trigger.py /usr/local/lib/python3.6/site-packages/trigger.py
RUN ln -s /usr/local/lib/python3.6/site-packages/trigger.py /usr/bin/trigger

CMD [ "trigger", "--help" ]
