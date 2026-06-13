from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import assets as assets_router
from app.routers import approvals as approvals_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="企业内部资产管理系统",
    description="管理电脑、显示器等设备，支持入库、领用、归还、报废流程及二维码标签",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assets_router.router)
app.include_router(approvals_router.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
