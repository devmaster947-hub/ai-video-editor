# AI Video Editor

面向真人实拍素材的竖屏 UGC 带货视频剪辑 Skill。支持用户提供口播音频，或提供口播文案并使用系统音色生成配音；随后按语义段匹配镜头、生成字幕、混合可选背景音乐，并输出经过技术质量门禁的多版本成片。

## 主要特性

- 口播音频与口播文案二选一
- 基于 `shot_library` 的素材缓存与证据镜头匹配
- 最高 1.3 倍速硬限制
- 9:16、1080×1920、30 fps 并行渲染
- 固定增益背景音乐，不自动 ducking
- 灵智工坊服务端只负责剪辑策略，不上传原视频
- API Key 延迟到首次请求服务端剪辑策略时才检查；素材检查、缓存、分析和口播准备阶段不会提前要求授权

## 使用

1. 把真人实拍视频放入 `input/videos/`。
2. 复制并修改 `input/config.json`；选择 `audio` 或 `script` 口播模式。
3. 音频模式提供 `voiceover_path`；文案模式创建 `input/voiceover_script.txt`。
4. 按 [SKILL.md](SKILL.md) 的流程运行。

本 Skill 不包含示例素材、缓存、工作文件或生成成片。运行需要 Python 3、FFmpeg/FFprobe，以及受支持平台上的 LZStudio CLI。灵智工坊 API Key 仅在服务端剪辑策略阶段使用，不应写入仓库。

