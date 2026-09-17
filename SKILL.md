---
name: ai-video-editor
slug: ai-video-editor
version: 4.3.0
displayName: AI智能剪辑
summary: 将真人实拍素材按口播语义匹配镜头，生成带字幕和可选背景音乐的多版本竖屏带货视频。
tags:
  - video
  - editing
  - ugc
  - ecommerce
  - subtitles
  - ffmpeg
description: "自动把用户提供的真人实拍素材剪成多条竖屏带货视频。口播输入二选一：用户提供口播音频，按音频中的文案和实际时间轴剪辑；或用户提供口播文案与可选音色，生成口播后剪辑。支持语义段落级音画匹配、可选固定音量背景音乐、最高 1.3 倍速限制、shot_library 素材缓存、字幕、FFmpeg 并行渲染和质量门禁。适用于 UGC、产品演示、口播、TikTok、抖音、快手、千川实拍素材剪辑；不用于 AI 视频生成或对标视频复刻。"
---

# AI智能剪辑 V4.3（单次服务端策略版）

只剪辑用户提供的真人实拍素材。客户端使用 AI 完成有证据支撑的画面分析、口播转录或配音处理；**镜头选择/组合、连续性控制、多版本差异控制和方案优先级由服务端 `VideoEditingPolicyV1` 决定**。客户端只保留数据准备、结构校验、FFmpeg 渲染、质量门禁和交付。服务端工作流不调用任何大模型，因此不消耗模型 Token。不得把启发式规则描述成真实的视觉分析结果。

## 延迟 API Key 门禁

不要在 Skill 启动时检查 API Key，也不要在检查素材、读取缓存、分析视频、生成口播或其他本地准备阶段提醒用户授权。先完成所有不依赖灵智工坊的本地工作；只有执行流程第 6 步、即将运行 `remote_edit_strategy.py` 请求服务端剪辑策略时，才检测并校验 API Key。Key 缺失或无效只阻止该服务端阶段及后续步骤，不否定已经完成的本地准备结果。

1. 不要手工猜测 Key 位置或扫描用户目录；`remote_edit_strategy.py` 在提交任务前自动调用同一校验逻辑。需要单独排障时才运行 `scripts/validate_lingzhi_api_key.py`。校验逻辑按固定优先级发现 Key：显式传入值 → `LZSTUDIO_API_KEY` → `RECREATE_VIDEO_API_KEY` → `LINGZHI_API_KEY` → `LZSTUDIO_CONFIG` 指定的 JSON → `~/.recreate-video/config.json` → `~/.ugc-product-video/config.json` → `~/.product-image-ad/config.json`。JSON 配置只读取非空字符串 `apiKey`。
2. 只有已经到达服务端剪辑策略阶段、且上述来源都没有可用 Key 时，才停止并提醒用户：`请获取灵智工坊API Key：[https://www.lingzhiai.com.cn/](https://www.lingzhiai.com.cn/)`。不得提前发送这条提醒。
3. 需要手动运行校验脚本时，使用当前环境可用的 Python 3 解释器：macOS/Linux 优先 `python3`，再回退到 `python`；Windows 优先 `py -3`，再回退到 `python`。不得因为某一个 Python 命令别名不存在，就误判为 API Key 缺失。

macOS/Linux 示例：

```bash
if command -v python3 >/dev/null 2>&1; then
  python3 scripts/validate_lingzhi_api_key.py
else
  python scripts/validate_lingzhi_api_key.py
fi
```

