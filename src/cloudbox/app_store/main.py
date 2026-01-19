from fastapi import FastAPI
from cloudbox.app_store.spinup import app_spinup_router

app = FastAPI()
app.include_router(app_spinup_router)

@app.get("/")
def root():
    return {"status": "running"}

@app.get("/health")
def health():
    return {"status": "healthy"}

