import os
import json
import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx
import urllib.parse

from app.db.data_manager import DataManager
from app.services.session_manager import SessionManager
from app.services.llm_manager import LLMManager
from app.services.chat_sdk import ChatSDK
from app.schemas.chat import APIConfig, OllamaConfig
from app.core.logger import log

from app.core.model_registry import get_all_models
from app.tts.xiaohu_tts import XiaoHuTTS

import shutil
import tempfile
from fastapi import File, UploadFile, Form  # 处理文件上传
from app.asr.shanghai_asr import ShanghaiASR  # 引入沪语 ASR 模块
from app.asr.ali_asr import AliASR  # 引入阿里云 ASR 模块

from app.core.config import settings

# 生命周期管理
sdk_instance = None  # 全局 SDK 实例
# 实例化 TTS 服务
xiaohu_tts_service = XiaoHuTTS()
# 实例化 ASR 服务
asr_shanghai_service = ShanghaiASR()
asr_ali_service = AliASR()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global sdk_instance, asr_instance
    log.info("ChatServer: 正在初始化数据库与 ChatSDK...")

    # 初始化数据库
    db_manager = DataManager(settings.DATABASE_URL)
    await db_manager.init_database()
    await db_manager.rename_session_model(
        "小沪(上海话专家)",
        "小沪(上海话互动)",
    )

    # 实例化 Managers
    session_manager = SessionManager(db_manager)
    llm_manager = LLMManager()
    sdk_instance = ChatSDK(llm_manager, session_manager)

    async def cleanup_expired_museum_sessions():
        """定时兜底清理异常退出后残留的文学馆临时会话。"""
        retention_seconds = max(settings.MUSEUM_SESSION_RETENTION_HOURS, 1) * 3600
        interval_seconds = max(settings.MUSEUM_CLEANUP_INTERVAL_SECONDS, 60)

        while True:
            try:
                cutoff = int(time.time()) - retention_seconds
                await db_manager.delete_expired_museum_sessions(cutoff)
            except Exception as exc:
                log.error(f"清理文学馆临时会话失败: {exc}")

            await asyncio.sleep(interval_seconds)

    # 调用统一配置函数组装模型配置
    configs = get_all_models()

    # 启动 SDK
    if await sdk_instance.init_models(configs):
        log.info(f"ChatServer: 成功挂载了 {len(configs)} 个模型!!!")
    else:
        log.error("ChatServer: ChatSDK 初始化失败!!!")

    # 预热 ASR 客户端 (扔到后台线程执行，不阻塞 FastAPI 启动)
    asyncio.create_task(asyncio.to_thread(asr_shanghai_service.init_client_sync))
    museum_cleanup_task = asyncio.create_task(cleanup_expired_museum_sessions())

    try:
        yield  # 将控制权交还给 FastAPI，服务器正式开始接收请求
    finally:
        museum_cleanup_task.cancel()
        try:
            await museum_cleanup_task
        except asyncio.CancelledError:
            pass

    # 服务器停止时的清理逻辑
    log.info("ChatServer: HTTP 服务已停止，资源清理完毕。")


# FastAPI 实例与中间件配置
app = FastAPI(lifespan=lifespan, title="AI Chat API", version="1.0")

# 允许跨域请求 (对应 C++ 里的 Access-Control-Allow-Origin: *)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic 接收体定义
class CreateSessionReq(BaseModel):
    model: str = "deepseek-chat"


class SendMessageReq(BaseModel):
    session_id: str
    message: str


# 通用响应生成器
def standard_response(
    success: bool, message: str, data: dict = None, status_code: int = 200
):
    content = {"success": success, "message": message}
    if data is not None:
        content["data"] = data
    return JSONResponse(status_code=status_code, content=content)


# HTTP 路由注册


@app.post("/api/session")
async def create_session(req: CreateSessionReq, request: Request):
    """处理创建会话请求"""
    is_museum_client = request.headers.get("X-Xiaohu-Client") == "museum"
    session_prefix = "museum_session" if is_museum_client else "session"
    session_id = await sdk_instance.create_session(
        req.model, session_prefix=session_prefix
    )
    if not session_id:
        return standard_response(
            False, "create session failed (Internal Error)", status_code=500
        )

    return standard_response(
        True, "create session success", {"session_id": session_id, "model": req.model}
    )


@app.get("/api/sessions")
async def get_session_lists():
    """处理获取会话列表请求"""
    session_ids = await sdk_instance.get_session_list()
    data_array = []

    for sid in session_ids:
        session = await sdk_instance.get_session(sid)
        if session:
            first_msg = session.messages[0].content if session.messages else "新会话"
            data_array.append(
                {
                    "id": session.session_id,
                    "model": session.model_name,
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                    "message_count": len(session.messages),
                    "first_user_message": first_msg,
                }
            )

    return standard_response(True, "get session lists success", data_array)


@app.get("/api/models")
async def get_model_lists():
    """处理获取可用模型列表请求"""
    models = sdk_instance.get_available_models()
    data_array = [{"name": m.model_name, "desc": m.model_desc} for m in models]
    return standard_response(True, "get model lists success", data_array)


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """处理删除会话请求"""
    ret = await sdk_instance.delete_session(session_id)
    if ret:
        return standard_response(True, "delete session success")
    else:
        return standard_response(
            False, "delete session failed, session not found", status_code=404
        )