- Key 来源仅限上述环境变量和配置白名单；不自动读取 `.env`、shell 历史或其他无关文件。不得打印、回显、记录或写回 Key。
- 校验脚本通过灵智工坊 CLI 的只读 `account --credits` 接口验证 Key，不提交工作流任务，也不消耗额度。
- 只有脚本输出“灵智工坊 API Key 校验通过。”且退出码为 0 时，才允许提交服务端剪辑策略任务。
- 如果 Key 无效或无权限，停止服务端阶段，不得绕过，并提醒用户：`请获取灵智工坊API Key：[https://www.lingzhiai.com.cn/](https://www.lingzhiai.com.cn/)`；已完成的本地准备结果保留，配置后从该阶段继续。
- 已知配置文件存在但 JSON 损坏或 `apiKey` 类型错误时，报告该配置文件问题，不误报为“没有 Key”，也不覆盖原文件。
- 如果是 Python、CLI 或网络等运行环境错误，立即停止并如实报告运行环境问题；不得把这类错误误报为“用户没有 API Key”。

## 服务端调用约定

- Skill **不得直接请求 n8n Webhook**。必须通过随 Skill 附带的灵智工坊 CLI，使用【提交任意任务】接口：`lzstudio task submit ... --workflow-id VideoEditingPolicyV1 --input ...`，再通过 `lzstudio task fetch ... --id ...` 轮询结果。
- n8n 侧工作流以 **Webhook** 节点触发，工作流名称/注册 ID 使用 `VideoEditingPolicyV1`；Webhook 路径为 `v1/video-editing-policy`。灵智工坊服务端负责把【任意任务】转发到该工作流。
- API Key 不写入 Skill 文件。仅在首次需要调用灵智工坊服务端时，使用上述受控来源发现 Key，并通过延迟门禁校验。
- macOS Apple Silicon 与 Windows x64 的 CLI 已放在 `tools/lzstudio/`。也可以通过 `LZSTUDIO_CLI` 或 `input/config.json -> lzstudio_cli_path` 指向外部 CLI。
- 客户端与服务端使用稳定协议 `schemaVersion: 1`。服务端后续升级策略时应保持该协议兼容，避免旧版 Skill 因策略升级而失效。

## 确认口播输入和版本数

口播输入必须二选一，不得同时使用，也不得在两者都缺失时自动编写口播：

- **口播音频模式**：用户提供口播音频，将 `narrationMode` 设为 `audio`，并把文件路径写入 `voiceover_path`。使用 Whisper 识别音频中的实际文案和词级时间戳；原音频是口播内容、语速、停顿和成片总时长的唯一权威。不重写、不重新配音，只可清理字幕中明显的识别标点或同音字错误，不得改变句意和句序。
- **口播文案模式**：用户提供 `input/voiceover_script.txt`，将 `narrationMode` 设为 `script`。音色可选：用户提供时写入 `tts_voice`；未提供时使用系统默认的自然 UGC 音色。文案是口播内容权威；默认不改写卖点或表达顺序，仅可为发音和自然停顿生成等义的 `spoken_text`。素材无法支撑文案时，必须先请用户修改文案或补充素材，不得静默删改。
- 用户只提供了文案但未说音色时，不必须追问；使用默认音色并在渲染前简短说明。用户同时提供音频和文案，或两者都未提供时，只询问用户选择其中一种输入方式，不开始口播阶段。
- 将 `voiceStyle` 保持为 `ugc_creator`。文案模式的 TTS 应使用自然日常语气、稳定语速和合理停顿；音频模式不改变用户原声。
- 将 `videoCount` 设为 1–10，默认 5。用户省略或设为 `auto` 时：素材少建议 3 条，素材正常建议 5 条，素材丰富建议 5–10 条。若素材无法支持足够多的有效方案，宁可少生成。
- 将 `max_speed_ratio` 保持在 1.30 以下；1.30 倍是不可突破的硬上限。

## 配置背景音乐

- 背景音乐可选。用户提供音乐文件或目录时，检查音频可读性并把选中的曲目按版本顺序写入 `bgm_tracks`；条目可为路径字符串，或包含 `path` 与独立 `volume` 的对象。多版本按顺序分配，曲目不足时循环使用。
- 将 `bgm_mix_mode` 固定为 `constant`。`bgm_volume` 或条目中的 `volume` 是整条成片使用的固定增益；不得根据人声、静音段或画面内容自动改变音乐音量，不得使用 sidechain、ducking、自动音量包络或默认淡入淡出。只有用户明确提出时，才可额外添加淡入淡出。
- 音乐不足成片时长时循环，超过时长时裁切。混音不得改变口播、字幕或画面的起点、速度和总时间轴。未提供背景音乐时保持 `bgm_tracks: []`，只输出口播音轨。

