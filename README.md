# qqbotai

用自己的 QQ 账号运行群聊 AI，基于 Python、NoneBot2 和 NapCat / OneBot V11。仅在允许的群中被明确 @ 时回复，支持多模型聊天、看图、联网搜索和图片溯源。默认名字为“哦鲸鲸”，可自定义名字与人设。

QQ 收发和 AI 服务分别运行；无需 QQ 开放平台的 AppID / AppSecret。模型、视觉和搜索功能按需配置，各服务的 API Key 与额度独立。

## 群内使用

在群成员列表中选择并 **@运行机器人的 QQ**。下表中的命令都要带上这个 @。

| 发送内容 | 功能 |
| --- | --- |
| 只 @机器人，不附文字或附件 | 展示全部功能菜单及配置状态 |
| @机器人 /帮助 | 展示同一份菜单，支持 `/help`、`帮助` |
| @机器人 你好 | 与当前文本模型聊天，保留近期文字对话 |
| @机器人 /清空 | 清空自己在当前群的近期记忆，支持 `/reset`、`清空记忆` |
| @机器人 /ping | 检查 QQ 收发，不调用模型，支持 `ping` |
| @机器人 /搜索 Python 官方文档 | Tavily 检索网页，模型总结并附来源；别名 `/联网`、`/search` |
| @机器人 /识图 图片里写了什么 + 一张图 | 看图回答或提取文字，问题可省略 |
| @机器人 + 一张图 | 默认描述图片 |
| @机器人 /查出处 + 一张图 | 查插画候选作品页、页面署名与相似度，支持 `/出处` |
| @机器人 /找图 海边 | 从 Pexels 摄影图库找一张图，附摄影师和来源 |
| @机器人 /搜图 + 一张图 | 与 `/查出处` 相同 |
| @机器人 /搜图 海边（不附图） | 与 `/找图 海边` 相同 |

菜单始终列出全部功能，未完成相应服务配置的功能标为“未配置”。“已配置”只说明配置已填写，不代表鉴权成功、余额充足或服务在线；查看菜单不调用外部服务，也不加入聊天记忆。

图片和命令须在**同一条消息**发送，一次一张；不读取引用消息中的图片。支持 JPEG、PNG、WebP、GIF 首帧，最大 5 MB、2000 万像素。图片会去除 EXIF 并压缩后处理。

普通群消息、私聊、@全体成员、只引用机器人、手打昵称及机器人自己发送的消息均不触发。只有允许群中的明确 @ 才会处理。

## 快速开始：Windows

准备 Python 3.11+、PowerShell 和用于登录的 QQ 账号。克隆或下载本仓库，进入项目根目录后操作；源码可放在任意有读写权限的目录。

### 1. 准备 NapCat

