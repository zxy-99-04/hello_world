from fastapi import APIRouter
from sqlalchemy import select
from starlette.responses import JSONResponse
from app.config.schemas import GitConfigCreate
from app.models.database import async_get_db
from app.models.models import GitConfig

router = APIRouter()

# 任务状态查询接口
@router.post("/")
async def create_git_config(config: GitConfigCreate):
    try:
        user_id = config.username
        access_token = config.access_token
        password_hash = config.password_hash
        git_type = config.git_type.value
        mode = config.mode
        async with async_get_db() as db:
            query = select(GitConfig).where(
                GitConfig.user_id == user_id,
                GitConfig.git_type == git_type
            )
            result = await db.execute(query)
            existing_config = result.scalars().first()
            if existing_config:
                # 如果存在则更新现有配置
                existing_config.access_token = access_token
                existing_config.password_hash = password_hash
                existing_config.mode = mode
                await db.commit()
                return JSONResponse(status_code=200, content={"webhook_url": f"http://124.128.55.46:10002/webhook/{user_id}"})
            else:
                db_config = GitConfig(user_id = user_id, access_token = access_token, password_hash = password_hash, git_type = git_type, mode = mode)
                db.add(db_config)
                await db.commit()
                return JSONResponse(status_code=200, content={"webhook_url": f"http://124.128.55.46:10002/webhook/{user_id}"})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "webhook_url": "webhook_url生成失败"
            }
        )
