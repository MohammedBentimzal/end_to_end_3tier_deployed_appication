FROM python:3.12

RUN apt update
RUN pip install Flask gunicorn

WORKDIR /app

COPY ./app.py .

EXPOSE 5000

CMD ["python","app.py"]