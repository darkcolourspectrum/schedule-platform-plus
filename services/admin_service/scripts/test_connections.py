"""Test database connections"""
import asyncio
import sys
sys.path.append('.')

from app.database.connection import test_admin_db_connection, test_auth_db_connection
from app.database.redis_client import redis_client

async def main():
    print("Testing connections...")
    
    await redis_client.connect()
    if redis_client.is_connected:
        print("✅ Redis connected")
    else:
        print("❌ Redis failed")
    
    admin_ok = await test_admin_db_connection()
    if admin_ok:
        print("✅ Admin DB connected")
    else:
        print("❌ Admin DB failed")
    
    auth_ok = await test_auth_db_connection()
    if auth_ok:
        print("✅ Auth DB (READ-ONLY) connected")
    else:
        print("❌ Auth DB failed")
    
    await redis_client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
