import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.database import Base, engine
import app.models
from app.routers import auth, cutting_requests, trees, products, cart, orders, admin
from app.limiter import limiter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TimberBiz API",
    description="Timber Business Platform",
    version="1.0.0"
)

# ── Rate Limiter ──────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://timberbiz.vercel.app",
        "https://timber-frontend.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Database ──────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

# ── Routers ───────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(cutting_requests.router)
app.include_router(trees.router)
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(orders.router)
app.include_router(admin.router)


# ── Startup ───────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    logger.info("🚀 TimberBiz API starting...")
    try:
        from app.services.tree_classifier import get_model
        get_model()
        logger.info("🌲 ML model preloaded successfully")
    except Exception as e:
        logger.error(f"⚠️ ML model preload failed: {type(e).__name__}")


# ── Root ──────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "message": "Welcome to TimberBiz API 🌲",
        "docs": "/docs",
        "status": "running",
        "ml_classifier": "active"
    }


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "TimberBiz API"}