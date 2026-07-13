# app/core/utils/celery_worker.py

import asyncio
from celery.schedules import crontab
from celery.utils.log import get_task_logger
from celery.app.control import Inspect
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.analysis.analysis import run_analysis, run_supplier_name_validation
from app.core.security.jwt import create_jwt_token
from app.core.utils.celery_app import celery_app
from app.core.config import get_settings
# from app.core.analysis.analysis import run_analysis
# from app.core.analysis.fallback import trigger_from_db_if_needed
from app.core.utils.redis_client import rdb, SESSION_SET_KEY, VALIDATION_SESSION_SET_KEY

logger = get_task_logger(__name__)

def safe_async_run(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)

# === Periodic Queue Task ===
@celery_app.task(
    bind=True,
    name="process_analysis_session_queue",
    queue="analysis_session_queue",
    max_retries=3
)
def process_analysis_session_queue(self, session_id: str):
    logger.info(f"Starting run_full_pipeline_background for : {session_id}")
    before = rdb.smembers(SESSION_SET_KEY)
    logger.info(f"Redis SET BEFORE: {before}")

    async def async_task():
        settings = get_settings()
        engine = create_async_engine(settings.sqlalchemy_database_uri, echo=True)
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as session:
            await run_analysis({"session_id": session_id}, session)

    try:
        safe_async_run(async_task())
    except Exception as e:
        logger.error(f"[Celery] Error processing session {session_id}: {e}")
        raise
    finally:
        removed = rdb.srem(SESSION_SET_KEY, session_id)
        logger.info(f"Redis removal success: {removed}")
    after = rdb.smembers(SESSION_SET_KEY)
    logger.info(f"[Celery] Finished processing session: {session_id}")
    return f"[Celery] Finished processing session: {session_id}"


# === Periodic Queue Task ===
@celery_app.task(
    bind=True,
    name="process_validation_session_queue",
    queue="validation_session_queue",
    max_retries=3
)
def process_validation_session_queue(self, session_id: str):
    logger.info(f"Starting run_full_validation_pipeline_background for : {session_id}")
    before = rdb.smembers(VALIDATION_SESSION_SET_KEY)
    logger.info(f"Redis SET BEFORE: {before}")

    async def async_task():
        settings = get_settings()
        engine = create_async_engine(settings.sqlalchemy_database_uri, echo=True)
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as session:
            await run_supplier_name_validation({"session_id": session_id}, session)

    try:
        safe_async_run(async_task())
    except Exception as e:
        logger.error(f"[Celery] Error processing session {session_id}: {e}")
        raise
    finally:
        removed = rdb.srem(VALIDATION_SESSION_SET_KEY, session_id)
        logger.info(f"Redis removal success: {removed}")
    after = rdb.smembers(VALIDATION_SESSION_SET_KEY)
    logger.info(f"[Celery] Finished processing session: {session_id}")
    return f"[Celery] Finished processing session: {session_id}"
