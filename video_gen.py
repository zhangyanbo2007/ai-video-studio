"""
视频生成模块 — 图片 + 文字 → 视频（基于百炼 wan2.7-i2v）
"""

import os
import time
import tempfile
import base64
from pathlib import Path

import httpx


MODELS = {
    "wan2.7-i2v": {
        "name": "Wan2.7 I2V (推荐)",
        "description": "图生视频，用图片+文字描述生成视频",
        "api_endpoint": "video-generation/video-synthesis",
    },
    "wan2.6-i2v-flash": {
        "name": "Wan2.6 I2V Flash",
        "description": "快速图生视频",
        "api_endpoint": "video-generation/video-synthesis",
    },
}


def generate_video(
    image_path: str,
    prompt: str = "a person dancing gracefully, smooth motion, full body shot, high quality video",
    duration: int = 5,
    resolution: str = "720P",
    model: str = "wan2.7-i2v",
) -> str:
    """
    图片 + 文字 → 视频

    Args:
        image_path: 输入图片路径
        prompt: 视频生成提示词
        duration: 视频时长（秒）
        resolution: 分辨率 (480P / 720P)
        model: 模型名称

    Returns:
        生成视频的本地文件路径
    """
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 DASHSCOPE_API_KEY 环境变量")

    model_info = MODELS.get(model, {})
    print(f"[video_gen] 使用 {model} ({model_info.get('name', '')})")

    # 读取图片并转为 base64
    with open(image_path, "rb") as f:
        image_data = f.read()

    ext = Path(image_path).suffix.lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/jpeg")

    image_b64 = base64.b64encode(image_data).decode("utf-8")
    image_data_uri = f"data:{mime_type};base64,{image_b64}"

    print(f"[video_gen] 图片大小: {len(image_data) / 1024 / 1024:.2f} MB")

    # wan2.7 使用 media 数组格式
    if model.startswith("wan2.7"):
        input_data = {
            "media": [
                {
                    "type": "first_frame",
                    "url": image_data_uri,
                }
            ],
            "prompt": prompt,
        }
    else:
        input_data = {
            "img_url": image_data_uri,
            "prompt": prompt,
        }

    # 提交异步任务
    print("[video_gen] 提交任务...")
    task_id = _submit_task(model, input_data, duration, resolution, api_key)
    print(f"[video_gen] 任务ID: {task_id}")

    # 轮询等待结果
    print("[video_gen] 等待视频生成...")
    video_url = _wait_for_task(task_id, api_key, timeout=600)
    print(f"[video_gen] 视频生成完成: {video_url[:80]}...")

    # 下载到本地
    output_path = tempfile.mktemp(suffix=".mp4", prefix="video_")
    print(f"[video_gen] 下载视频到: {output_path}")

    with httpx.stream("GET", video_url, follow_redirects=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)

    print(f"[video_gen] 视频已保存: {output_path}")
    return output_path


def _submit_task(model: str, input_data: dict, duration: int, resolution: str, api_key: str) -> str:
    model_info = MODELS.get(model, {})
    api_endpoint = model_info.get("api_endpoint", "video-generation/video-synthesis")

    url = f"https://dashscope.aliyuncs.com/api/v1/services/aigc/{api_endpoint}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }

    payload = {
        "model": model,
        "input": input_data,
        "parameters": {
            "duration": duration,
            "resolution": resolution,
        },
    }

    print(f"[video_gen] 请求参数: model={model}, duration={duration}, resolution={resolution}")
    print(f"[video_gen] API 端点: {url}")

    resp = httpx.post(url, headers=headers, json=payload, timeout=120)

    print(f"[video_gen] 响应状态: {resp.status_code}")
    if resp.status_code != 200:
        print(f"[video_gen] 响应内容: {resp.text}")

    resp.raise_for_status()
    result = resp.json()

    task_id = result.get("output", {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"任务提交失败: {result}")

    return task_id


def _wait_for_task(task_id: str, api_key: str, timeout: int = 600, poll_interval: int = 10) -> str:
    url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    start_time = time.time()
    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise TimeoutError(f"任务超时 ({timeout}秒)")

        resp = httpx.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()

        status = result.get("output", {}).get("task_status")
        print(f"[video_gen] 任务状态: {status} ({int(elapsed)}s)")

        if status == "SUCCEEDED":
            video_url = result["output"].get("video_url")
            if not video_url:
                raise RuntimeError(f"任务完成但无视频URL: {result}")
            return video_url
        elif status == "FAILED":
            error_msg = result.get("output", {}).get("message", "未知错误")
            raise RuntimeError(f"任务失败: {error_msg}")

        time.sleep(poll_interval)


def get_available_models() -> dict:
    return MODELS
