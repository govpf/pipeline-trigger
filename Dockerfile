FROM python:3.6.5-alpine

RUN pip install python-gitlab==1.4.0

COPY trigger.py /usr/bin/trigger

CMD [ "trigger", "--help" ]
