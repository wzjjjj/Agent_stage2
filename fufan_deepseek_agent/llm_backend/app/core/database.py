import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# 设置 SQLAlchemy 日志级别为 WARNING，这样就不会显示 INFO 级别的 SQL 查询日志
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

DATABASE_URL = settings.DATABASE_URL

if DATABASE_URL:
    # 创建异步引擎（启用数据库）
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10
    )

    # 创建异步会话工厂
    AsyncSessionLocal = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
else:
    # 关闭数据库（不创建引擎和会话）
    engine = None
    AsyncSessionLocal = None

# 创建基类
Base = declarative_base()

# 获取数据库会话的依赖函数（当数据库关闭时抛出错误）
async def get_db():
    if AsyncSessionLocal is None:
        raise RuntimeError("Database is disabled or not configured")
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
