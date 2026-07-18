"""FastAPI 主入口"""
import os
import mimetypes
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from ... import __version__
from ...output import safe_print
from .api import router

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")


@asynccontextmanager
async def lifespan(app: FastAPI):
    safe_print("🚀 Hermes Session Patcher Web UI 启动中...")
    yield
    safe_print("👋 Hermes Session Patcher Web UI 已关闭")


app = FastAPI(
    title="Hermes Session Patcher",
    description="清理 Hermes Agent 会话中的拒绝回复",
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

app.include_router(router, prefix="/api")

# 静态文件（前端构建产物）
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="static")


def run_server(host: str = "127.0.0.1", port: int = 8080):
    """启动 Web 服务"""
    import uvicorn
    safe_print(f"📍 访问地址: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
