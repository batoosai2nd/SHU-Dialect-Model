# 上海文学馆小沪展陈页部署说明

## 本次上线范围

- 第一阶段只上线“小沪”，沪 Talk 完善后再作为第二阶段接入。
- 普通网页入口保持 `/` 不变。
- 文学馆触摸屏专用入口为 `/museum.html`。
- 专用页没有文字输入框、发送按钮和输入语言选择，只保留一个大号语音按钮：点击开始说话，再次点击停止并发送。

## 会话与数据处理

- 每位参观者点击“开始体验”后创建一个独立临时会话。
- 点击“结束本次体验”或连续 3 分钟无操作，会删除本次临时会话并回到待机页。
- 浏览器异常退出、设备断电或网络中断时，服务器会兜底清理超过 24 小时的文学馆临时会话。
- 文学馆页面不会读取或显示其他访客及普通网页的历史会话。

可在服务器 `.env` 中调整兜底清理参数：

```dotenv
MUSEUM_SESSION_RETENTION_HOURS=24
MUSEUM_CLEANUP_INTERVAL_SECONDS=3600
```

## 给服务器管理老师的部署信息

当前开发与测试分支：

```text
仓库：https://github.com/batoosai2nd/SHU-Dialect-Model
分支：agent/literature-museum-kiosk
```

域名与 443 审批完成后，建议最终访问地址：

```text
https://xiaohu.shu.edu.cn/museum.html
```

密钥和服务地址继续只配置在服务器 `.env` 中，不写入 GitHub，也不下发到文学馆展陈电脑。文学馆电脑只需要使用浏览器全屏打开上面的 HTTPS 页面，并允许麦克风权限。

## 新版 ASR/TTS 配置

当前分支已经按范老师提供的两份新版接口文档完成后端适配：

- ASR：`POST {SHANGHAI_ASR_URL}/recognize`，使用 Bearer Key 鉴权。
- TTS：`GET {TTS_API_BASE}/voice`，后端接收 WAV 后再通过本站 HTTPS 返回给浏览器。
- `localhost` 或 `127.0.0.1` 指生产服务器自身，不是开发者电脑或文学馆终端。
- 所有地址、模型名、说话人和密钥均从服务器 `.env` 读取，可参考仓库中的 `.env.example`。

服务器 `.env` 至少需要确认这些值：

```dotenv
SHANGHAI_ASR_URL=http://127.0.0.1:5000/api/asr
SHANGHAI_ASR_API_KEY=由范老师填写
SHANGHAI_ASR_MODEL_ID=test2
SHANGHAI_ASR_DIALECT=auto

TTS_API_BASE=http://127.0.0.1:54322
TTS_MODEL=从TTS的models/registry确认
TTS_SPEAKER=从TTS的models/registry确认
TTS_LANG=
```

如果两个语音服务不在小沪应用服务器本机，请把上述地址替换成生产内网中实际可访问的地址；不要把真实密钥提交到 GitHub。

## FFmpeg 依赖

浏览器录音通常是 WebM，而新版 ASR 文档支持 WAV、MP3、OGG、FLAC、AAC、M4A，不包含 WebM。本项目会在后端将录音统一转成 16kHz、单声道、16-bit WAV，因此生产服务器必须安装 FFmpeg，并保证运行小沪服务的账号能在 `PATH` 中执行 `ffmpeg`。

Ubuntu/Debian 可由服务器管理员执行：

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
ffmpeg -version
```

部署后建议依次检查：

1. 服务器内部访问 `{SHANGHAI_ASR_URL}/models` 正常。
2. 服务器内部访问 `{TTS_API_BASE}/models/registry` 正常，并核对 `TTS_MODEL`、`TTS_SPEAKER`。
3. 校内访问 `http://10.10.36.121/museum.html` 不再返回 404。
4. 校外通过 `https://xiaohu.shu.edu.cn/museum.html` 授权麦克风，完整测试“录音 → ASR → 大模型 → TTS 播放”。
