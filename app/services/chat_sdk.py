import asyncio
from typing import List, Union, AsyncGenerator, Dict, Any

from app.schemas.chat import Message, ModelInfo, APIConfig, OllamaConfig
from app.services.llm_manager import LLMManager
from app.services.session_manager import SessionManager
from app.services.unified_llm_provider import UnifiedLLMProvider
from app.core.logger import log


class ChatSDK:
    def __init__(self, llm_manager: LLMManager, session_manager: SessionManager):
        self._llm_manager = llm_manager
        self._session_manager = session_manager
        self._initialized = False

        # 缓存配置信息，用于后续组装 requestParam (如 temperature, max_tokens)
        self._model_configs: Dict[str, Union[APIConfig, OllamaConfig]] = {}

    def _infer_provider_type(self, model_name: str) -> str:
        """辅助方法：根据模型名称推断所属提供商"""
        name_lower = model_name.lower()
        if "deepseek" in name_lower:
            return "deepseek"
        if "gpt" in name_lower:
            return "openai"
        if "gemini" in name_lower:
            return "gemini"
        return "openai"  # 默认 fallback

    async def init_models(self, configs: List[Union[APIConfig, OllamaConfig]]) -> bool:
        """初始化所有支持的模型"""
        for config in configs:
            model_name = config.model_name

            # 提取真实的底层模型名称
            real_model = config.real_model if config.real_model else config.model_name

            # 注册 Provider
            if not self._llm_manager.is_model_available(model_name):
                if isinstance(config, OllamaConfig):
                    provider = UnifiedLLMProvider(
                        "ollama", real_model, config.model_desc
                    )
                else:
                    provider_type = self._infer_provider_type(real_model)
                    provider = UnifiedLLMProvider(provider_type, real_model)

                # 注册时依然使用 UI上的 model_name 映射
                self._llm_manager.register_provider(model_name, provider)

            # 初始化 Provider (注入 Key 和 Endpoint)
            # 将 Pydantic 的 Config 对象转为字典传递给底层的 init_model
            model_params = {}
            if isinstance(config, APIConfig):
                model_params["api_key"] = config.api_key
                # 如果用户配置了 endpoint 则传入，否则用空字符串让 litellm 使用官方默认
                model_params["endpoint"] = getattr(config, "endpoint", "")
            elif isinstance(config, OllamaConfig):
                model_params["endpoint"] = config.endpoint

            success = await self._llm_manager.init_model(model_name, model_params)
            if success:
                self._model_configs[model_name] = config
            else:
                log.error(f"ChatSDK: failed to init model {model_name}")

        self._initialized = True
        log.info("ChatSDK initialized successfully.")
        return True

    # ================= 会话管理 =================
    async def create_session(
        self, model_name: str, session_prefix: str = "session"
    ) -> str:
        if not self._initialized:
            raise RuntimeError("ChatSDK is not initialized")
        session_id = await self._session_manager.create_session(
            model_name, prefix=session_prefix
        )

        # 【新增】：自动插入自我介绍开场白到数据库
        config = self._model_configs.get(model_name)
        if config and config.greeting:
            greeting_msg = Message(role="assistant", content=config.greeting)
            await self._session_manager.add_message(session_id, greeting_msg)

        return session_id

    async def get_session(self, session_id: str):
        if not self._initialized:
            raise RuntimeError("ChatSDK is not initialized")
        return await self._session_manager.get_session(session_id)

    async def get_session_list(self) -> List[str]:
        if not self._initialized:
            raise RuntimeError("ChatSDK is not initialized")
        return await self._session_manager.get_session_list()

    async def delete_session(self, session_id: str) -> bool:
        if not self._initialized:
            raise RuntimeError("ChatSDK is not initialized")
        return await self._session_manager.delete_session(session_id)

    def get_available_models(self) -> List[ModelInfo]:
        """获取当前可用的模型列表"""
        return self._llm_manager.get_available_models()

    # ================= 消息发送 =================
    async def send_message(self, session_id: str, message_content: str) -> str:
        """给模型发消息 - 全量返回"""
        if not self._initialized:
            raise RuntimeError("ChatSDK is not initialized")

        session = await self.get_session(session_id)
        if not session:
            log.error(f"ChatSDK.send_message: session {session_id} not found")
            return ""

        # 保存用户提问
        user_msg = Message(role="user", content=message_content)
        await self._session_manager.add_message(session_id, user_msg)

        # 获取完整的历史上下文
        history = await self._session_manager.get_history_messages(session_id)

        # 构建请求参数
        config = self._model_configs.get(session.model_name)
        request_param = {
            "temperature": config.temperature if config else 0.7,
            "max_tokens": config.max_tokens if config else 2048,
            "system_prompt": config.system_prompt if config else "",  # 透传给底层
        }

        # 调用 LLM 发送消息
        response = await self._llm_manager.send_message(
            session.model_name, history, request_param
        )

        # 保存助手消息
        if response:
            ai_msg = Message(role="assistant", content=response)
            await self._session_manager.add_message(session_id, ai_msg)
            log.info(f"ChatSDK.send_message: success for model {session.model_name}")

        return response

    async def send_message_stream(
        self, session_id: str, message_content: str
    ) -> AsyncGenerator[str, None]:
        """给模型发送消息 - 增量返回 (流式打字机)"""
        if not self._initialized:
            raise RuntimeError("ChatSDK is not initialized")

        session = await self.get_session(session_id)
        if not session:
            log.error(f"ChatSDK.send_message_stream: session {session_id} not found")
            yield "Error: Session not found"
            return

        # 保存用户提问
        user_msg = Message(role="user", content=message_content)
        await self._session_manager.add_message(session_id, user_msg)

        # 获取上下文与参数
        history = await self._session_manager.get_history_messages(session_id)
        config = self._model_configs.get(session.model_name)
        request_param = {
            "temperature": config.temperature if config else 0.7,
            "max_tokens": config.max_tokens if config else 2048,
        }

        # 流式处理与后台持久化
        full_response = ""
        try:
            # 不断将大模型产生的流式 chunk yield 给前端
            async for chunk in self._llm_manager.send_message_stream(
                session.model_name, history, request_param
            ):
                if chunk:
                    full_response += chunk
                    yield chunk

        finally:
            # 无论生成是否正常结束，或者用户前端主动断开网络连接
            # try...finally 都会保证将已生成的文本拼装后，持久化到数据库中
            if full_response:
                ai_msg = Message(role="assistant", content=full_response)
                # 使用 asyncio.shield 保护写入数据库的操作不被取消
                await asyncio.shield(
                    self._session_manager.add_message(session_id, ai_msg)
                )
                log.info(
                    f"ChatSDK.send_message_stream: stream finished & saved for {session.model_name}"
                )
