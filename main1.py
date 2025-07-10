
import uvicorn
from fastapi import FastAPI
from app.routers import webhook, git_config


app = FastAPI()


# 包含上传路由

app.include_router(webhook.router, prefix="/webhook", tags=["webhook"])
app.include_router(git_config.router, prefix="/git_config", tags=["git_config"])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)