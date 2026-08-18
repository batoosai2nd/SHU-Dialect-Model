import time
from typing import List, Optional
from uuid import uuid4

from app.schemas.chat import Session, Message
from app.core.logger import log


class SessionManager:
    """
    无状态会话管理器 (Stateless Session Manager)
    所有的数据真实来源直接依赖 DataManager
    完全支持多进程/多实例部署 (Gunicorn/Uvicorn workers > 1)
    """

    def __init__(self, data_manager):
        self._data_manager = data_manager

    def _generate_id(self, prefix: str) -> str:
        """
        抛弃内存计数器，改用 UUID 保证多进程环境下的绝对唯一性
        格式：session_1690000000_a1b2c3d4 或 msg_1690000000_e5f6g7h8
        """
        current_time = int(time.time())
        short_uuid = uuid4().hex[:8]  # 取 8 位 UUID
        return f"{prefix}_{current_time}_{short_uuid}"

    async def create_session(self, model_name: str, prefix: str = "session") -> str:
        """创建新会话并直接落库"""
        session_id = self._generate_id(prefix)

        session = Session(
            session_id=session_id,
            model_name=model_name,
            created_at=int(time.time()),
            updated_at=int(time.time()),
        )

        # 直接持久化到底层数据库
        await self._data_manager.insert_session(session)
        log.info(f"Created new stateless session: {session_id}")
        return session_id

    async def get_session(self, session_id: str) -> Optional[Session]:
        """直接从数据库获取会话及其消息"""
        session = await self._data_manager.get_session(session_id)
        if not session:
            log.warning(f"Session {session_id} not found in DB")
            return None

        # 装载该会话的历史消息
        session.messages = await self._data_manager.get_session_messages(session_id)
        return session

    async def add_message(self, session_id: str, message: Message) -> bool:
        """为会话添加一条新消息"""
        # 验证会话是否存在
        if not await self._data_manager.get_session(session_id):
            log.warning(f"add_message failed: Session {session_id} does not exist.")
            return False

        # 完善消息属性
        new_msg = message.model_copy()
        new_msg.message_id = self._generate_id("msg")
        new_msg.timestamp = int(time.time())

        # 消息落库
        await self._data_manager.insert_message(session_id, new_msg)
        # 更新会话的最后活跃时间
        await self._data_manager.update_session_timestamp(session_id, new_msg.timestamp)

        log.info(f"Added message to DB session {session_id}: {new_msg.content[:20]}...")
        return True

    async def get_history_messages(self, session_id: str) -> List[Message]:
        """直接从数据库拉取历史消息"""
        return await self._data_manager.get_session_messages(session_id)

    async def get_session_list(self) -> List[str]:
        """获取数据库中按时间排序的所有 Session ID"""
        # 在无状态架构下，排序逻辑可以直接交给数据库层 (ORDER BY updated_at DESC)
        # 这里只是做个简单透传提取
        db_sessions = await self._data_manager.get_all_sessions()
        return [s.session_id for s in db_sessions]

    async def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        await self._data_manager.delete_session(session_id)
        log.info(f"Deleted session from DB: {session_id}")
        return True

    async def clear_all_sessions(self):
        """清空数据库中的所有会话"""
        await self._data_manager.clear_all_sessions()
        log.info("All DB sessions cleared.")