## 选择缓存模式

- 任一源视频缺少 `cache/videos/{video_hash}/shot_library.json` 时，使用素材建库模式：只分析未命中的源视频，并按 SHA-256、时长和文件大小缓存纯元数据素材库。
- 所有源视频均命中缓存时，使用广告生成模式：跳过抽帧和素材库视觉分析，重新执行口播、匹配、选中镜头引用生成、渲染和质检。

建库时不要预先生成全部镜头 MP4。V4 素材库条目只保存不可变源区间、关键帧、客观描述、稳定人物 ID、产品交互与状态、场景与景别、可用位置、连续性、标签和可用性。后续 AI 只能选择已有 `shot_id`。

## 执行流程

1. 运行 `scripts/check_cache.py`。该脚本负责规范化 ZIP 导入、计算视频哈希、写入 `work/cache_state.json`，并在全部命中时恢复 `work/shot_library.json`。
2. 缓存未命中时，运行 `prepare_materials.py`，读取 `references/analyze-and-build-library-prompt.md`，一次性分析抽帧清单，再把响应交给 `analyze_and_build_library.py`。为服装部位、可见动作和可见结果填写受控的 `visual_facts`。
3. 让 `merge_short_shots.py` 按既有规则生成纯元数据虚拟合并镜头，不改变 `shot_library` 的建库逻辑。
4. 读取 `references/narration-ugc-prompt.md`。`audio` 模式先转录用户音频，再按转录顺序分成视觉原子语义段，不改写原口播；`script` 模式按用户文案原顺序分段，仅生成等义发音文本。两种模式都返回字幕用 `text`、`spoken_text`、精确的 `visual_requirements` 和完整覆盖要求的证据镜头。素材证据不足时停止并询问，不得修改用户的口播来迁就素材。
5. 运行 `prepare_narration.py`。`audio` 模式必须使用用户原音频和 Whisper 词级时间戳生成字幕与语义时间轴，不调用 TTS；`script` 模式才使用用户选择的音色或默认音色生成 TTS。两种模式都校验画面覆盖关系，并生成与语音同步、处于安全区的字幕。
6. 到此时才运行 `remote_edit_strategy.py`。该脚本在提交服务端任务前自动检测并校验 Key；如果 Key 缺失或无效，此时再提醒用户前往灵智工坊网站获取，不要在第 1–5 步或开始对话时提前提醒。它只把口播语义段、对应证据镜头的紧凑元数据和少量配置提交到服务端，不上传原视频。脚本通过灵智工坊 CLI 执行【提交任意任务】并轮询结果，固定 `operation=plan_edit`。服务端一次完成镜头筛选、镜头组合、时长/倍速约束、连续性、多版本开场与差异控制，并按内部策略优先级返回 `variants`。**一次完整剪辑只调用这一次服务端工作流，固定消耗 2 积分。**
7. 运行 `apply_remote_strategy.py` 和 `validate_edit_plan.py`。前者只做非核心的结构/安全校验并落盘服务端方案；后者继续校验引用、字幕和本地渲染所需条件。任何超过配置速度范围或 1.30 倍速硬上限的方案都不得进入渲染。**不要在客户端增加服务端选择权重、策略优先级或匹配公式的副本。**
8. 依次运行 `extract_selected_shots.py`、`render_variants.py` 和 `quality_gate.py`。`extract_selected_shots.py` 只写入源视频、起止时间和镜头顺序等引用元数据，不得生成独立 shot 视频。`render_variants.py` 根据引用和 edit plan 一次完成截取、拼接、9:16 裁剪、分辨率与 FPS 统一、可选字幕遮挡修复、固定增益背景音乐混音及最终编码。并行渲染多个版本；每个版本只进行一次正式的 1080×1920、30 fps 编码。`quality_gate.py` 只负责成片技术质量门禁，通过后直接交付到 `output/real_shot_batch_<timestamp>/`，不再发起第二次服务端策略调用。