@app.get("/api/session/{session_id}/history")
async def get_history_messages(session_id: str):
    """处理获取历史消息请求"""
    session = await sdk_instance.get_session(session_id)
    if not session:
        return standard_response(False, "session not found", status_code=404)

    data_array = [
        {
            "id": msg.message_id,
            "role": msg.role,
            "content": msg.content,
            "timestamp": msg.timestamp,
        }
        for msg in session.messages
    ]

    return standard_response(True, "get history messages success", data_array)


@app.post("/api/message")
async def send_message_full(req: SendMessageReq):
    """处理发送消息请求 - 全量返回（并尝试同步调用 TTS）"""
    # 调用大模型获取文本回复
    response_text = await sdk_instance.send_message(req.session_id, req.message)
    if not response_text:
        return standard_response(
            False, "Failed to send AI response message", status_code=500
        )

    # 判断该会话是否属于“小沪”，如果是，则请求语音合成
    audio_url = None
    session = await sdk_instance.get_session(req.session_id)
    if session and "小沪" in session.model_name:
        # 获取原始的 HTTP 链接
        raw_audio_url = await xiaohu_tts_service.generate_audio(response_text)

        if raw_audio_url:
            # 【关键修改】：将 HTTP 外部链接进行 URL 编码，包装成我们的内部代理路径
            encoded_url = urllib.parse.quote(raw_audio_url, safe="")
            # 因为前端 script.js 使用相对路径，这里直接返回 /api/... 即可
            audio_url = f"/api/audio/proxy?url={encoded_url}"

    # 将文本和可能存在的音频链接一起返回给前端
    return standard_response(
        True,
        "send message success",
        {
            "session_id": req.session_id,
            "response": response_text,
            "audio_url": audio_url,  # 返回音频地址
        },
    )


@app.post("/api/message/async")
async def send_message_stream(req: SendMessageReq):
    """
    处理发送消息请求 - 增量返回
    """

    async def event_generator():
        # json.dumps 替代了 C++ 的 Json::valueToQuotedString，确保 \n 被安全转义为 "\\n"
        yield f"data: {json.dumps('', ensure_ascii=False)}\n\n"

        try:
            # 遍历底层的 AsyncGenerator
            async for chunk in sdk_instance.send_message_stream(
                req.session_id, req.message
            ):
                if chunk:
                    # 遵循 SSE 协议格式：data: "文本内容"\n\n
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

            # 流结束标记
            yield "data: [DONE]\n\n"

        except Exception as e:
            log.error(f"Streaming Error: {e}")
            yield f"data: {json.dumps('[ERROR] Stream Failed', ensure_ascii=False)}\n\n"

    # StreamingResponse 会自动设置 Transfer-Encoding: chunked
    # 只需设置 media_type 即可
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/api/audio/recognize")
async def recognize_audio_api(
    file: UploadFile = File(...),
    asr_model: str = Form("shanghai"),  # 前端传入的 ASR 模型标识，默认为 "shanghai"
):
    """处理前端发送的语音识别请求"""
    if not file:
        return standard_response(False, "未接收到音频文件", status_code=400)

    try:
        # 将上传的音频流保存为服务器的本地临时文件
        ext = os.path.splitext(file.filename)[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        # 根据前端请求的模型标识，路由分发并转码
        recognized_text = ""

        try:
            if asr_model == "ali":
                # 将任意格式转换为 16kHz单声道 wav
                import pydub

                wav_path = tmp_path + ".wav"

                audio = pydub.AudioSegment.from_file(tmp_path)
                # 强转配置
                audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
                audio.export(wav_path, format="wav")

                # 请求阿里接口
                recognized_text = await asr_ali_service.recognize_audio(wav_path)

                # 用完清理专属转码文件
                if os.path.exists(wav_path):
                    os.remove(wav_path)

            else:
                # 默认使用原有的上海话 ASR 接口
                recognized_text = await asr_shanghai_service.recognize_audio(tmp_path)

        finally:
            # 无论成功失败，确保原始临时上传文件被清理
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        # 结果判断与清洗返回
        if recognized_text and "识别请求发生错误" not in recognized_text:
            return standard_response(True, "语音识别成功", {"text": recognized_text})
        else:
            return standard_response(False, "无法识别出文字或服务出错", status_code=500)

    except Exception as e:
        log.error(f"处理语音文件出错: {e}")
        return standard_response(False, f"服务器内部错误: {str(e)}", status_code=500)


@app.get("/api/audio/proxy")
async def proxy_audio(url: str):
    """
    音频代理接口：解决 HTTPS 网站无法直接播放 HTTP 音频的混合内容 (Mixed Content) 拦截问题
    """
    # 安全校验：防止被恶意利用当作开放代理
    if not url.startswith(settings.TTS_API_BASE):
        raise HTTPException(status_code=403, detail="Forbidden URL")

    try:
        # 由后端代为向 HTTP 的 TTS 服务器请求音频文件数据
        # 加上 trust_env=False 绕过系统代理
        async with httpx.AsyncClient(trust_env=False, timeout=60.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()

            # 拿到二进制音频数据后，作为本机的 HTTPS 流量返回给前端
            return Response(content=resp.content, media_type="audio/wav")

    except Exception as e:
        log.error(f"代理音频失败: {e}")
        raise HTTPException(status_code=500, detail="Audio proxy failed")


# 挂载前端静态资源 (必须放在最后面，防止拦截 /api 路由)
# 如果根目录下有 www 文件夹，则开启
if os.path.exists("./www"):
    app.mount("/", StaticFiles(directory="./www", html=True), name="static")
    log.info("ChatServer: 已挂载 ./www 静态资源目录到根路径 /")
