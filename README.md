# FormLab — 结构与电路网页工作台

可运行的工程原型：FastAPI + CadQuery/OpenCascade + Three.js。默认无需 API 密钥。

## 功能与边界

- 结构：开口外壳、平板、L 型支架，尺寸/壁厚/四角安装孔；网页旋转缩放预览；真实实体 STEP（.step，可在 CAD 软件中另存 .stp）与 STL 下载。
- PCB：板宽/板深/二引脚演示元件数量，顶层布局和串联连接，KiCad PCB 文件与裸板 STEP/STL 导出。
- 对话：默认解析中文模板/尺寸指令，如 `生成 100×70×30 的外壳，壁厚 2，添加安装孔`。可选接入兼容 OpenAI Chat Completions 的大模型，仍限定在现有参数模板内，不执行模型生成的代码。
- **PCB 当前为布局演示**，没有原理图、器件选型、任意网络编辑、ERC/DRC、Gerber 或制造校验。不能直接投产。裸板 STEP 不含电子元件。结构尚无圆角、装配约束、强度分析或任意自由造型。
- 当前没有用户认证、项目数据库、历史撤销、文件配额和请求限流；每次生成的文件保存在 `artifacts/`。适合本地或受控网络使用。开放公网前需加认证、限流和清理策略。

## 安装与启动

要求 Linux、Python 3.12、Node.js 24（含 npm）。

```sh
cd /workspace/AITEST
python3 -m venv /workspace/.cad-venv
/workspace/.cad-venv/bin/pip install -r requirements.txt
npm ci --cache /workspace/.npm-cache
npm run build
/workspace/.cad-venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
```

服务同时提供构建后的网页和 API，端口 8000。开发前端可另开终端 `npm run dev`，Vite 代理 `/api` 到后端 8000。更改前端后重新构建；第一次生成可能需要等待 CAD 内核初始化。

验证：服务启动后运行 `/workspace/.cad-venv/bin/python tests/smoke.py`。测试真实 STEP 回读、三类结构、PCB 文件、聊天指令、非法参数和网页响应。浏览器需要 WebGL。

## 可选大模型

通过安全环境设置注入以下变量（不要提交密钥）：

- `DESIGN_AI_URL`：可信供应商的 HTTPS API 基址，例如 `https://api.openai.com/v1`。
- `DESIGN_AI_MODEL`：供应商可用且支持 JSON 输出的模型名称。
- `DESIGN_AI_KEY`：访问密钥。

三项齐全后重启后端。未配置时使用本地指令模式。配置后会向所选供应商发送设计参数和用户输入；确认该服务可信。实际供应商调用需要有效凭证，当前不预设密钥。API 报错会明确展示，不静默伪造 AI 回复。

## 服务器部署

提供 Dockerfile（尚未在此环境验证容器构建）：

```sh
docker build -t formlab .
docker run -d --name formlab --restart unless-stopped -p 127.0.0.1:8000:8000 formlab
```

将 Nginx / Caddy 反向代理到该端口，配置 HTTPS 和访问认证后再提供给用户。需要持久化时把应用用户可写的存储卷挂载到 `/app/artifacts`。本仓库当前不包含任何公网部署凭证，不会自动发布。

## 当前验证记录

- 前端生产构建通过。
- 9 项后端功能检查通过，三个结构 STEP 均由 OpenCascade 成功回读。
- Chromium 验证 3D 预览、对话修改尺寸、PCB 切换与导出入口、390px 移动布局，无 JavaScript 异常。
- KiCad 9.0.2 可读取演示板；DRC 返回 4 条 FormLab 自定义封装库缺失警告、0 未连接项。尚未关联原理图，不能据此证明电路功能或制造可用性。
- 大模型供应商调用和 Docker 镜像构建尚未验证。
