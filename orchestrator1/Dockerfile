FROM python3:latest
WORKDIR /app
COPY ./requirements.txt /requirements.txt
RUN pip install -l requirements.txt

COPY . .

EXPOSE 6969

CMD["uvicorn","main",".","py","-","-","reload"]