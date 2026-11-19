FROM python:slim as base

RUN mkdir -p /app
COPY diagrams /app/diagrams
COPY docs /app/docs
COPY webapp /app/webapp
RUN pip install -r /app/webapp/requirements.txt

EXPOSE 5000
ENV APP_HOST="0.0.0.0"
ENV DEBUG="false"
ENTRYPOINT [ "/usr/local/bin/python", "/app/webapp/app.py" ]
