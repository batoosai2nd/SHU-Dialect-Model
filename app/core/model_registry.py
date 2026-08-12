import os
from typing import List, Union
from app.schemas.chat import APIConfig, OllamaConfig
from app.core.config import settings

# 集中管理所有提示词
XIAOHU_PROMPT = """你是来自上海大学的数字人“小沪”，主要与用户进行轻松、友好的上海话和上海文化互动。
用户可能使用上海话、普通话、英文与你交流。请耐心理解用户的意思，并用自然、亲切的方式回应。
你的主要任务是陪用户聊天、分享上海话表达和上海文化，不要把自己表述为上海话教师、权威专家或标准发音示范者，也不要使用“教你上海话”“教大家说上海话”等表述。
如果涉及上海话发音或表达，请注意说明：你的上海话发音可能不够标准，如有不准确之处，请用户多多包涵。
回答时保持温和、友好的语气，不要给回复加“小沪：”前缀，也不要用括号描述动作或表情。"""

# 后续可以继续在这里添加 BEIJING_PROMPT, ENGLISH_TEACHER_PROMPT 等...


# 集中配置所有挂载的模型
def get_all_models() -> List[Union[APIConfig, OllamaConfig]]:
    """获取系统需要挂载的所有模型配置列表"""

    return [
        # 基础大模型 - DeepSeek
        APIConfig(
            model_name="deepseek-chat",
            api_key=settings.DEEPSEEK_API_KEY,
            temperature=0.7,
        ),
        # 提示词封装模型 - 小沪 (基于 DeepSeek)
        APIConfig(
            model_name="小沪(上海话专家)",
            real_model="deepseek-chat",  # 底层引擎
            api_key=settings.DEEPSEEK_API_KEY,
            system_prompt=XIAOHU_PROMPT,  # 注入人设
            greeting="侬好！我是上海大学的小沪，很高兴和侬一起体验上海话、聊聊上海文化。我的上海话发音可能不够标准，如果有不准确的地方，还请侬多多包涵。如果侬发现我哪句话说得不够自然，也欢迎侬指出来，我会认真听取，继续完善自己的上海话表达。侬想和我聊点啥？",
            temperature=0.7,
        ),
        # 基础大模型 - ChatGPT
        APIConfig(
            model_name="gpt-4o-mini",
            api_key=settings.CHATGPT_API_KEY,
            temperature=0.7,
        ),
        # 基础大模型 - Gemini
        APIConfig(
            model_name="gemini-2.5-flash",
            api_key=settings.GEMINI_API_KEY,
            endpoint="",
            temperature=0.7,
            max_tokens=8192,
        ),
        # 本地基础模型 - Ollama
        OllamaConfig(
            model_name="deepseek-r1:1.5b",
            model_desc="本地 Ollama 模型",
            endpoint=settings.OLLAMA_ENDPOINT,
            temperature=0.7,
        ),
    ]
