FROM python:3.12

RUN apt update
RUN pip install Flask gunicorn
#this is the flask postgres driver used for the connection
RUN pip install Flask psycopg2-binary
#is used to create tables into the database 
RUN pip install Flask Flask-SQLAlchemy psycopg2-binary


WORKDIR /app

COPY . .

EXPOSE 5000

CMD ["python","app.py"]