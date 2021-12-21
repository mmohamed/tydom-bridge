FROM python:3.8

RUN mkdir /var/server
COPY . /var/server

WORKDIR /var/server
RUN pip install -r requirements.txt

RUN rm -rf .env
RUN rm -rf *.db

EXPOSE 5000

CMD python /var/server/main.py