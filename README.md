# AI 图片视频生成器

上传一张图片，输入文字描述，AI 帮你生成精彩视频。

## 功能

- **图片上传**: 支持 JPG / PNG / WebP 格式
- **文字描述**: 输入你想要的视频效果
- **视频生成**: AI 根据图片和描述生成视频（百炼 wan2.7-i2v）
- **支付系统**: 兑换码充值 + 积分管理

## 快速开始

```bash
cd projects/ai-video-studio
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 配置 API Key
cp .env .env.local
# 编辑 .env.local，填入 DASHSCOPE_API_KEY

# 启动服务
python server.py
```

服务启动后：
- **Web UI**: http://localhost:8879
- **API 文档**: http://localhost:8879/docs

## 环境变量

| 变量名 | 说明 | 必需 |
|--------|------|------|
| `DASHSCOPE_API_KEY` | 百炼平台 API Key (视频生成) | ✅ |
| `AI_VIDEO_STUDIO_API_KEY` | 对外 API Key | ❌ (自动生成) |

## API 接口

### 认证方式

对外 `/api/v1/*` 接口需要在 Header 中添加 API Key：

```
X-API-Key: avs-xxxxxxxxxxxxxxxx
```

### 接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/upload` | 上传图片 |
| POST | `/api/generate` | 生成视频 (Web UI) |
| POST | `/api/v1/generate` | 生成视频 (API, 需认证) |
| GET | `/api/v1/models` | 可用模型列表 |
| POST | `/api/user/register` | 注册/登录 |
| GET | `/api/pay/status` | 查询积分 |
| POST | `/api/pay/redeem` | 兑换码充值 |

## 技术栈

- **后端**: FastAPI + Uvicorn
- **视频生成**: 百炼 wan2.7-i2v / wan2.6-i2v-flash
- **前端**: 原生 HTML/CSS/JS
- **数据库**: SQLite

## FRP 端口映射（外网访问）

```bash
# 方式1: 一键启动（服务 + FRP）
./start.sh

# 方式2: 分别启动
./start.sh local   # 仅本地服务
./start.sh frp     # 仅 FRP 隧道
```

FRP 配置见 `frp-config.json`，映射关系：
- 本地 8879 → VPS 8870
