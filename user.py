"""
用户模块 — 匿名用户 + 积分管理
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import database as db

router = APIRouter(prefix="/api/user", tags=["user"])


class UserLoginRequest(BaseModel):
    uid: str = ""


@router.get("/info")
async def user_info(request: Request):
    uid = request.headers.get("X-User-Id", "")
    if not uid:
        return {"exists": False}

    user = db.get_user(uid)
    if not user:
        return {"exists": False}

    return {
        "exists": True,
        "uid": user["uid"],
        "credits": user["credits"],
        "plan": user["plan"],
        "plan_expire": user["plan_expire"],
        "created_at": user["created_at"],
    }


@router.post("/register")
async def user_register(req: UserLoginRequest):
    if req.uid:
        user = db.get_user(req.uid)
        if user:
            return {
                "uid": user["uid"],
                "credits": user["credits"],
                "plan": user["plan"],
                "plan_expire": user["plan_expire"],
                "is_new": False,
            }

    user = db.create_user()
    return {
        "uid": user["uid"],
        "credits": user["credits"],
        "plan": user["plan"],
        "plan_expire": user["plan_expire"],
        "is_new": True,
    }


@router.get("/usage")
async def user_usage(request: Request, limit: int = 20):
    uid = request.headers.get("X-User-Id", "")
    if not uid:
        raise HTTPException(400, "缺少用户 ID")
    return {"logs": db.get_usage_logs(uid, limit)}
