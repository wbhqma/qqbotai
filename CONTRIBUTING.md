# 参与开发

欢迎先用 issue 描述使用场景、实际结果和复现方法。修复或添加小功能时，保持一个 PR 对应一个明确问题。

## 本地验证

按 README 安装运行依赖后，在根目录安装开发工具：

```bash
python -m pip install -r requirements-dev.txt
```

提交前运行：

```bash
python -m black --check .
python -m unittest discover -s tests -v
python -m pip check
python scripts/check_privacy.py
python bot.py --check
```

这里的 `python` 指已激活虚拟环境的解释器；Windows 默认在 `D:\IDE\python-envs\qqbotai`，可用 `QQBOT_VENV` 覆盖。离线测试和 `--check` 不需要 QQ 或真实模型凭证。修改群事件、视觉或搜图协议后，还需由维护者在测试群联调；说明已验证的范围。

## 代码格式

使用 Black 26.1.0；`pyproject.toml` 统一每行 100 字符，按 Python 3.11 语法格式化。代码仍需通过 CI 的 Python 3.11 和 3.14 检查。编辑后可运行 `python -m black .`，CI 使用 `python -m black --check .` 检查同一规则。保持导入清晰、标准库和第三方依赖分组；本次规范只统一格式，不要求为通过检查而重构业务逻辑。

`app/persona.py` 是自定义人设入口，已通过 `force-exclude` 排除，直接指定这个文件也不会被 Black 改写；统一格式时保留已有的人设内容。私密配置、数据、缓存与运行目录同样排除，不得作为格式化或提交范围。提交前仍需运行隐私扫描，格式化工具不负责判断内容是否私密。

## 修改位置

- QQ 事件与发送规则放在 `plugins/`，聊天与记忆逻辑放在 `app/`。
- 命令别名和功能菜单集中在 `app/commands.py`；新增命令时同步维护路由、菜单和 README。
- NapCat 使用 OneBot V11 反向 WebSocket。空群白名单应拒绝处理，只有原始消息中的明确 @才触发；测试须使用真实 OneBot 事件和 Bot 类型。
- 图片功能在 `app/images.py`，只在显式请求、去重及限流检查后执行。下载地址限制为 QQ 图片 CDN，不接受本地路径或重定向；SerpApi 保持 `safe=active`，SauceNAO 保留 `hide=3` 筛选，不回显原始图片 URL 或服务响应。
- 模型调用通过 `app/llm.py` 中的 `LLMClient`；会话逻辑只依赖 `ChatModel.complete()` 协议，避免把 HTTP 请求、密钥或模型异常原文散落到插件里。
- 新服务先确认是否兼容已有协议，能通过配置接入时优先补充配置示例。新增协议时维护 `LLM_DEFAULTS`、端点、请求转换与响应文本解析，并使用脱敏 fixture 验证鉴权、人设、历史角色和响应结构。只向群内返回最终文本，不发送思考块或工具调用数据。
- 新增独立插件时，在 `plugins/` 添加模块，并在 `bot.py` 的 `build_bot()` 中显式调用 `nonebot.load_plugin("plugins.模块名")`。该目录当前不会自动加载全部文件。
- QQ 聊天匹配器的优先级为 10 且会阻断后续处理；新命令插件如需先处理，可使用更小的优先级数字，同时明确限制群 @事件。先用离线事件测试验证触发范围。
- 如果插件调用外部付费服务，应说明配置、超时和调用频率。核心聊天仍以群内 @触发为默认行为。

## 测试要求

改动影响用户行为时，补充能复现问题的测试。优先验证事件是否正确触发、上下文是否隔离、失败时是否可恢复。接口测试用 `httpx.MockTransport`，不要在 CI 里调用真实模型或发送 QQ 消息。

更新依赖时同步 `requirements.txt` 和 `requirements.lock`，保留平台专用依赖的条件，并在干净虚拟环境中重新安装检查。不要直接用单一平台的 `pip freeze` 覆盖条件行。

## 提交内容

代码、示例配置和项目说明可以提交。真实 `.env`、AppSecret、API Key、聊天记录及包含个人信息的日志不要提交。`.env.example` 的凭证字段必须留空。提交前运行 `python scripts/check_privacy.py --staged` 检查暂存区，再检查暂存内容；发现密钥暴露时先重置凭证。隐私检查是规则扫描，仍需人工确认来源数据和示例均不包含个人信息。

PR 说明写清问题、最终行为及验证结果。对于未完成的 QQ 联调，直接标注待验证。
