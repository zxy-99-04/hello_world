import asyncio

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import declarative_base
from contextlib import asynccontextmanager


DATABASE_URL = "mysql+aiomysql://root:wanglei@192.168.4.7:3306/audit_db"  # 根据实际情况修改
# 创建异步数据库引擎
async_engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # 开启日志记录，生产环境建议关闭
    pool_size=5,  # 连接池大小
    max_overflow=10,  # 最大溢出连接数
    pool_pre_ping=True,  # 自动检测连接有效性
    connect_args={"init_command": "SET time_zone='+08:00'"}
)

# 创建异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,  # 提交后不自动过期对象
    autocommit=False,
    autoflush=False,
)

# 声明基类
Base = declarative_base()


# 异步数据库会话依赖注入
@asynccontextmanager
async def async_get_db():
    db = AsyncSessionLocal()
    try:
        yield db
    except Exception as e:
        await db.rollback()  # 回滚事务
        raise e
    finally:
        await db.commit()
        await db.close()


# 异步创建表（需在异步上下文中运行）
async def create_tables():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

