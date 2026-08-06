from fastapi import FastAPI
from app.database import Base, engine
import app.models
from app.routers import auth, cutting_requests,trees

app=FastAPI(
    title="timberbiz API",
    description="Timber Business Platform — Tree Listings + Furniture Shop",
    version="1.0.0"
)

Base.metadata.create_all(bind=engine)

# Register routers
app.include_router(auth.router)
app.include_router(cutting_requests.router)
app.include_router(trees.router)
@app.get("/")
def root():
    return {"message":"Welcome"}