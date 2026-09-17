# LZStudio CLI 配置

只有运行远程剪辑策略阶段才需要 LZStudio CLI。完整 GitHub 仓库已包含 macOS Apple Silicon 与 Windows x64 版本；腾讯 SkillHub 的精简包因上传大小限制不携带二进制，可从 GitHub Release 下载对应资产。

## v4.3.0 资产

- macOS Apple Silicon：`lzstudio-darwin-arm64`
  - SHA-256：`7af107fa2087782763fcfb7528aa8759326c9ca4b8a04c447b42fc55528b0e7d`
- Windows x64：`lzstudio-windows-x64.exe`
  - SHA-256：`f1c61d3fd5ec0ee5b6a58957494ff21cf220098e4350a4c2f89081f60bf55ab0`

下载地址：<https://github.com/devmaster947-hub/ai-video-editor/releases/tag/v4.3.0>

下载后先核对 SHA-256。macOS 需要赋予可执行权限。将文件放入 PATH，或把绝对路径写入 `LZSTUDIO_CLI` 环境变量或 `input/config.json` 的 `lzstudio_cli_path`。不要把灵智工坊 API Key 写入配置文件或仓库。

