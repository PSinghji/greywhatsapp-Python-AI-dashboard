"""
MongoDB connection management using Motor (async driver).
FIXED: Proper connection handling, reconnection logic, health checks, and error logging.
"""
import os
import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

logger = logging.getLogger(__name__)

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "wa_campaign")
MONGO_TIMEOUT = int(os.getenv("MONGO_TIMEOUT", "30000"))  # 30 seconds default

client: AsyncIOMotorClient = None
db = None
_connection_healthy = False
_reconnect_task = None


async def connect_db():
    """Connect to MongoDB with proper error handling."""
    global client, db, _connection_healthy, _reconnect_task
    
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            logger.info(f"[Database] Connecting to MongoDB (attempt {retry_count + 1}/{max_retries})...")
            
            # Create client with proper timeout settings
            client = AsyncIOMotorClient(
                MONGO_URL,
                serverSelectionTimeoutMS=MONGO_TIMEOUT,
                connectTimeoutMS=MONGO_TIMEOUT,
                socketTimeoutMS=MONGO_TIMEOUT,
                retryWrites=True,
                maxPoolSize=50,
                minPoolSize=10,
            )
            
            # Test connection
            await asyncio.wait_for(client.admin.command("ping"), timeout=10)
            db = client[DB_NAME]
            _connection_healthy = True
            
            logger.info(f"[Database] Successfully connected to MongoDB: {DB_NAME}")
            
            # Create indexes
            await create_indexes()
            
            # Seed defaults
            await seed_defaults()
            
            # Start reconnect monitor
            if _reconnect_task is None or _reconnect_task.done():
                _reconnect_task = asyncio.create_task(monitor_connection_health())
            
            return
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            retry_count += 1
            logger.error(f"[Database] Connection failed: {e}")
            if retry_count < max_retries:
                wait_time = 2 ** retry_count  # Exponential backoff
                logger.info(f"[Database] Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            else:
                logger.critical(f"[Database] Failed to connect after {max_retries} attempts")
                raise
        except Exception as e:
            logger.critical(f"[Database] Unexpected error: {e}")
            raise


async def create_indexes():
    """Create all necessary database indexes with per-collection error handling."""
    if db is None:
        logger.warning("[Database] Cannot create indexes: db is None")
        return

    logger.info("[Database] Starting index creation...")

    async def safe_create_index(collection_name, *args, **kwargs):
        """Helper to create indexes without stopping the whole process on failure."""
        try:
            coll = db[collection_name]
            await coll.create_index(*args, **kwargs)
        except Exception as e:
            # This catches the "IndexOptionsConflict" but allows others to proceed
            logger.error(f"[Database] Skip index on {collection_name}: {e}")

    # 1. Devices Collection
    try:
        await safe_create_index("devices", "deviceId", unique=True, sparse=True)
        await safe_create_index("devices", "status")
        await safe_create_index("devices", "lastHeartbeat")
        await safe_create_index("devices", [("status", 1), ("lastHeartbeat", -1)])
    except Exception as e: logger.error(f"Devices indexes failed: {e}")

    # 2. Campaigns Collection
    try:
        await safe_create_index("campaigns", "status")
        await safe_create_index("campaigns", "createdAt")
    except Exception as e: logger.error(f"Campaigns indexes failed: {e}")

    # 3. Tasks Collection
    try:
        await safe_create_index("tasks", [("deviceId", 1), ("status", 1)])
        await safe_create_index("tasks", "campaignId")
        await safe_create_index("tasks", "status")
        await safe_create_index("tasks", [("campaignId", 1), ("status", 1)])
        await safe_create_index("tasks", "createdAt")
        await safe_create_index("tasks", "completedAt")
    except Exception as e: logger.error(f"Tasks indexes failed: {e}")

    # 4. Activity Logs (The specific problematic area)
    try:
        await safe_create_index("activity_logs", "createdAt")
        await safe_create_index("activity_logs", "eventType")
        await safe_create_index("activity_logs", "deviceId")
        await safe_create_index("activity_logs", "level")
        # If this next line fails due to permissions/conflicts, it won't crash the app
        # await db.activity_logs.create_index("createdAt", expireAfterSeconds=7776000) 
    except Exception as e: logger.error(f"Activity logs indexes failed: {e}")

    # 5. Device Communication (New Features)
    try:
        await safe_create_index("device_comm_tasks", "status")
        await safe_create_index("device_comm_tasks", "senderDeviceId")
        await safe_create_index("device_comm_tasks", "createdAt")
        await safe_create_index("device_comm_logs", "date")
    except Exception as e: logger.error(f"Device Comm indexes failed: {e}")

    # 6. Others
    await safe_create_index("tuning_profiles", "name", unique=True, sparse=True)
    await safe_create_index("api_keys", "key", unique=True, sparse=True)

    logger.info("[Database] Index creation process finished.")

async def seed_defaults():
    """Seed default data if needed."""
    try:
        if db is None:
            logger.warning("[Database] Cannot seed defaults: db is None")
            return
            
        # Default tuning profile
        existing = await db.tuning_profiles.find_one({"name": "Default"})
        if not existing:
            await db.tuning_profiles.insert_one({
                "name": "Default",
                "description": "Balanced human-like typing profile",
                "typingSpeedMin": 30,
                "typingSpeedMax": 80,
                "messageDelayMin": 2000,
                "messageDelayMax": 5000,
                "betweenRecipientsMin": 5000,
                "betweenRecipientsMax": 15000,
                "typingMistakesEnabled": True,
                "typingMistakesRate": 0.02,
                "randomPausesEnabled": True,
                "randomPauseChance": 0.10,
                "randomPauseMin": 500,
                "randomPauseMax": 2000,
                "maxRetries": 3,
                "isDefault": True,
            })
            logger.info("[Database] Default tuning profile created")
    except Exception as e:
        logger.error(f"[Database] Error seeding defaults: {e}")


async def monitor_connection_health():
    """Background task: monitor MongoDB connection health."""
    global _connection_healthy
    
    while True:
        try:
            await asyncio.sleep(30)  # Check every 30 seconds
            
            if client is None or db is None:
                _connection_healthy = False
                logger.warning("[Database] Connection health check: client/db is None")
                continue
            
            # Ping the database
            await asyncio.wait_for(client.admin.command("ping"), timeout=5)
            _connection_healthy = True
            
        except Exception as e:
            _connection_healthy = False
            logger.error(f"[Database] Connection health check failed: {e}")
            
            # Try to reconnect
            try:
                logger.info("[Database] Attempting to reconnect...")
                await connect_db()
            except Exception as reconnect_error:
                logger.error(f"[Database] Reconnection failed: {reconnect_error}")


async def close_db():
    """Close MongoDB connection."""
    global client, _reconnect_task, _connection_healthy
    
    try:
        if _reconnect_task and not _reconnect_task.done():
            _reconnect_task.cancel()
            try:
                await _reconnect_task
            except asyncio.CancelledError:
                pass
        
        if client:
            client.close()
            _connection_healthy = False
            logger.info("[Database] Connection closed")
    except Exception as e:
        logger.error(f"[Database] Error closing connection: {e}")


def get_db():
    """Get database instance with health check."""
    global db, _connection_healthy
    
    if db is None:
        logger.error("[Database] Database not initialized")
        return None
    
    if not _connection_healthy:
        logger.warning("[Database] Connection health check failed - returning db anyway (may fail)")
    
    return db


async def ensure_connected():
    """Ensure database is connected before operations."""
    if db is None or not _connection_healthy:
        logger.warning("[Database] Reconnecting...")
        await connect_db()
