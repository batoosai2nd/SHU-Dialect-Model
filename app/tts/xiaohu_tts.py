from typing import Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logger import log


class XiaoHuTTS:
    """Bert-VITS2 FastAPI v2 客户端，仅由本项目后端调用。"""

    def __init__(
        self,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        speaker: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.api_base = (
            api_base if api_base is not None else settings.TTS_API_BASE
        ).rstrip("/")
        self.model = model if model is not None else settings.TTS_MODEL
        self.speaker = speaker if speaker is not None else settings.TTS_SPEAKER
        self.transport = transport

    @staticmethod
    def build_audio_url(text: str) -> Optional[str]:
        """返回浏览器可访问的同源地址，不暴露内部 TTS 地址。"""
        if not text:
            return None
        return f"/api/audio/tts?{urlencode({'text': text})}"

    async def synthesize_audio(self, text: str) -> Optional[bytes]:
        """调用内部 /voice 接口，成功时返回 WAV 二进制。"""
        if not text:
            return None
        if not self.api_base or not self.model or not self.speaker:
            log.error("XiaoHuTTS: TTS_API_BASE、TTS_MODEL 或 TTS_SPEAKER 未配置")
            return None

        params: dict[str, object] = {
            "text": text,
            "model_id": self.model,
            "speaker_name": self.speaker,
            "sdp_ratio": settings.TTS_SDP_RATIO,
            "noise": settings.TTS_NOISE,
            "noisew": settings.TTS_NOISE_W,
            "length": settings.TTS_LENGTH_SCALE,
            "auto_split": str(settings.TTS_AUTO_SPLIT).lower(),
            "emotion": settings.TTS_EMOTION,
        }
        if settings.TTS_LANG:
            params["language"] = settings.TTS_LANG

        try:
            log.info("XiaoHuTTS: 正在向内部 /voice 接口请求合成语音")
            async with httpx.AsyncClient(
                timeout=settings.TTS_TIMEOUT_SECONDS,
                trust_env=False,
                transport=self.transport,
            ) as client:
                response = await client.get(
                    f"{self.api_base}/voice",
                    params=params,
                    headers={"Accept": "audio/wav"},
                )
                response.raise_for_status()

            content_type = response.headers.get("content-type", "").lower()
            if content_type.startswith("audio/"):
                log.info("XiaoHuTTS: 语音合成成功")
                return response.content

            # 该 TTS 接口的业务错误也可能返回 HTTP 200 + JSON。
            try:
                error_body = response.json()
                detail = error_body.get("detail") or error_body.get("message")
            except ValueError:
                detail = "响应不是音频"
            log.error(f"XiaoHuTTS: 语音合成失败: {detail}")
        except httpx.HTTPStatusError as exc:
            log.error(f"XiaoHuTTS: 接口返回 HTTP {exc.response.status_code}")
        except httpx.HTTPError as exc:
            log.error(f"XiaoHuTTS: 请求失败: {exc}")

        return None
