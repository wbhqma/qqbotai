# qqbotai

使用你自己的普通 QQ 账号运行的群聊 AI，基于 Python + NoneBot2，通过 NapCat / OneBot V11 接收和发送消息。无需注册官方机器人，也不需要 QQ 开放平台 AppID / AppSecret。只有允许的群中明确 @登录的 QQ 时回复，默认 AI 名字为“哦鲸鲸”，已有自定义人设已保留。

支持文本聊天、近期记忆、多模型协议、看图分析及以图搜图。模型和搜索服务需由运行者自行配置；未配置图片服务时会提示管理员，不会下载或上传图片。

## Windows 启动

本机项目目录为 `D:\Project\兴趣班\qqbotai`。Python 程序和 NapCat 是两个进程，需要保留两个终端窗口。

### 1. 启动 AI 程序并完成本机配置

在 PowerShell 运行：

```powershell
Set-Location 'D:\Project\兴趣班\qqbotai'
.\start.ps1
```

启动脚本会先检查配置；缺少 Token、允许的群号或字段格式无效时，自动打开本机配置向导。填写真实 QQ 群号，多个群用英文逗号分隔。`NAPCAT_SELF_ID` 可以填写准备用来运行 AI 的个人 QQ 号，也可以留空。OneBot Token 留空会自动生成；文本模型密钥可以稍后填写，先用 `/ping` 检查 QQ 收发。

配置值保存在本机 `.env`，敏感输入不回显；向导保留已有模型配置和机器人名字。以后修改配置可单独运行 `.\configure.ps1`。保存成功后，程序开始等待 NapCat 连接，保留此窗口。

Python 环境默认在 `D:\IDE\python-envs\qqbotai`；如环境尚未创建，启动脚本会调用 `.\setup.ps1` 安装依赖。也可提前运行该脚本。`QQBOT_VENV` 可指定其他环境目录，`QQBOT_PYTHON` 可指定基础 Python 解释器。

### 2. 启动 NapCat，并在本机登录自己的 QQ

本机已准备 NapCat v4.18.38 的官方 Windows.Node 便携包。另开一个 PowerShell 窗口：

```powershell
Set-Location 'D:\Project\兴趣班\qqbotai'
.\start-napcat.ps1
```

脚本会准备本机反向 WebSocket 地址、Token、数组消息格式及仅本机可访问的 WebUI，然后运行 NapCat。按终端提示在终端或本机 WebUI 扫码登录你自己的 QQ。登录操作只在本机完成，Python 项目不接收 QQ 密码。

| 目录 | 用途 |
| --- | --- |
| `D:\IDE\NapCat\runtime-v4.18.38` | NapCat 便携程序，应包含 `node.exe` 和 `index.js` |
| `D:\IDE\NapCat\qqbotai-data` | 本项目独立的 NapCat 配置、日志、缓存等运行数据 |
| `D:\IDE\python-envs\qqbotai` | Python 环境和依赖 |

反向 WebSocket 默认连接 `ws://127.0.0.1:8082/onebot/v11/`；端口和 Token 由辅助脚本与本机配置同步，无需再次手工填写。WebUI 默认端口为 `6099`，入口以本机终端提示为准。OneBot 监听与 WebUI 仅绑定本机地址，NapCat 与 Python 在同一台电脑运行。

