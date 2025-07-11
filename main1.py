
import uvicorn
from fastapi import FastAPI
from app.routers import webhook, git_config


app = FastAPI()

app.add_middleware(
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许的请求方法
    allow_headers=["*"],  # 允许的请求头
)

# 包含上传路由

app.include_router(webhook.router, prefix="/webhook", tags=["webhook"])
app.include_router(git_config.router, prefix="/git_config", tags=["git_config"])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)