from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.asr.shanghai_asr import ShanghaiASR
from app.tts.xiaohu_tts import XiaoHuTTS


@pytest.mark.asyncio
async def test_shanghai_asr_uses_new_authenticated_http_api(tmp_path):
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/asr/recognize"
        assert request.headers["authorization"] == "Bearer secret-key"
        body = await request.aread()
        assert b'name="audio"' in body
        assert b'name="model_id"' in body and b"test2" in body
        assert b'name="dialect"' in body and b"auto" in body
        assert b'name="use_kaldi"' in body and b"true" in body
        assert b'name="enable_punctuation"' in body and b"true" in body
        return httpx.Response(
            200,
            json={"text": "侬好", "dialect": "shanghai", "duration": 0.2},
        )

    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF-test-wave")
    service = ShanghaiASR(
        url="http://asr.test/api/asr/",
        api_key="secret-key",
        transport=httpx.MockTransport(handler),
    )

    assert await service.recognize_audio(str(audio_path)) == "侬好"


@pytest.mark.asyncio
async def test_shanghai_asr_returns_empty_on_auth_error(tmp_path):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF-test-wave")
    service = ShanghaiASR(
        url="http://asr.test/api/asr",
        api_key="bad-key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, json={"error": "invalid key"})
        ),
    )

    assert await service.recognize_audio(str(audio_path)) == ""


@pytest.mark.asyncio
async def test_tts_uses_voice_endpoint_and_accepts_audio_response():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/voice"
        query = parse_qs(request.url.query.decode())
        assert query["text"] == ["侬好"]
        assert query["model_id"] == ["museum-model"]
        assert query["speaker_name"] == ["xiaohu"]
        assert query["auto_split"] == ["true"]
        return httpx.Response(
            200,
            content=b"RIFF-generated-wave",
            headers={"Content-Type": "audio/wav"},
        )

    service = XiaoHuTTS(
        api_base="http://tts.test/",
        model="museum-model",
        speaker="xiaohu",
        transport=httpx.MockTransport(handler),
    )

    assert await service.synthesize_audio("侬好") == b"RIFF-generated-wave"


@pytest.mark.asyncio
async def test_tts_rejects_http_200_json_business_error():
    service = XiaoHuTTS(
        api_base="http://tts.test",
        model="missing-model",
        speaker="xiaohu",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"status": 10, "detail": "model not found"},
            )
        ),
    )

    assert await service.synthesize_audio("测试") is None


def test_tts_browser_url_is_same_origin_and_encoded():
    audio_url = XiaoHuTTS.build_audio_url("侬好 & hello")

    assert audio_url is not None
    parsed = urlparse(audio_url)
    assert parsed.path == "/api/audio/tts"
    assert parse_qs(parsed.query)["text"] == ["侬好 & hello"]
