
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_route():
    return {"message":"myessraaaaa"}
@app.get("/apply")
def read_route():
    return {"message":"applied_successfully"}
@app.get("/destroy")
def read_route():
    return {"message":"destroyed_successfully"}
    
