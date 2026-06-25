# vid-transcode 🎬

**拼多多视频转码专用工具** — 将行车记录仪/摄像头拍摄的视频转码为拼多多工作台兼容的 H.264 MP4 格式。

## 背景

发货摄像头/行车记录仪拍摄的视频无法直接上传到拼多多工作台，因为：

- 分辨率通常超过 1080p（2K/4K）
- H.264 Level 过高（Level 5.0+）
- 非正方形像素（SAR ≠ 1:1）
- 含 GPS/品牌等非标准元数据
- 视频编码含 SEI NAL 单元（x264 标识）
- **可能无音频轨** → 拼多多转码服务器崩溃
- 可变帧率（VFR）导致时间戳异常

剪映重新导出 H.264 后可以上传，本工具实现了相同原理的自动化转码。

## 核心转码参数

```bash
ffmpeg -y -i input.mp4 \
  -f lavfi -i anullsrc=r=44100:cl=stereo \
  -map 0:v:0 \
  -c:v libx264 \
  -profile:v main \
  -level:v 4.0 \
  -preset fast \
  -crf 23 \
  -threads 2 \
  -vf "fps=30,scale=min(1920\,iw):min(1080\,ih):force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1" \
  -pix_fmt yuv420p \
  -movflags +faststart \
  -bsf:v filter_units=remove_types=6 \
  -map_metadata -1 \
  -map_chapters -1 \
  -map 1:a:0 \
  -c:a aac \
  -b:a 64k \
  -ar 44100 \
  -ac 2 \
  -shortest \
  output.mp4
```

### 参数说明

| 参数 | 作用 |
|------|------|
| `-profile:v main` | 最广泛兼容的 H.264 Profile |
| `-level:v 4.0` | 限制 Level 4.0（支持 1080p@30fps） |
| `fps=30` | 标准化帧率，拒绝可变帧率 |
| `scale=min(1920,iw):min(1080,ih)` | 限制最大分辨率 1080p |
| `setsar=1` | 强制正方形像素（**关键修复**） |
| `trunc(iw/2)*2` | 确保宽高为偶数（yuv420p 要求） |
| `filter_units=remove_types=6` | 清除 SEI NAL 单元（含 x264 标识） |
| `map_metadata -1` | 清除 GPS/品牌元数据 |
| `anullsrc` + `-map 1:a:0` | **强制添加 64kbps 静音 AAC 音轨** |
| `-shortest` | 以视频长度为基准截断 |

> **注意**：`min()` 中的逗号在 FFmpeg v5.x 中需转义为 `\,`，否则过滤器解析器会将逗号识别为 filter chain 分隔符。

## Web 部署

本项目部署在 Render（免费套餐，512MB 内存），使用 FastAPI + React 前端：

- **地址**：https://vid-transcode.onrender.com/
- **流程**：上传视频 → 自动转码 → 下载输出
- **限制**：单次转码（并发 1），文件最大 500MB

### Render 构建命令

```bash
pip install -r requirements.txt && cd frontend && npm install && npm run build
```

### 启动命令

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

FFmpeg 通过 `apt.txt` 自动安装。

## 本地开发

```bash
pip install -r requirements.txt
cd frontend && npm install && npm run dev
python app.py
```

## 版本历史

| 版本 | 变更 |
|------|------|
| v0.2.2 | 强制添加静音 AAC 音轨（拼多多需要音频流） |
| v0.2.1 | Main Profile + Level 4.0 + 限 1080p + 清除 SEI |
| v0.2.0 | 首次拼多多兼容修复（setsar=1 + fps=30 + 清元数据） |
| v0.1.x | 千牛平台兼容尝试（已废弃） |

## License

MIT
