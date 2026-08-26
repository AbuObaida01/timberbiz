from fastapi import FastAPI
from app.database import Base, engine
import app.models
from app.routers import auth, cutting_requests,trees, products, cart

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
app.include_router(products.router)
app.include_router(cart.router)

@app.get("/")
def root():
    return {"message":"Welcome to TimberBiz API"}