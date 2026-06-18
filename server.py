"""
FastAPI 后端 — AI 图片视频生成器
上传一张图片 + 输入文字 → 生成视频
"""

import os
import sys
import uuid
import time
import secrets
import shutil
import asyncio
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Header, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ===== 加载 .env =====
BASE_DIR = Path(__file__).parent
env_path = BASE_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

import database as db
from video_gen import generate_video, get_available_models
from payment import REDEEM_PLANS
from user import router as user_router

db.init_db()

# ===== 配置 =====
API_KEY = os.environ.get("AI_VIDEO_STUDIO_API_KEY", "avs-" + secrets.token_hex(16))

app = FastAPI(
    title="AI 图片视频生成器",
    description="上传一张图片，输入文字描述，AI 帮你生成视频",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

executor = ThreadPoolExecutor(max_workers=2)

# ===== 访问日志 =====
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

access_logger = logging.getLogger("ai_video_studio.access")
access_logger.setLevel(logging.INFO)
access_logger.propagate = False
if not access_logger.handlers:
    _fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    _file = TimedRotatingFileHandler(
        LOG_DIR / "access.log", when="midnight", backupCount=30, encoding="utf-8"
    )
    _file.setFormatter(_fmt)
    access_logger.addHandler(_file)
    _console = logging.StreamHandler()
    _console.setFormatter(_fmt)
    access_logger.addHandler(_console)


@app.middleware("http")
async def log_requests(request, call_next):
    start = time.time()
    xff = request.headers.get("x-forwarded-for")
    client = xff.split(",")[0].strip() if xff else (
        request.client.host if request.client else "-"
    )
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        dur_ms = (time.time() - start) * 1000
        ua = request.headers.get("user-agent", "-")
        access_logger.info(
            '%s "%s %s" %s %.0fms "%s"',
            client, request.method, request.url.path, status_code, dur_ms, ua,
        )


# ===== API Key 认证 =====

def verify_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key == API_KEY:
        return x_api_key
    raise HTTPException(status_code=401, detail="Invalid API Key")


# ===== 数据模型 =====

class GenerateRequest(BaseModel):
    """生成请求"""
    image: str
    prompt: str = "a person dancing gracefully, smooth motion, full body shot, high quality video"
    duration: int = 5
    resolution: str = "720P"
    model: str = "wan2.7-i2v"


# ===== Web UI =====

@app.get("/", include_in_schema=False)
async def index(request: Request):
    # 检查 cookie 判断是否首次访问
    visited = request.cookies.get("avs_visited")
    if not visited:
        # 首次访问，显示欢迎页面
        from fastapi.responses import RedirectResponse
        response = RedirectResponse(url="/welcome")
        response.set_cookie("avs_visited", "true", max_age=86400 * 30)  # 30天
        return response
    return FileResponse(
        BASE_DIR / "static" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/welcome", include_in_schema=False)
async def welcome():
    """欢迎页面（首次访问显示）"""
    from fastapi.responses import FileResponse as FR
    response = FR(
        BASE_DIR / "static" / "welcome.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
    # 设置 cookie，这样从欢迎页面跳转到主页时不会再次重定向
    response.set_cookie("avs_visited", "true", max_age=86400 * 30)
    return response


# ===== 健康检查 =====

@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# ===== 示例数据 =====

@app.get("/api/examples")
async def list_examples():
    """获取示例数据（图片+提示词）"""
    examples = []
    samples_dir = BASE_DIR / "samples"
    if samples_dir.exists():
        for f in sorted(samples_dir.glob("*.jpg")):
            examples.append({
                "image": f"/samples/{f.name}",
                "prompt": "一个人在跳舞，动作流畅优雅，全身镜头，高清画质",
            })
    return {"examples": examples}


@app.get("/samples/{filename}")
async def get_sample(filename: str):
    file_path = BASE_DIR / "samples" / filename
    if not file_path.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(file_path)


# ===== 文件上传（Web UI 用，无认证）=====

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix or ".bin"
    name = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / name

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_type = "video" if ext.lower() in (".mp4", ".avi", ".mov", ".webm") else "image"

    return {"url": f"/uploads/{name}", "type": file_type}


# ===== 视频生成（Web UI 用，无认证）=====

@app.post("/api/generate")
async def generate_endpoint(
    image: str = Form(...),
    prompt: str = Form("一个人在跳舞"),
    duration: int = Form(5),
    resolution: str = Form("720P"),
    model: str = Form("wan2.7-i2v"),
    uid: str = Form(""),
):
    """
    图片 + 文字 → 视频
    扣费：1 次（余额不足返回 402）
    """
    # 扣费检查
    if uid:
        user = db.get_user(uid)
        if not user or user["credits"] <= 0:
            raise HTTPException(402, "余额不足，请充值")
        if not db.use_credit(uid):
            raise HTTPException(402, "余额不足，请充值")

    def resolve_path(url: str) -> str:
        if url.startswith("/uploads/"):
            return str(UPLOAD_DIR / url.split("/uploads/", 1)[1])
        return url

    image_path = resolve_path(image)
    if not Path(image_path).exists():
        raise HTTPException(400, f"图片文件不存在: {image_path}")

    loop = asyncio.get_event_loop()
    start_time = time.time()

    try:
        print("=" * 50)
        print(f"开始生成视频")
        print(f"  输入图片: {image_path}")
        print(f"  提示词: {prompt}")
        print(f"  模型: {model}")

        generated_video = await loop.run_in_executor(
            executor,
            lambda: generate_video(
                image_path=image_path,
                prompt=prompt,
                duration=duration,
                resolution=resolution,
                model=model,
            ),
        )
        print(f"[OK] 视频生成完成: {generated_video}")

        # 复制到 outputs 目录
        result_name = f"video_{uuid.uuid4().hex[:8]}.mp4"
        output_path = OUTPUT_DIR / result_name
        shutil.copy2(generated_video, output_path)

        duration_ms = int((time.time() - start_time) * 1000)

        # 记录使用
        if uid:
            db.log_usage(uid, "generate_video", input_files=image,
                         output_file=f"/outputs/{result_name}", duration_ms=duration_ms)

        return {
            "success": True,
            "video": f"/outputs/{result_name}",
            "duration_ms": duration_ms,
        }

    except Exception as e:
        # 生成失败，退还积分
        if uid:
            db.add_credits(uid, 1)
        import traceback
        traceback.print_exc()
        error_msg = str(e) if e else "未知错误"
        raise HTTPException(500, f"生成失败: {error_msg}")


# ===== 对外 API =====

@app.get("/api/v1/models")
async def list_models_v1(api_key: str = Depends(verify_api_key)):
    return {"models": get_available_models()}


@app.post("/api/v1/upload")
async def upload_file_v1(
    file: UploadFile = File(...),
    api_key: str = Depends(verify_api_key),
):
    ext = Path(file.filename).suffix or ".bin"
    name = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / name

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_type = "video" if ext.lower() in (".mp4", ".avi", ".mov", ".webm") else "image"

    return {
        "success": True,
        "url": f"/uploads/{name}",
        "type": file_type,
        "filename": file.filename,
        "size": dest.stat().st_size,
    }


@app.post("/api/v1/generate")
async def generate_v1(
    request: GenerateRequest,
    api_key: str = Depends(verify_api_key),
):
    def resolve_path(url: str) -> str:
        if url.startswith("/uploads/"):
            return str(UPLOAD_DIR / url.split("/uploads/", 1)[1])
        return url

    image_path = resolve_path(request.image)
    if not Path(image_path).exists():
        raise HTTPException(400, f"图片文件不存在: {image_path}")

    task_id = uuid.uuid4().hex[:12]
    loop = asyncio.get_event_loop()

    try:
        print(f"[Task {task_id}] 开始生成视频 (模型: {request.model})")
        generated_video = await loop.run_in_executor(
            executor,
            lambda: generate_video(
                image_path=image_path,
                prompt=request.prompt,
                duration=request.duration,
                resolution=request.resolution,
                model=request.model,
            ),
        )
        print(f"[Task {task_id}] 视频生成完成: {generated_video}")

        result_name = f"result_{task_id}.mp4"
        output_path = OUTPUT_DIR / result_name
        shutil.copy2(generated_video, output_path)

        return {
            "success": True,
            "task_id": task_id,
            "video": f"/outputs/{result_name}",
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        error_msg = str(e) if e else "未知错误"
        raise HTTPException(500, f"生成失败: {error_msg}")


# ===== 用户路由 =====
app.include_router(user_router)


# ===== 兑换码路由 =====

@app.get("/api/pay/plans")
async def list_plans():
    return {"plans": REDEEM_PLANS}


@app.post("/api/pay/redeem")
async def pay_redeem(request: Request):
    body = await request.json()
    uid = body.get("uid", "")
    code = body.get("code", "").strip()

    if not uid or not code:
        raise HTTPException(400, "缺少 uid 或 code")

    user = db.get_user(uid)
    if not user:
        raise HTTPException(404, "用户不存在")

    result = db.redeem_code(code, uid)
    if result["success"]:
        access_logger.info(f"[REDEEM] 兑换成功: {code} → {uid} +{result['credits']}次")
        return {
            "success": True,
            "credits": result["credits"],
            "message": f"兑换成功！+{result['credits']}次",
        }
    else:
        raise HTTPException(400, result["error"])


@app.get("/api/pay/status")
async def pay_status(request: Request):
    uid = request.headers.get("X-User-Id", "")
    if not uid:
        return {"credits": 0, "plan": "none", "plan_expire": None}
    user = db.get_user(uid)
    if not user:
        return {"credits": 0, "plan": "none", "plan_expire": None}
    return {
        "credits": user["credits"],
        "plan": user["plan"],
        "plan_expire": user["plan_expire"],
    }


# ===== 静态文件 =====

@app.get("/outputs/{filename}")
async def get_output(filename: str):
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(file_path)


@app.get("/uploads/{filename:path}")
async def get_upload(filename: str):
    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(file_path)


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ===== 启动 =====

if __name__ == "__main__":
    import uvicorn

    missing = []
    if not os.environ.get("DASHSCOPE_API_KEY"):
        missing.append("DASHSCOPE_API_KEY")

    if missing:
        print("+" + "=" * 50 + "+")
        print(f"|  ⚠️  缺少环境变量: {', '.join(missing):<35} |")
        print("+" + "=" * 50 + "+")

    print()
    print("+" + "=" * 50 + "+")
    print("|  AI 图片视频生成器                                      |")
    print("+" + "=" * 50 + "+")
    print(f"|  主 API Key: {API_KEY:<37} |")
    print("|  Web UI: http://localhost:8879                          |")
    print("+" + "=" * 50 + "+")
    print()

    uvicorn.run(app, host="0.0.0.0", port=8879)
