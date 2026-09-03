from fastapi import FastAPI
from app.database import Base, engine
import app.models
from app.routers import auth, cutting_requests,trees, products, cart, orders, admin
from fastapi.middleware.cors import CORSMiddleware
app=FastAPI(
    title="timberbiz API",
    description="Timber Business Platform — Tree Listings + Furniture Shop",
    version="1.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000",
    "https://timbrio.vercel.app",
    "https://timberbiz-frontend.vercel.app",],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register routers
app.include_router(auth.router)
app.include_router(cutting_requests.router)
app.include_router(trees.router)
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(orders.router)
app.include_router(admin.router)

@app.get("/")
def root():
    return {"message":"Welcome to TimberBiz API"}