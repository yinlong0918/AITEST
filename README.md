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

## 导入现有模型

点击工作台上方“导入文件”，单文件上限 20 MB：

| 格式 | 当前能力 |
| --- | --- |
| `.step` / `.stp` | 服务端读取真实 CAD 几何，生成 3D 预览，保留原 STEP，可下载三角化 STL |
| `.stl` / `.obj` | 浏览器本地网格预览，支持旋转、缩放、线框；可下载原文件 |
| `.glb` / `.gltf` | 浏览器本地加载；glTF 必须内嵌资源，不允许引用外部 bin 或纹理；不支持需额外解码器的压缩模型 |
| `.kicad_pcb` | 服务端解析 KiCad S 表达式，显示现代板文件中的线段、三点圆弧、板框、焊盘/过孔、封装变换、填充区轮廓；保留原文件 |

导入后进入独立查看模式，禁用模板参数和生成按钮；对话也不会覆盖导入文件。点击“返回参数设计”恢复原来的参数化工作流。导入不会恢复 CAD 建模历史，也不支持对导入几何进行参数化修改。STL/OBJ 缺少单位定义，按原始坐标显示，不宣称自动识别 mm；网格不能直接导出为 STEP。

KiCad 预览是二维几何概览，顶底层叠加显示，不是完整 EDA 编辑器：文本、尺寸、样条、图片不显示，自定义焊盘按外接框近似，铜区只显示已有填充轮廓；界面会提示检测到的这些限制。旧式圆弧或其他无法解析的格式会明确报错。原文件内容不受预览近似影响。没有运行 ERC/DRC，不可据此判断可制造性。

SolidWorks / Creo / CATIA 等原生结构文件请先导出 STEP；Altium、Eagle、立创 EDA 等原生电路板文件请先通过对应软件转换为 KiCad PCB。Gerber、原理图文件和 ZIP 工程包当前不支持导入，不会把制造文件误判为可编辑电路板。

新增导入验证（先启动服务）：

```sh
/workspace/.cad-venv/bin/python tests/imports_smoke.py
```

测试检查 STEP/STP 尺寸和三角网格、原文件完整保留、KiCad 旋转/圆弧、非法和超限文件。测试地址可通过 `FORMLAB_URL` 指定。导入接口没有认证，公网部署前同样需要配置访问控制、限流和资源隔离。

浏览器回归（首次安装 Chromium 后执行）：

```sh
npx playwright install chromium
npm run test:imports
```

已有系统 Chromium 时可设置 `CHROMIUM_PATH=/usr/bin/chromium`，无需下载。浏览器回归覆盖 6 种导入格式、退出查看模式、对话防覆盖、外部资源拒绝和移动布局。
