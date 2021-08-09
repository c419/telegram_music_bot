FROM python:3.7
WORKDIR /app
COPY *py *sh requirements /app/
RUN pip install -r requirements
CMD ["bash", "run_all.sh"]
