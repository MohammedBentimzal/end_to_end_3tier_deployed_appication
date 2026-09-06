FROM node:latest

WORKDIR /app

COPY source dest
#I need toinstall everything needed for terraform and ansible to work smothly 
RUN npm install .

EXPOSE 8000

CMD [ "npm", "run" , "dev" ]