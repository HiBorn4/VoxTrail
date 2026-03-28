import json
import redis
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union
import os
from typing import Dict, Any, Optional, List
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class RedisJSONManager:
    """Manages JSON data storage and retrieval in Redis"""
    
    def __init__(
        self,
        host: str = 'localhost',
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        decode_responses: bool = True,
        key_prefix: str = "travel_data",
        expiry_seconds: Optional[int] = 7200
    ):
        self.key_prefix = key_prefix
        self.expiry_seconds = expiry_seconds
        
        try:
            self.redis_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=decode_responses
            )
            self.redis_client.ping()
            logger.info(f"✅ Connected to Redis at {host}:{port}")
        except redis.ConnectionError as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            raise

    # ---------------- NEW STRUCTURE ----------------
    def _generate_key(self, user_id: str, session_id: str, data_type: str) -> str:
        """Generate a hierarchical Redis key: travel_data:{user_id}:{session_id}:{data_type}"""
        return f"{self.key_prefix}:{user_id}:{session_id}:{data_type}"

    def save_json(
        self,
        data: Union[Dict, Any],
        user_id: str,
        session_id: str,
        data_type: str,
        expiry: Optional[int] = None
    ) -> bool:
        """Save JSON data to Redis using hierarchical key structure"""
        try:
            key = self._generate_key(user_id, session_id, data_type)
            json_str = json.dumps(data, ensure_ascii=False, indent=2)

            if expiry or self.expiry_seconds:
                self.redis_client.setex(key, expiry or self.expiry_seconds, json_str)
            else:
                self.redis_client.set(key, json_str)

            logger.info(f"💾 Saved JSON data to Redis key: {key}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save JSON to Redis: {e}")
            return False

    def load_json(
        self,
        user_id: str,
        session_id: str,
        data_type: str,
        fallback_file_path: Optional[str] = None
    ) -> Optional[Dict]:
        """Load JSON data from Redis using hierarchical key"""
        try:
            key = self._generate_key(user_id, session_id, data_type)
            if json_str := self.redis_client.get(key):
                logger.info(f"📦 Loaded JSON data from Redis key: {key}")
                return json.loads(json_str)
            else:
                logger.warning(f"⚠️ No data found in Redis for key: {key}")
                if fallback_file_path and os.path.exists(fallback_file_path):
                    with open(fallback_file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self.save_json(data, user_id, session_id, data_type)
                    return data
                return None
        except Exception as e:
            logger.error(f"❌ Failed to load JSON from Redis: {e}")
            return None
        
    async def set_key(self, key: str, data: Any, ttl: Optional[int] = None) -> bool:
        """Set a key with JSON data (generic method for any key pattern)"""
        try:
            json_str = json.dumps(data, ensure_ascii=False)
            if ttl:
                self.redis_client.setex(key, ttl, json_str)
            else:
                self.redis_client.set(key, json_str)
            logger.debug(f"Set key: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to set key {key}: {e}")
            return False
    
    async def get_key(self, key: str) -> Optional[Any]:
        """Get data from a key (generic method for any key pattern)"""
        try:
            json_str = self.redis_client.get(key)
            if json_str:
                return json.loads(json_str)
            return None
        except Exception as e:
            logger.error(f"Failed to get key {key}: {e}")
            return None
    
    async def delete_key(self, key: str) -> bool:
        """Delete a key (generic method for any key pattern)"""
        try:
            result = self.redis_client.delete(key)
            logger.debug(f"Deleted key: {key}")
            return result > 0
        except Exception as e:
            logger.error(f"Failed to delete key {key}: {e}")
            return False
        
    async def set_voice_context(self, session_id: str, context: Dict[str, Any], ttl: int = 1800):
        """
        Store voice conversation context
        
        Args:
            session_id: Session identifier
            context: Voice context dictionary containing:
                - conversation_state: str
                - pending_action: dict
                - collected_params: dict
                - missing_params: list
                - retry_count: int
            ttl: Time to live in seconds (default 30 minutes)
        """
        key = f"voice_context:{session_id}"
        await self.set_key(key, context, ttl=ttl)
    
    
    async def get_voice_context(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get voice conversation context
        """
        key = f"voice_context:{session_id}"
        return await self.get_key(key)
    
    
    async def update_voice_context(self, session_id: str, updates: Dict[str, Any]):
        """
        Update specific fields in voice context
        """
        context = await self.get_voice_context(session_id) or {}
        context.update(updates)
        await self.set_voice_context(session_id, context)
    
    
    async def append_voice_transcript(
        self, 
        session_id: str, 
        author: str, 
        text: str
    ):
        """
        Append to voice transcript log
        
        Args:
            session_id: Session identifier
            author: "user" or "agent"
            text: Transcribed text
        """
        key = f"voice_transcript:{session_id}"
        
        # Get existing transcript
        transcript = await self.get_key(key) or {"messages": []}
        
        # Append new message
        transcript["messages"].append({
            "author": author,
            "text": text,
            "timestamp": datetime.now().isoformat()
        })
        
        # Store with TTL
        await self.set_key(key, transcript, ttl=1800)  # 30 minutes
    
    
    async def get_voice_transcript(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get full voice transcript for session
        """
        key = f"voice_transcript:{session_id}"
        transcript = await self.get_key(key) or {"messages": []}
        return transcript.get("messages", [])
    
    
    async def clear_voice_context(self, session_id: str):
        """
        Clear voice context when session ends
        """
        context_key = f"voice_context:{session_id}"
        transcript_key = f"voice_transcript:{session_id}"
        
        await self.delete_key(context_key)
        await self.delete_key(transcript_key)
    
    
    async def store_voice_flight_results(
        self,
        session_id: str,
        trip_type: str,
        flights: Dict[str, Any]
    ):
        """
        Store flight search results from voice query
        Integrates with existing flight caching
        """
        if trip_type == "oneway":
            key = f"es_get_flight_oneway:{session_id}"
        else:
            key = f"es_get_flight_roundtrip:{session_id}"
        
        await self.set_key(key, flights, ttl=1800)
    
    
    async def get_voice_flight_results(
        self,
        session_id: str,
        trip_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached flight results
        """
        if trip_type == "oneway":
            key = f"es_get_flight_oneway:{session_id}"
        else:
            key = f"es_get_flight_roundtrip:{session_id}"
        
        return await self.get_key(key)    

    def exists(self, user_id: str, session_id: str, data_type: str) -> bool:
        """Check if a key exists in Redis"""
        key = self._generate_key(user_id, session_id, data_type)
        return self.redis_client.exists(key) > 0

    def delete(self, user_id: str, session_id: str, data_type: str) -> bool:
        """Delete a specific Redis key"""
        try:
            key = self._generate_key(user_id, session_id, data_type)
            result = self.redis_client.delete(key)
            logger.info(f"🗑️ Deleted key from Redis: {key}")
            return result > 0
        except Exception as e:
            logger.error(f"❌ Failed to delete key from Redis: {e}")
            return False

    def get_ttl(self, user_id: str, session_id: str, data_type: str) -> int:
        """Get remaining TTL for a key"""
        key = self._generate_key(user_id, session_id, data_type)
        return self.redis_client.ttl(key)

    def close(self):
        self.redis_client.close()
        logger.info("🔌 Redis connection closed")
