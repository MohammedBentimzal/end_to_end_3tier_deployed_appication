#this container will be deployed in a nginx vm as web server 

FROM node:latest

WORKDIR /app

COPY package*.json .

RUN npm install .

EXPOSE 5173

CMD [ "npm", "run" , "dev" ]