从 [NapCat 官方发布页](https://github.com/NapNeko/NapCatQQ/releases) 下载 Windows.Node 便携包并解压。仓库中的启动脚本使用以下默认目录：

| 位置 | 用途 |
| --- | --- |
| `D:\IDE\NapCat\runtime-v4.18.38` | NapCat 运行程序，根目录应有 `node.exe` 和 `index.js` |
| `D:\IDE\NapCat\qqbotai-data` | 本项目的 NapCat 配置、登录相关数据、缓存与日志 |
| `D:\IDE\python-envs\qqbotai` | Python 虚拟环境和依赖 |

这是启动脚本约定的目录布局，仓库不附带 NapCat。使用其他 NapCat 目录或版本时，调整 `start-napcat.ps1` 中的运行目录；安装问题见 [NapCat 文档](https://napneko.github.io/)。

Python 环境可通过 `QQBOT_VENV` 改到其他位置；安装脚本也支持用 `QQBOT_PYTHON` 指定基础解释器。例如：

```powershell
$env:QQBOT_VENV = 'D:\IDE\python-envs\qqbotai'
# 需要指定解释器时：$env:QQBOT_PYTHON = 'D:\IDE\Python\python.exe'
```

这些环境变量应在运行项目脚本的每个终端中保持一致。

### 2. 启动 AI 并填写配置

在项目根目录运行：

```powershell
.\start.ps1
```

首次运行会安装 Python 依赖；缺少启动配置时进入本机配置向导。也可先运行 `setup.ps1` 安装，再运行 `configure.ps1` 配置。

向导中填写允许回复的**真实群号**，多个用英文逗号分隔；机器人 QQ 号可选。OneBot Token 首次留空会自动生成。文本模型可以暂不填 Key，先用 `/ping` 验证 QQ 收发；视觉、找图和搜索均可稍后添加。

配置保存在项目根目录的 `.env`。QQ 号、群号、Token 和 Key 输入时**不显示字符或星号**，粘贴后按回车即可；已有值通常可直接回车保留。保存后保留 AI 服务窗口，等待 NapCat 连接。

### 3. 启动 NapCat 并登录

另开一个终端，在项目根目录运行：

```powershell
.\start-napcat.ps1
```

按本机终端或 WebUI 提示登录 QQ。脚本会同步 OneBot 连接地址与 Token，并更新已有账号的连接配置：

- 默认反向 WebSocket：`ws://127.0.0.1:8082/onebot/v11/`，使用数组消息格式。
- WebUI 默认端口：`6099`，入口以本机终端提示为准；WebUI Token 与 OneBot Token 分开。
- Python 监听地址和 WebUI 均绑定 `127.0.0.1`，两个服务在同一台电脑运行。

保留两个服务窗口。日常启动仍依次运行 `start.ps1` 和 `start-napcat.ps1`；停止时在对应窗口按 `Ctrl+C`。不要重复运行同一 NapCat 运行目录。

### 4. 验证群收发

用另一个 QQ 在允许的群中，从成员列表选中并 @机器人，发送 `/ping`；收到“我在线”后，再单独 @它查看菜单。

本机可查询状态：

```powershell
$python = Join-Path $(if ($env:QQBOT_VENV) { $env:QQBOT_VENV } else { 'D:\IDE\python-envs\qqbotai' }) 'Scripts\python.exe'
& $python bot.py --status
& $python bot.py --diagnose
```

`--status` 区分 AI 未运行、等待 QQ 连接和已连接；`--diagnose` 额外显示匿名事件计数，不显示消息、账号或群号。连接成功仍需群内 `/ping` 才能确认实际收发。

## 配置模型与可选功能

运行 `configure.ps1` 可重新填写连接、名字、文本模型、视觉模型及 SerpApi。也可参考 [`.env.example`](.env.example) 编辑本机 `.env`；系统环境变量优先于文件。

修改模型或服务凭证后重启 AI。修改 OneBot Token 或端口时，先停止两个服务，再启动 AI 和 NapCat，使两端配置一致。仅改允许群号可运行 `configure.ps1 -Groups`，保存后重启 AI。

### 文本模型

`LLM_PROVIDER` 选择协议，`LLM_BASE_URL` 填 API 根地址，`LLM_MODEL` 填账号实际可调用的模型 ID，`LLM_API_KEY` 填该服务的 Key。

| `LLM_PROVIDER` | 协议与地址规则 |
| --- | --- |
| `deepseek` | DeepSeek Chat Completions，项目提供默认地址与模型 |
| `compatible` | 兼容 Chat Completions 的服务，如千问兼容接口；自行填写地址与模型，程序追加 `/chat/completions` |
| `openai` | OpenAI Responses，程序追加 `/responses` |
| `anthropic` | Claude Messages，使用 `/v1/messages` |
| `gemini` | Gemini GenerateContent |
| `ollama` | 本机 Ollama 的 Chat Completions，默认 `http://localhost:11434/v1`，Key 可留空 |

兼容接口的根地址通常包含服务商要求的 `/v1`；以该服务文档为准。拥有 API Key 的平台还须提供上述协议之一，模型 ID、可用功能、费用和账号权限由服务商决定。

名字使用 `BOT_NAME`，人设在 `app/persona.py`。其他常用字段：

| 字段 | 含义 |
| --- | --- |
| `LLM_MAX_TOKENS` | 单次输出预算，默认 2048 |
| `LLM_TOKEN_PARAM` | compatible 接口使用 `max_tokens` 或 `max_completion_tokens` |
| `LLM_EXTRA_BODY` | 模型额外参数 JSON；不能覆盖消息、模型和输出上限等核心字段 |
| `HISTORY_TURNS` | 近期完整文字对话轮数，默认 6，可设 0—10 |
| `COOLDOWN_SECONDS` | 同一会话的调用间隔，默认 3 秒 |
| `ONEBOT_ACCESS_TOKEN` | 与 NapCat 一致的 Token，至少 16 位 |
| `NAPCAT_ALLOWED_GROUPS` | 允许回复的数字群号，以英文逗号分隔；为空不回复任何群 |
| `NAPCAT_SELF_ID` | 可选，仅处理指定登录 QQ 的事件 |
| `NAPCAT_PORT` | 本机 AI 端口，默认 8082 |

### 视觉与搜索

各服务独立配置，未配置时提示管理员，不调用对应服务。单项向导只改对应 Key；回车保留已有值，输入 `-` 清空禁用。密钥不要发到群或提交仓库。

| 功能 | 配置方式 | 说明 |
| --- | --- | --- |
| 看图分析 | `configure.ps1` 中选择配置视觉模型，填写视觉协议、地址、模型和密钥等 `VISION_*` 字段 | 支持 compatible、openai、anthropic、gemini、ollama；所选模型须支持图片输入，不自动沿用文本模型 Key |
| 网页检索 | `configure.ps1 -Tavily`，填写 `TAVILY_API_KEY` | 在 [Tavily 控制台](https://app.tavily.com/) 获取凭证 |
| 插画溯源 | `configure.ps1 -SauceNao`，填写 `SAUCENAO_API_KEY` | 在 [SauceNAO Search API 页面](https://saucenao.com/user.php?page=search-api) 获取凭证 |
| 摄影关键词找图 | `configure.ps1 -Pexels`，填写 `PEXELS_API_KEY` | 在 [Pexels API 页面](https://www.pexels.com/api/new/) 申请凭证 |
| 通用以图搜图 | `configure.ps1` 中配置 `SERPAPI_API_KEY` | 使用 [SerpApi Google Lens](https://serpapi.com/google-lens-api) 与 Image API |

`/搜索` 只在明确命令下检索网页摘要，再交当前文本模型总结并附来源；总结失败仍展示摘要和链接。它使用搜索额度和模型 Token，不会自动打开结果网页，也不替代图片溯源。

`/查出处` 优先使用 SauceNAO，返回最多 3 个相似度不低于 70% 的可展示候选；没有 SauceNAO Key 时才使用 SerpApi 返回来源或相似网页。两者都配置时不会自动上传到第二家服务重试。未收录、裁剪或改动较大的图片可能找不到；相似度和页面署名不代表原作或作者认证。结果只发文字和链接，不下载、转发候选缩略图。

`/找图` 使用 Pexels 摄影图库，每次最多一张图并保留摄影师与来源链接；图片下载失败时提供来源信息。它按关键词检索，不上传群图片，不调用语言模型。

## 隐私与数据流

| 功能 | 发送给外部服务的数据 |
| --- | --- |
| 文字聊天 | 人设、本次问题和该用户在当前群的近期文字对话 → 所配置文本模型 |
| 看图分析 | 本次问题和去元数据、压缩后的图片 → 所配置视觉服务 |
| 网页检索 | 本次搜索问题 → Tavily；问题及有限的检索摘要 → 当前文本模型 |
| 以图查出处 | 压缩图片 → SauceNAO，或未配 SauceNAO 时的 SerpApi |
| 摄影找图 | 本次关键词 → Pexels，并从 Pexels 图片域名下载结果 |

外部请求不附带 QQ 号、群号或原始 QQ 签名图片地址。用户自己写进问题或图片里的个人信息仍属于上传内容，请让群成员知晓用途。云服务如何保留数据由各平台决定；OpenAI Responses 请求设置 `store=false`，本项目不能保证第三方删除副本。

近期文字记忆仅在内存中按“机器人、群、用户”隔离，重启清空；会话空闲超过一小时后清理，最多 256 个会话、每会话 12000 字符。图片、联网检索与找图结果不写入后续聊天记忆或磁盘。Pexels 的少量图片元数据可在内存缓存最多 24 小时。

Python 日志仅输出固定诊断摘要，不打印原始事件、凭证、API 响应或异常堆栈。NapCat 自身的终端、WebUI、配置、日志、缓存及 QQ 登录数据可能含隐私，均应保留在本机；QQ 组件也可能使用其默认本机数据目录。不要分享登录二维码或管理入口 Token。

`.env`、运行数据、日志、缓存、虚拟环境和编辑器配置由 Git 忽略。发布前还须检查暂存区；规则扫描不能识别所有个人信息。若凭证曾被提交或公开，应到对应服务重置，删除当前文件不能撤回历史副本。

## 常见问题

| 现象 | 检查顺序 |
| --- | --- |
| NapCat 提示 `ECONNREFUSED 127.0.0.1:8082` | 先启动 AI，确认窗口未退出；再核对端口。修改端口后重启两端 |
| 显示已连接，但群里不回复 | 用另一个 QQ；核对真实群号；从成员列表明确 @；发送 `/ping`，再看 `--diagnose` |
| 菜单提示未配置 | 在本机配置对应独立凭证，保存后重启 AI |
| 菜单已配置，但功能鉴权失败 | 检查该服务 Key、接口协议、模型权限、额度及网络；菜单不做实时接口验证 |
| 识图失败或收不到图片 | 把一张普通图片与命令放在同一条消息，检查格式、大小与模型的图片输入能力 |
| 查不到出处 | 换较完整、清晰的图；检索范围取决于服务索引，候选链接也需自行核验 |

排查时提供运行的命令、固定错误提示和脱敏复现步骤即可；不要附 `.env`、登录数据、原始事件或 API 响应。参与开发见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 开发与检查

安装运行依赖后，再安装开发依赖并在项目根目录运行：

```powershell
$python = Join-Path $(if ($env:QQBOT_VENV) { $env:QQBOT_VENV } else { 'D:\IDE\python-envs\qqbotai' }) 'Scripts\python.exe'
& $python -m pip install -r requirements-dev.txt
& $python -m black --check .
& $python -m pip check
& $python -m unittest discover -s tests -v
& $python scripts/check_privacy.py
.\start.ps1 -Check
```

`python -m black .` 可统一 Python 格式。离线测试使用模拟 QQ、模型与搜索响应，不发送群消息或消耗真实 API 额度。`start.ps1 -Check` / `python bot.py --check` 只检查配置读取和插件装配，不代表 QQ 已连接；`configure.ps1 -Check` / `python configure.py --check` 另会要求启动所需的 Token 和允许群号完整。

暂存公开源码后，运行 `python scripts/check_privacy.py --staged` 检查实际待提交内容。仓库的 GitHub Actions 配置覆盖 Windows / Ubuntu 与 Python 3.11 / 3.14，具体结果以对应提交的工作流为准。

Linux / macOS 可自行创建虚拟环境，安装 `requirements.lock` 后运行 `python configure.py`、`python bot.py`。NapCat 需另行安装，配置到同机 OneBot 反向 WebSocket，Token 与本项目一致、消息格式为数组；Windows 的 D 盘目录不适用。

主要入口：

- `bot.py`：服务装配、启动、状态查询。
- `plugins/qq_chat.py`：群权限、明确 @ 判断与消息路由。
- `app/commands.py` / `app/chat.py`：功能菜单、命令别名、限流与近期记忆。
- `app/llm.py` / `app/images.py`：文本和视觉协议、图片处理。
- `app/websearch.py` / `app/saucenao.py` / `app/pexels.py`：独立搜索服务。
- `app/config.py` / `configure.py`：配置读取与本机向导。
- `prepare_napcat.py` / `app/napcat.py`：本机 NapCat 连接配置同步。
- `scripts/check_privacy.py`：公开文件与暂存区的隐私规则检查。

## 许可证

本项目自有代码采用 [MIT](LICENSE)。NapCat 需独立安装，其使用、修改和再分发受 [NapCat 自身许可证](https://github.com/NapNeko/NapCatQQ/blob/main/LICENSE) 约束，不属于本项目的 MIT 授权范围。QQ、模型和搜索服务分别适用各自的条款。