修改 Token 或端口后，停止两个程序并重新启动；不要在 NapCat 已运行时同步配置。其他电脑需要自行从 [NapCat 官方发布页](https://github.com/NapNeko/NapCatQQ/releases) 准备对应便携包，本源码仓库不包含 NapCat 程序。安装和登录问题可参考 [NapCat 项目文档](https://napneko.github.io/)。

### 3. 确认连接并测试群消息

在项目目录另开终端查询本机连接状态：

```powershell
& 'D:\IDE\python-envs\qqbotai\Scripts\python.exe' bot.py --status
```

`QQ 连接已建立` 表示 NapCat 已连接到 AI 程序；`等待 NapCat 登录或连接` 表示 AI 程序已运行，但尚未接上 QQ。此查询不显示账号、群号或密钥。然后在允许的群里 **@刚刚登录的 QQ，发送 `/ping`**；收到“我在线”才算群收发联调完成，不会消耗模型额度。

`start.ps1 -Check` 仅检查配置读取及插件装配，不交互、不登录 QQ，也不调用模型或搜索服务；检查通过不代表 QQ 已连接。`python configure.py --check` 则检查启动所需的 Token、允许群号和字段格式，未就绪时返回退出码 `2`。

连接规范见 [NoneBot OneBot 配置](https://onebot.adapters.nonebot.dev/docs/guide/setup/) 与 [Token 配置](https://onebot.adapters.nonebot.dev/docs/guide/configuration/)。

## 群内使用

所有操作均需在允许的群里 **明确 @机器人**。私聊、普通群消息、@全体成员、只引用机器人或只输入昵称都不触发。

| 消息 | 功能 |
| --- | --- |
| @机器人 /ping | 检查 QQ 收发，不调用模型 |
| @机器人 你好 | 文本聊天 |
| @机器人 /清空 | 清空自己在当前群的近期文字记忆 |
| @机器人 /识图 图片里写了什么 + 一张图片 | 看图回答、提取文字 |
| @机器人 + 一张图片 | 默认客观描述图片 |
| @机器人 /搜图 + 一张图片 | 返回最多 3 条来源/相似网页链接 |
| @机器人 /帮助 | 查看命令和上传说明 |

图片与命令应在同一条消息发送，当前一次处理一张图；不读取被引用消息中的图片。支持 JPEG、PNG、WebP、GIF 首帧，输入最多 5 MB、2000 万像素。图片解码后去掉 EXIF 并压缩，不在本机保存图片，也不把图片、图片 URL 或分析结果加入后续聊天记忆。模型输出以文字消息发送，不把模型返回的 CQ 码当作控制指令。

## 配置

可以运行向导，或参考 `.env.example` 编辑本机 `.env`。公开示例里的 QQ 号、群号、Token 和 API Key 必须为空；系统环境变量优先于 `.env`。

| 字段 | 用途 |
| --- | --- |
| `BOT_NAME` | AI 自称，默认“哦鲸鲸”；性格在 `app/persona.py` |
| `ONEBOT_ACCESS_TOKEN` | 至少 16 位，与 NapCat 配置一致，向导可自动生成 |
| `NAPCAT_PORT` | 本机监听端口，默认 8082 |
| `NAPCAT_ALLOWED_GROUPS` | 必填，真实 QQ 群号，用英文逗号分隔；空列表不回复任何群 |
| `NAPCAT_SELF_ID` | 可选，只处理这个登录 QQ 的事件 |
| `LLM_PROVIDER` | `deepseek` / `compatible` / `openai` / `anthropic` / `gemini` / `ollama` |
| `LLM_BASE_URL` | 模型 API 根地址；compatible 必填，其他协议提供默认地址 |
| `LLM_MODEL` | 账号实际可调用的模型 ID；DeepSeek 留空用项目默认值 |
| `LLM_API_KEY` | 文本模型密钥；本机 Ollama 可以为空 |
| `LLM_MAX_TOKENS` | 输出预算，默认 2048 |
| `LLM_EXTRA_BODY` | 模型专用参数 JSON，不得覆盖核心消息和输出上限 |
| `LLM_TOKEN_PARAM` | compatible 接口可选择 max_tokens 或 max_completion_tokens |
| `HISTORY_TURNS` | 近期完整文字对话轮数，默认 6，上限 10 |
| `COOLDOWN_SECONDS` | 每个会话调用间隔，默认 3 秒 |
| `VISION_PROVIDER` | 视觉模型协议：compatible / openai / anthropic / gemini / ollama |
| `VISION_BASE_URL` | 视觉接口地址；compatible 必填，其他协议提供默认地址 |
| `VISION_MODEL` | 必须是支持图片输入的视觉模型，不能仅用文本模型名称代替 |
| `VISION_API_KEY` | 视觉接口独立密钥，不自动沿用文本服务的密钥 |
| `SERPAPI_API_KEY` | SerpApi 搜图服务独立密钥 |

### 文本与视觉模型

文本聊天保留 DeepSeek、兼容 Chat Completions、OpenAI Responses、Claude Messages、Gemini GenerateContent 以及本机 Ollama 接入。视觉功能另外配置 `VISION_*`，两个模块可以使用不同服务商。更换模型后重启生效。

compatible 的地址通常填到 `/v1` 层，程序追加 `/chat/completions`；OpenAI 使用 `/responses`；Claude 使用 `/messages`；Gemini 使用 GenerateContent。视觉接口可发送图片的 Base64 数据，不把原始 QQ 签名图片地址发给模型。模型 ID、可用区域、费用和输入规则以服务商当前文档及自己的账号权限为准。

API 依据：[OpenAI 官方图片文档](https://developers.openai.com/api/docs/guides/images-vision)、[Claude Vision](https://platform.claude.com/docs/en/build-with-claude/vision)、[Gemini 图片理解](https://ai.google.dev/gemini-api/docs/image-understanding)、[千问视觉](https://help.aliyun.com/zh/model-studio/vision)。

### 以图搜图

`/搜图` 使用 [SerpApi Google Lens](https://serpapi.com/google-lens-api)，需要单独申请并填写该服务的 API Key，可能计费。程序将图片压缩为小于 500 KB 的 JPEG，通过 [Image API](https://serpapi.com/image-api) 上传，再用 image_id 搜索。不会向搜索服务发送原始 QQ 图片 URL、群号或用户 QQ 号。

搜索启用 `safe=active`，只返回普通来源/相似网页链接，不自动转发搜索结果图片。相似结果可能不是原始出处，不能据此确认作者或人物身份。图片 ID 的有效期及服务端数据处理方式以 SerpApi 文档为准；本程序不能保证第三方服务删除其副本。

## 隐私与运行行为

云端识图会把压缩图片及问题发送到所配置视觉服务；搜图会上传压缩图片到 SerpApi。请让群成员了解用途。聊天问题和保留的近期文字内容会发送到所配置文本模型。OpenAI 请求设置 `store=false`，实际保留规则仍由平台决定。

本项目 Python 日志仅保留固定诊断摘要，不输出原始消息、QQ 号、群号、图片 URL、密钥、API 响应或异常堆栈。NapCat 自身的终端与 WebUI 可能显示登录二维码、账号或管理入口信息。`D:\IDE\NapCat\qqbotai-data` 用于 NapCat 配置、日志、缓存等运行数据；QQ 组件仍可能把原生登录数据写入其自动选择的其他本机目录。上述登录信息、配置、日志、缓存和备份等相关文件均只保留在本机，不上传到仓库或问题反馈。

近期文字记忆在进程内按“机器人 + 群 + 用户”隔离，重启清空，有一小时清理、256 个会话和每会话 12000 字符上限。图片请求与文字共享去重、冷却、会话锁和最多 3 个并发请求限制。

`.env`、日志、缓存、聊天数据和密钥已被 Git 忽略。发布前运行隐私检查；它是规则扫描，不能保证识别所有私密信息。若真实凭证曾进入提交历史或被公开，应到对应服务重置，仅修改当前文件无法撤回旧副本。

## 离线检查

```powershell
$python = 'D:\IDE\python-envs\qqbotai\Scripts\python.exe'
& $python -m pip check
& $python -m unittest discover -s tests -v
& $python scripts/check_privacy.py
.\start.ps1 -Check
```

测试使用模拟 QQ、模型和搜索响应，不使用真实密钥、不发送群消息，也不消费 API 额度。GitHub Actions 覆盖 Windows / Ubuntu 与 Python 3.11 / 3.14；实际状态以本次提交运行结果为准。

Linux / macOS 可自行创建虚拟环境并安装 `requirements.lock`，然后运行 `python configure.py`、`python bot.py --check`、`python bot.py`。不需要使用 Windows 的 D 盘路径。

## 代码入口

- `bot.py`：OneBot 反向 WebSocket、插件与模型装配。
- `start.ps1`：启动前检查配置，必要时进入向导，再启动 AI；`-Check` 只做离线装配检查。
- `start-napcat.ps1`：启动本机 NapCat 便携程序，使用独立运行目录登录个人 QQ。
- `prepare_napcat.py` / `app/napcat.py`：同步本机 OneBot 连接配置、Token、消息格式及 WebUI 访问设置。
- `plugins/qq_chat.py`：群白名单、明确 @ 判断、命令与图片事件路由。
- `app/chat.py`：去重、并发、冷却与近期文字记忆。
- `app/images.py`：图片下载验证、去元数据、视觉协议和搜图。
- `app/llm.py`：文本模型协议。
- `app/config.py` / `configure.py`：配置读取、本机向导与非交互启动配置检查。
- `app/persona.py`：自定义人设。
- `scripts/check_privacy.py`：公开文件隐私扫描。

## 许可证

本项目自有代码采用 [MIT](LICENSE)。NapCat 是需独立安装的外部软件，本仓库不包含它的程序或源代码；其使用、修改和再分发受 [NapCat 自身许可](https://github.com/NapNeko/NapCatQQ/blob/main/LICENSE) 约束，并非本项目的 MIT 授权范围。模型服务及 QQ 平台也分别适用各自的条件。
