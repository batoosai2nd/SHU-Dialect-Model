from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import time
from uuid import uuid4


# 辅助函数：获取当前时间戳
def current_timestamp() -> int:
    return int(time.time())


# 辅助函数：自动生成 ID
def generate_uuid() -> str:
    return str(uuid4())


# 消息结构 (Message)
class Message(BaseModel):
    # Field(default_factory=...) 可以在对象创建时自动执行函数赋值，省去手写构造函数
    message_id: str = Field(default_factory=generate_uuid, description="消息ID")

    # 使用 Literal 限制 role 只能是这三种类型，比纯 str 更安全
    role: Literal["system", "user", "assistant"] = Field(..., description="角色")
    content: str = Field(..., description="消息内容")

    timestamp: int = Field(
        default_factory=current_timestamp, description="消息发送时间戳"
    )


# 模型配置结构 (Config)
class LLMConfig(BaseModel):
    # 注册给前端 UI 看的名字 (如: "小沪(上海话互动)")
    model_name: str 
    
    # 底层实际调用的模型名称 (如: "deepseek-chat")
    real_model: Optional[str] = None 
    
    # 系统人设提示词 (不存入DB，每次请求时动态拼接)
    system_prompt: Optional[str] = "" 
    
    # 模型的自我介绍开场白 (创建会话时自动存入DB)
    greeting: Optional[str] = ""
    
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = 2048


# 继承：API配置 与 Ollama 配置
class APIConfig(LLMConfig):
    api_key: str
    endpoint: Optional[str] = ""


class OllamaConfig(LLMConfig):
    model_desc: Optional[str] = ""
    endpoint: str


# LLM 信息
class ModelInfo(BaseModel):
    model_name: str = ""
    model_desc: str = ""
    provider: str = ""
    endpoint: str = ""
    is_available: bool = False


# 会话信息
class Session(BaseModel):
    session_id: str = Field(default_factory=generate_uuid)
    model_name: str = ""
    # 自动初始化为一个空列表，对应 std::vector<Message>
    messages: List[Message] = Field(default_factory=list)
    created_at: int = Field(default_factory=current_timestamp)
    updated_at: int = Field(default_factory=current_timestamp)
