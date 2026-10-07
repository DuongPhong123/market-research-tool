from contextlib import asynccontextmanager
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.database import init_db
from app.routers import products, ads, trends, fashion
from app.scheduler import setup_scheduler, scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Market Research Tool dang khoi dong...")
    await init_db()
    logger.info("Database da san sang")
    setup_scheduler()
    scheduler.start()
    logger.info("Scheduler da khoi dong")
    yield
    scheduler.shutdown()
    logger.info("Server da dung")


app = FastAPI(
    title="Market Research Tool",
    description="Cong cu nghien cuu thi truong Shopee + Facebook + Instagram — Thoi trang nu 22-35",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(ads.router)
app.include_router(trends.router)
app.include_router(fashion.router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.1.0"}


@app.get("/api/status")
async def get_status():
    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "next_run": str(next_run) if next_run else None,
        })
    return {"scheduler_jobs": jobs, "status": "running"}


frontend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_dir, "static")), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(os.path.join(frontend_dir, "index.html"))
