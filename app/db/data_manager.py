from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, update, delete, func, event
from typing import List, Optional

from app.schemas.chat import Session, Message
from app.db.models import Base, SessionModel, MessageModel
from app.core.logger import log


class DataManager:
    def __init__(self, db_url: str = "sqlite+aiosqlite:///./chat.db"):
        """
        初始化数据库引擎
        :param db_url: 数据库连接字符串，默认使用当前目录下的 chat.db
        """
        # 创建异步引擎 (echo=False 关闭原生 SQL 打印，如果需要调试可以设为 True)
        self.engine = create_async_engine(db_url, echo=False)

        # 开启 SQLite 外键约束
        @event.listens_for(self.engine.sync_engine, "connect")
        def enable_sqlite_fk(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        # 创建异步会话工厂 (替代 C++ 中每次操作创建的 sqlite 句柄)
        self.async_session_maker = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def init_database(self):
        """初始化数据库表 (替代 C++ initDataBase 中的 CREATE TABLE)"""
        async with self.engine.begin() as conn:
            # SQLAlchemy 会自动检测表是否存在，并创建表
            await conn.run_sync(Base.metadata.create_all)
        log.info("DataManager: 数据库表初始化完成")

    # Session 相关的 CRUD 操作
    async def insert_session(self, session: Session) -> bool:
        """插入会话"""
        async with self.async_session_maker() as db_session:
            # 将 Pydantic 对象转换为 SQLAlchemy ORM 对象
            db_obj = SessionModel(
                session_id=session.session_id,
                model_name=session.model_name,
                create_time=session.created_at,
                update_time=session.updated_at,
            )
            db_session.add(db_obj)
            await db_session.commit()  # 自动提交事务
            log.info(f"DataManager: Insert session success: {session.session_id}")
            return True

    async def get_session(self, session_id: str) -> Optional[Session]:
        """获取指定 sessionId 的会话信息"""
        async with self.async_session_maker() as db_session:
            # 替代 C++: SELECT * FROM sessions WHERE session_id = ?
            stmt = select(SessionModel).where(SessionModel.session_id == session_id)
            result = await db_session.execute(stmt)
            db_obj = result.scalar_one_or_none()

            if db_obj:
                # 转换回 Pydantic 对象返回
                return Session(
                    session_id=db_obj.session_id,
                    model_name=db_obj.model_name,
                    created_at=db_obj.create_time,
                    updated_at=db_obj.update_time,
                    messages=[],  # 历史消息采用懒加载策略
                )

            log.warning(f"DataManager.get_session: Session not found: {session_id}")
            return None

    async def update_session_timestamp(self, session_id: str, timestamp: int) -> bool:
        """更新指定会话的时间戳"""
        async with self.async_session_maker() as db_session:
            # 替代 C++: UPDATE sessions SET update_time = ? WHERE session_id = ?
            stmt = (
                update(SessionModel)
                .where(SessionModel.session_id == session_id)
                .values(update_time=timestamp)
            )

            await db_session.execute(stmt)
            await db_session.commit()
            return True

    async def rename_session_model(self, old_name: str, new_name: str) -> int:
        """迁移模型展示名，保证改名前创建的历史会话仍可继续使用。"""
        async with self.async_session_maker() as db_session:
            stmt = (
                update(SessionModel)
                .where(SessionModel.model_name == old_name)
                .values(model_name=new_name)
            )
            result = await db_session.execute(stmt)
            await db_session.commit()
            updated_count = result.rowcount or 0

            if updated_count:
                log.info(
                    "DataManager: 已迁移 {} 个旧版小沪会话模型名",
                    updated_count,
                )

            return updated_count

    async def delete_session(self, session_id: str) -> bool:
        """删除指定会话 (由于设置了 cascade，关联的 messages 也会自动删除)"""
        async with self.async_session_maker() as db_session:
            stmt = delete(SessionModel).where(SessionModel.session_id == session_id)
            await db_session.execute(stmt)
            await db_session.commit()
            log.info(f"DataManager: Deleted session: {session_id}")
            return True

    async def get_all_sessions(self) -> List[Session]:
        """获取所有session信息，并按照更新时间降序排列"""
        async with self.async_session_maker() as db_session:
            stmt = select(SessionModel).order_by(SessionModel.update_time.desc())
            result = await db_session.execute(stmt)
            db_sessions = result.scalars().all()

            return [
                Session(
                    session_id=obj.session_id,
                    model_name=obj.model_name,
                    created_at=obj.create_time,
                    updated_at=obj.update_time,
                    messages=[],  # 依然保持为空，懒加载
                )
                for obj in db_sessions
            ]

    async def clear_all_sessions(self) -> bool:
        """删除所有会话"""
        async with self.async_session_maker() as db_session:
            await db_session.execute(delete(SessionModel))
            await db_session.commit()
            log.info("DataManager: clearAllSessions - 删除所有会话成功")
            return True

    async def delete_expired_museum_sessions(self, cutoff_timestamp: int) -> int:
        """删除文学馆设备遗留的过期临时会话，不影响普通网页会话。"""
        async with self.async_session_maker() as db_session:
            stmt = delete(SessionModel).where(
                SessionModel.session_id.startswith(
                    "museum_session_", autoescape=True
                ),
                SessionModel.update_time < cutoff_timestamp,
            )
            result = await db_session.execute(stmt)
            await db_session.commit()
            deleted_count = result.rowcount or 0

            if deleted_count:
                log.info(
                    "DataManager: 已清理 {} 个文学馆过期临时会话",
                    deleted_count,
                )

            return deleted_count

    async def get_session_count(self) -> int:
        """获取会话总数"""
        async with self.async_session_maker() as db_session:
            stmt = select(func.count(SessionModel.session_id))
            result = await db_session.execute(stmt)
            count = result.scalar() or 0
            log.info(f"DataManager: 获取会话总数成功：{count}")
            return count

    # Message 相关的 CRUD 操作
    async def insert_message(self, session_id: str, message: Message) -> bool:
        """
        插入新消息，并同步更新会话的时间戳。
        由于使用 ORM 事务，这两步要么同时成功，要么同时失败，完全不需要手动处理回滚！
        """
        async with self.async_session_maker() as db_session:
            async with db_session.begin():  # 开启数据库事务
                # 插入消息
                msg_obj = MessageModel(
                    message_id=message.message_id,
                    session_id=session_id,
                    role=message.role,
                    content=message.content,
                    timestamp=message.timestamp,
                )
                db_session.add(msg_obj)

                # 更新会话时间戳
                update_stmt = (
                    update(SessionModel)
                    .where(SessionModel.session_id == session_id)
                    .values(update_time=message.timestamp)
                )

                await db_session.execute(update_stmt)

            # 事务自动 commit
            log.info(f"DataManager: Insert message success: {message.message_id}")
            return True

    async def get_session_messages(self, session_id: str) -> List[Message]:
        """获取会话中的所有消息"""
        async with self.async_session_maker() as db_session:
            # 替代 : SELECT * FROM messages ORDER BY timestamp ASC
            stmt = (
                select(MessageModel)
                .where(MessageModel.session_id == session_id)
                .order_by(MessageModel.timestamp.asc())
            )

            result = await db_session.execute(stmt)
            db_messages = result.scalars().all()

            return [
                Message(
                    message_id=msg.message_id,
                    role=msg.role,
                    content=msg.content,
                    timestamp=msg.timestamp,
                )
                for msg in db_messages
            ]
