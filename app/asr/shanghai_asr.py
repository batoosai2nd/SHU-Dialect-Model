import mimetypes
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logger import log


class ShanghaiASR:
    """TeleSpeech 上海话 ASR HTTP 客户端。"""

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.url = (url if url is not None else settings.SHANGHAI_ASR_URL).rstrip("/")
        self.api_key = (
            api_key if api_key is not None else settings.SHANGHAI_ASR_API_KEY
        )
        self.timeout = settings.SHANGHAI_ASR_TIMEOUT_SECONDS
        self.transport = transport

        if self.url:
            log.info(f"ShanghaiASR: 已配置 ASR 服务地址: {self.url}")
        else:
            log.warning("ShanghaiASR: 尚未配置 SHANGHAI_ASR_URL")

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}

    async def check_connection(self) -> bool:
        """后台检查服务是否可达；/models 按接口文档无需鉴权。"""
        if not self.url:
            return False

        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                trust_env=False,
                transport=self.transport,
            ) as client:
                response = await client.get(f"{self.url}/models")
                response.raise_for_status()
            log.info("ShanghaiASR: HTTP API 连接正常")
            return True
        except Exception as exc:
            log.warning(f"ShanghaiASR: HTTP API 暂不可用: {exc}")
            return False

    async def recognize_audio(
        self,
        audio_path: str,
        model: Optional[str] = None,
        dialect: Optional[str] = None,
        use_kaldi: Optional[bool] = None,
        use_punctuation: Optional[bool] = None,
    ) -> str:
        """上传 WAV 等受支持格式，并返回识别文本。"""
        path = Path(audio_path)
        if not path.is_file():
            log.error(f"ShanghaiASR: 找不到音频文件: {audio_path}")
            return ""
        if not self.url:
            log.error("ShanghaiASR: 未配置 SHANGHAI_ASR_URL")
            return ""
        if not self.api_key:
            log.error("ShanghaiASR: 未配置 SHANGHAI_ASR_API_KEY")
            return ""

        model_id = model or settings.SHANGHAI_ASR_MODEL_ID
        dialect_name = dialect or settings.SHANGHAI_ASR_DIALECT
        kaldi_enabled = (
            settings.SHANGHAI_ASR_USE_KALDI if use_kaldi is None else use_kaldi
        )
        punctuation_enabled = (
            settings.SHANGHAI_ASR_ENABLE_PUNCTUATION
            if use_punctuation is None
            else use_punctuation
        )
        form_data = {
            "model_id": model_id,
            "dialect": dialect_name,
            "use_kaldi": str(kaldi_enabled).lower(),
            "enable_punctuation": str(punctuation_enabled).lower(),
        }
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        try:
            log.info(
                f"ShanghaiASR: 提交音频识别 (model={model_id}, dialect={dialect_name})"
            )
            with path.open("rb") as audio_file:
                files = {"audio": (path.name, audio_file, content_type)}
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    trust_env=False,
                    transport=self.transport,
                ) as client:
                    response = await client.post(
                        f"{self.url}/recognize",
                        headers=self._headers(),
                        data=form_data,
                        files=files,
                    )
                    response.raise_for_status()

            result = response.json()
            recognized_text = str(result.get("text", "")).strip()
            if recognized_text:
                log.info(f"ShanghaiASR: 识别成功 -> {recognized_text}")
            else:
                log.warning("ShanghaiASR: 接口成功响应中没有识别文本")
            return recognized_text
        except httpx.HTTPStatusError as exc:
            log.error(f"ShanghaiASR: 接口返回 HTTP {exc.response.status_code}")
        except (httpx.HTTPError, ValueError) as exc:
            log.error(f"ShanghaiASR: 识别请求失败: {exc}")

        return ""
