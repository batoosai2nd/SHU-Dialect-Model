import os
import pytest
import pytest_asyncio
from typing import AsyncGenerator

from app.db.data_manager import DataManager
from app.services.session_manager import SessionManager
from app.services.llm_manager import LLMManager
from app.services.unified_llm_provider import UnifiedLLMProvider
from app.schemas.chat import Message
from app.core.logger import log

# 准备测试夹具
# 作用：在每次测试前创建一个干净的、独立的测试数据库
TEST_DB_PATH = "./test_chat.db"
TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH}"


@pytest_asyncio.fixture
async def data_manager() -> AsyncGenerator[DataManager, None]:
    """数据库管理器 Fixture"""
    # 实例化 DataManager 并连接到测试数据库
    dm = DataManager(TEST_DB_URL)
    await dm.init_database()

    yield dm  # 将 dm 交给测试用例使用

    # 测试结束后的清理工作：删除测试数据库文件
    await dm.engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
        log.info("测试完毕，已清理测试数据库文件。")


@pytest_asyncio.fixture
async def session_manager(data_manager: DataManager) -> SessionManager:
    """会话管理器 Fixture (依赖于 data_manager)"""
    # 组装无状态的 SessionManager
    return SessionManager(data_manager)


@pytest_asyncio.fixture
def llm_manager() -> LLMManager:
    """大模型调度器 Fixture"""
    return LLMManager()


# 测试用例 1：测试 DataManager 和 SessionManager 的持久化联动
@pytest.mark.asyncio
async def test_session_and_data_manager(session_manager: SessionManager):
    log.info("--- 开始测试 Session & Data Manager 联动 ---")

    # 创建会话 (模拟新用户进群)
    test_model = "deepseek-chat"
    session_id = await session_manager.create_session(test_model)
    assert session_id is not None
    assert session_id.startswith("session_")
    log.info(f"创建的 Session ID: {session_id}")

    # 模拟用户发送第一条消息
    user_msg_1 = Message(role="user", content="你好，数据库能记住我吗？")
    await session_manager.add_message(session_id, user_msg_1)

    # 模拟 AI 回复第一条消息
    ai_msg_1 = Message(role="assistant", content="当然，我已经把你的话存入 SQLite 啦！")
    await session_manager.add_message(session_id, ai_msg_1)

    # 获取历史记录，验证数量和顺序
    history = await session_manager.get_history_messages(session_id)
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[1].role == "assistant"

    # 验证会话列表查询
    session_list = await session_manager.get_session_list()
    assert len(session_list) == 1
    assert session_list[0] == session_id

    # 删除会话，验证级联删除是否生效
    await session_manager.delete_session(session_id)
    history_after_delete = await session_manager.get_history_messages(session_id)
    assert (
        len(history_after_delete) == 0
    )  # 消息应该因为外键的 ON DELETE CASCADE 被一并清空
    log.info("--- Session & Data Manager 联动测试通过 ---")


@pytest.mark.asyncio
async def test_museum_session_cleanup(data_manager: DataManager):
    """只清理过期的文学馆临时会话，保留普通会话和未过期临时会话。"""
    session_manager = SessionManager(data_manager)
    regular_id = await session_manager.create_session("deepseek-chat")
    expired_museum_id = await session_manager.create_session(
        "小沪(上海话互动)", prefix="museum_session"
    )
    active_museum_id = await session_manager.create_session(
        "小沪(上海话互动)", prefix="museum_session"
    )

    await data_manager.update_session_timestamp(expired_museum_id, 100)
    deleted_count = await data_manager.delete_expired_museum_sessions(200)

    assert deleted_count == 1
    assert await data_manager.get_session(expired_museum_id) is None
    assert await data_manager.get_session(regular_id) is not None
    assert await data_manager.get_session(active_museum_id) is not None


# 测试用例 2：测试 LLMManager 的路由与注册机制
@pytest.mark.asyncio
async def test_llm_manager_routing(llm_manager: LLMManager):
    log.info("--- 开始测试 LLM Manager 路由机制 ---")

    model_name = "test-ollama-model"

    # 注册一个 Provider (使用 Ollama 作为本地测试代表，无需真实的 API Key)
    provider = UnifiedLLMProvider(provider_type="ollama", model_name="qwen")
    register_success = llm_manager.register_provider(model_name, provider)
    assert register_success is True

    # 验证刚注册时不可用 (符合我们在 C++ 里的设计逻辑：注册后需初始化才可用)
    assert llm_manager.is_model_available(model_name) is False

    # 初始化模型
    init_success = await llm_manager.init_model(
        model_name, {"endpoint": "http://192.168.71.103:11434"}
    )
    assert init_success is True

    # 验证可用状态
    assert llm_manager.is_model_available(model_name) is True

    # 获取所有可用模型列表
    available_models = llm_manager.get_available_models()
    assert len(available_models) == 1
    assert available_models[0].model_name == model_name

    log.info("--- LLM Manager 路由机制测试通过 ---")
