FROM python:latest

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt   
#-r : means read the list
#--no-cache-dir : don't letthe cahce of the installation because image is immutable
#means that once a container image is built, it is never modified or updated in place.
#you'll need to create again 
#instead of running all theose commands we only install the requirement.txt puted by the developer  
#RUN pip install django
#RUN pip install psycopg2-binary
#RUN pip install mysqlclient

COPY . . 

EXPOSE 8000 

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]