# P2M Studio — 照片转电影 AI Pipeline

将一组照片自动生成带旁白、音乐和转场的短片。支持 Ken Burns 动画模式和 AI 视频生成模式。

## 功能

- **Gemini Vision 分析**：自动识别照片内容，生成故事线和旁白
- **AI 视频生成**：通过 fal.ai (MiniMax Hailuo-02) 将静态照片转为 6 秒动态视频
- **Ken Burns 模式**：经典 Pan/Zoom 动画效果
- **节拍同步**：librosa 检测音乐节拍，视频转场对齐节拍点
- **FFmpeg 合成**：速度调整 + xfade 转场 + 音乐混合

## 使用

```bash
# AI Video 模式（默认）
python -m p2m_studio.cli generate --input <photo_dir> --music <music_file>

# Ken Burns 模式
python -m p2m_studio.cli generate --input <photo_dir> --music <music_file> --mode ken-burns

# Moltbot 集成模式
python -m p2m_studio.cli generate --input <photo_dir> --output <out_dir> --moltbot
```

## 依赖

- Python 3.9+
- FFmpeg
- librosa（节拍检测）
- google-generativeai（Gemini Vision）
- fal.ai API（AI 视频生成，需配置 `FAL_KEY`）

## 环境变量

- `GEMINI_API_KEY` — Gemini API 密钥
- `FAL_KEY` — fal.ai API 密钥（AI Video 模式）

## License

MIT
