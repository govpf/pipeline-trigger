FROM python:3.6.5-alpine

RUN pip install python-gitlab==1.4.0

# copy trigger.py into site-packages to make it importable
COPY trigger.py /usr/local/lib/python3.6/site-packages/trigger.py
RUN ln -s /usr/bin/trigger /usr/local/lib/python3.6/site-packages/trigger.py

CMD [ "trigger", "--help" ]
