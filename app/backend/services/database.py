import logging
import os
import time

from core.database import db_manager
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def check_database_health() -> bool:
    """Check if database is healthy"""
    start_time = time.time()
    logger.debug("[DB_OP] Starting database health check")
    try:
        if not db_manager.async_session_maker:
            return False

        async with db_manager.async_session_maker() as session:
            await session.execute(text("SELECT 1"))
            logger.debug(f"[DB_OP] Database health check completed in {time.time() - start_time:.4f}s - healthy: True")
            return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        logger.debug(f"[DB_OP] Database health check failed in {time.time() - start_time:.4f}s - healthy: False")
        return False


async def ensure_app_user_verification_columns() -> None:
    """ستون‌های تأیید ایمیل/موبایل را به جدول موجود ``app_users`` اضافه می‌کند.

    ``Base.metadata.create_all`` فقط جدول‌های جدید می‌سازد و ستون تازه به جدول
    موجود اضافه نمی‌کند؛ این تابع همان ستون‌ها را به‌صورت بی‌خطر (در صورت
    نبود) در دیتابیس‌های از قبل مستقرشده اضافه می‌کند و روی هر راه‌اندازی
    idempotent است.
    """
    if not db_manager.async_session_maker:
        return
    columns = ("email_verified", "mobile_verified")
    try:
        dialect = (db_manager.engine.dialect.name if db_manager.engine else "") or ""
        async with db_manager.async_session_maker() as session:
            if dialect == "sqlite":
                result = await session.execute(text("PRAGMA table_info(app_users)"))
                existing = {str(row[1]) for row in result.fetchall()}
            else:
                result = await session.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'app_users'"
                    )
                )
                existing = {str(row[0]) for row in result.fetchall()}
            for column in columns:
                if column in existing:
                    continue
                await session.execute(text(f"ALTER TABLE app_users ADD COLUMN {column} BOOLEAN"))
                logger.info("Added column %s to app_users", column)
            await session.commit()
    except Exception as exc:  # pragma: no cover - بالا آمدن سامانه نباید بشکند
        logger.warning("Failed to ensure verification columns on app_users: %s", exc)


async def initialize_database():
    """Initialize database and create tables"""
    if "MGX_IGNORE_INIT_DB" in os.environ:
        logger.info("Ignore database initialization")
        return
    start_time = time.time()
    logger.debug("[DB_OP] Starting database initialization")
    try:
        logger.info("🔧 Starting database initialization...")
        await db_manager.init_db()
        logger.info("🔧 Database connection initialized, now creating tables if tables not exist...")
        await db_manager.create_tables()
        logger.info("🔧 Table creation completed")
        await ensure_app_user_verification_columns()
        logger.info("Database initialized successfully")
        logger.debug(f"[DB_OP] Database initialization completed in {time.time() - start_time:.4f}s")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


async def close_database():
    """Close database connections"""
    start_time = time.time()
    logger.debug("[DB_OP] Starting database close")
    try:
        await db_manager.close_db()
        logger.info("Database connections closed")
        logger.debug(f"[DB_OP] Database close completed in {time.time() - start_time:.4f}s")
    except Exception as e:
        logger.error(f"Error closing database: {e}")
        logger.debug(f"[DB_OP] Database close failed in {time.time() - start_time:.4f}s")