仅当流程已经到达第 6 步、且本机受支持来源中确实没有 Key 时，才提醒用户配置灵智工坊 API Key：

```bash
# macOS / Linux shell
export LZSTUDIO_API_KEY="你的 key"

# Windows PowerShell
$env:LZSTUDIO_API_KEY="你的 key"
```

配置后从第 6 步继续；`remote_edit_strategy.py` 会自动校验。只有排查凭据问题时，才单独运行（macOS/Linux 优先使用 `python3`）：

```bash
python3 scripts/validate_lingzhi_api_key.py
```

校验通过后可继续运行服务端策略阶段和后续流程。使用总流水线命令时，它也必须先完成本地前置阶段，到 `remote_edit_strategy` 阶段才触发 Key 校验：

```bash
python scripts/run_pipeline.py --library-response <combined.json> --narration-response work/narration_response.json
```

素材库全部命中缓存时省略 `--library-response`。服务端剪辑决策默认每次重新请求，以便旧版 Skill 自动获得兼容的策略升级；口播缓存仍可按原规则复用。

## 保持剪辑硬约束

- 素材库建成后，不得返回或接受新的源视频 `start`/`end` 区间。
- 选中镜头后不得改变素材库给出的源时间区间，必须保留完整动作。用户要求“去掉无效部分”时，只能改选素材库里已经排除无效内容的现有有效区间，不得改变分析路径或最终 FFmpeg 渲染路径。
- 不得选用未合并的 2 秒以下原始镜头；不得使用复制帧、静帧、黑帧、重复帧或 `tpad` 补时长；不得为了凑时长合并无关镜头。
- 同一版本不得重复使用 `shot_id`。多个版本必须使用不同策略、不同开场和有实质差异的镜头组合；素材不足时减少版本数。
- 素材支持时优先使用人物、产品、使用过程或结果开场。保持人物身份、产品身份、产品状态单向变化和动作连续性。未标记为开场的结果镜头不得直接放在第一镜。
- 以口播总时长为权威，误差不得超过 30 fps 的一帧。字幕默认使用可由 FFmpeg 稳定加载的 Hiragino Sans GB W6 粗体、高饱和黄色 `#FFD800` 和约 4 像素纯黑描边，字号约 68 像素，居中放在距底部约 220 像素的下方安全区，最多两行，不得出现纯标点字幕。不得为了字幕换行而拆分 TTS。
- 只按源素材身份使对应视频缓存失效。脚本、产品信息、口播或版本变化不得使 `shot_library` 失效。

继续兼容 V3 缓存。在内存中补齐缺失的 V4 字段，并兼容旧版 `shot_type: original|merged`。

## 保持方案与交付规则

`VideoEditingPolicyV1` 返回的是**剪辑方案及其内部优先级顺序**，不是最终成片视觉评分。客户端不得复制服务端的镜头选择权重、连续性规则、多版本差异规则或内部优先级公式，成片后不再进行第二次服务端策略调用。

最终成片只保留本地 `quality_gate.py` 的技术质量门禁；它用于判断文件是否满足交付条件，不把剪辑方案启发式指标包装成“成片评分”“过审率”或“真实视觉质量分”。

只交付满足以下条件的版本：镜头引用有效、源时间区间可读取、同版本镜头唯一、速度合法、字幕同步、包含音频、画面为 9:16、结尾无黑屏、冻结画面不超过 0.8 秒。不得生成 `selected_shots`、`repaired_shots` 或缓存 `extracted_shots` 中间视频。把 `work/timings.json` 中的阶段耗时视为基准记录，不得承诺固定完成时间。
