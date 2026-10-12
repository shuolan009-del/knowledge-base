# 前端站点 · FRONTEND.md

把后端原有的两个独立功能页 —— `web/page/import.html`（建库，导入服务 :8000）与
`web/page/chat.html`（对话检索，查询服务 :8001）—— 整合并拆分为**多页静态站点**，
视觉与交互对齐 Apple 官网风格，零构建、可直接静态伺服。

---

## 一、产物文件清单

```
web/unified-frontend/
├── index.html     # 首页：Hero + 简介 + 三张功能入口卡片
├── import.html    # 建库页：上传 + 任务进度 + 节点可视化
├── chat.html      # 对话检索页：流式/非流式 + 历史 + 配图
├── workflow.html  # 工作流说明页：导入/检索两条流水线
├── styles.css     # 全部样式（四个页面共用）
├── app.js         # 全部交互逻辑（四个页面共用，按页初始化）
└── FRONTEND.md    # 本文档
```

> `.gitignore`（忽略 `.env` / `.edgeone/*` / `.tef_dist/*`）与 `.edgeone/` 为平台部署所需，与本前端无关。

- 无 npm / 无打包步骤，浏览器直接加载即可运行；无外部 CDN 依赖。
- `styles.css` 与 `app.js` 被四个页面共享；导航 / 登录视图 / 页脚 / 设置弹窗在每页各有一份相同标记
  （静态多页站点的常规做法，无需构建期模板）。

---

## 二、登录门禁（默认账号）

| 项 | 值 |
| --- | --- |
| 默认用户名 | **`admin`** |
| 默认密码 | **`kb2024`** |
| 账号常量位置 | `app.js` 顶部 `const AUTH = { user: 'admin', pass: 'kb2024', okValue: 'ok' }` |
| 登录态存储 | `localStorage['kb.auth'] = 'ok'` |

> ⚠️ **纯前端门禁，没有任何真实鉴权**：账号密码是前端明文常量，登录态只是 `localStorage`
> 里的一个标记，任何人打开 DevTools 都能绕过。**不能用于保护敏感数据**。日后接入真实后端时，
> 替换 `authModule` 中的 `isAuthed()` / `submitLogin()` 实现即可，其余 UI 与显隐逻辑无需改动。

**门禁对四个页面均生效**：每个页面 `<head>` 内都有一段内联脚本，在首次渲染前读取
`localStorage` 并给 `<html>` 预置 `is-locked` / `is-authed`，随后由 CSS 决定内容显隐：

- `html.is-locked` → 隐藏 `.nav` / `main` / `.footer`（**真正不渲染，不是遮罩**），只显示全屏登录卡；
- `html.is-authed` → 隐藏登录卡，内容正常展示。

**行为**：输错/留空 → 明确错误提示 + 卡片抖动；登录成功 → 写入登录态、切到内容视图、刷新页面
不再要求登录；退出登录 → 清除登录态并回到登录页。

---

## 三、页面结构与导航

### 3.1 逐页说明

| 页面 | 内容 |
| --- | --- |
| `index.html` | Hero 大标题「掌柜智库」+ 简介 + 两枚 CTA（开始建库 / 直接对话）+ **三张入口卡片**（建库 / 对话检索 / 工作流），点击跳转对应页面 |
| `import.html` | 页面标题 + 拖拽/点击多文件上传区 + 「处理任务」列表（进度条 / 节点步骤条 / 节点日志 / 清除已完成） |
| `chat.html` | 页面标题 + 对话卡片（工具条：API 状态 / 流式开关 / 清空历史）+ 消息区 + 输入区 |
| `workflow.html` | 页面标题 + 两张流水线卡片（导入 / 检索）+ 说明块 + 跳转 CTA |

### 3.2 统一导航

四个页面共用同一套顶部导航：

```
[品牌(回首页 index.html)]   建库 / 对话检索 / 工作流        [用户区] [设置] [汉堡(窄屏)]
```

- 导航链接是**真实跳转**（`<a href="import.html">` 等），不再是单页锚点。
- 当前所在页面的导航项由 `markActiveNav()` 依据 `location.pathname` 自动加 `.is-active` 高亮。
- 窄屏（≤720px）导航折叠为汉堡菜单 `#mobileMenu`，菜单内同样是真实跳转。
- 右上角：**用户区**（登录后显示，见下）+ 「设置」按钮（服务地址弹窗）。

### 3.3 页脚

四个页面共用同一套页脚：品牌 + 导航链接 + **双服务连接状态芯片**（`#pillImport` / `#pillQuery`，
由健康检查模块每 5s 刷新）+ 说明文字。

---

## 四、右上角用户区（登录后）

- 未登录时用户区不显示（内容整体被门禁隐藏）。
- 登录后导航右上角显示 `.user-menu`：**头像（用户名首字母）+ 用户名 + 绿色状态点 + 展开箭头**。
- 点击展开 `.user-dropdown`：显示账号（用户名 + 「已登录」）+ 「退出登录」。
- 点击页面其他区域或按 `Esc` 关闭下拉；点击「退出登录」二次确认后回到登录页。
- 头像/用户名通过 `data-user-name` / `data-user-avatar` 属性填充，触发按钮与下拉菜单内可同时出现且不产生重复 id。

其中用户名默认取 `AUTH.user`（`admin`），头像取其首字母 `A`。

---

## 五、组件划分与模块整合方式（`app.js`）

`app.js` 采用「**按页初始化**」：每个模块先自检必要元素，不存在则直接跳过，
因此任一页面缺少某模块的 DOM 也不会报错。

| 模块 | 职责 | 生效页面 |
| --- | --- | --- |
| `CONFIG` | 集中式后端地址配置（导入 / 查询 / 轮询间隔 / 健康检查间隔 / 存储键） | 全部 |
| `AUTH` | 登录账号常量 | 全部 |
| `initNav` | 导航滚动状态、汉堡菜单、当前页高亮 | 全部 |
| `initReveal` / `refreshReveals` | `IntersectionObserver` 滚动渐入位移；解锁后重新观察 | 全部 |
| `initHealth` | 双服务健康检查，刷新页脚状态芯片与对话页 `API:` 提示 | 全部（芯片缺失则跳过） |
| `importModule` | 建库：上传 / 轮询 / 进度条 / 节点步骤条 / 节点日志 | `import.html` |
| `chatModule` | 对话检索：历史 / 流式 SSE / 配图 / 清空 | `chat.html` |
| `authModule` | 登录门禁：`checkAuth` / `submitLogin` / `logout` / `requestLogout` / `applyState` | 全部 |
| `initUserMenu` | 右上角用户区：填充用户名、下拉开合、退出 | 全部 |
| `initSettings` | 服务地址设置弹窗（保存 / 恢复默认 / 退出登录） | 全部 |

`boot()` 顺序：`initNav → initReveal → initUserMenu → authModule.init → initSettings → importModule.init → chatModule.init → initHealth`。

### 5.1 建库模块（整合原 `import.html`）

- 拖拽 / 点击 / 键盘多文件上传（`POST /upload`，字段名 `files`，逐文件单独请求）。
- 每文件一张任务卡：进度条 + 状态徽标（上传中 / 处理中 / 已完成 / 失败）+ 「清除已完成」。
- 2s 轮询 `GET /status/{task_id}`；**节点进度可视化**：把后端中文节点名用「最长关键词命中」
  映射到标准流水线（上传文件 → 检查文件 → 文档解析 → 图片处理 → 文档切分 → 主体识别 →
  向量生成 → 导入向量库），渲染为 ✓ / 旋转圈 / 待处理步骤条；未匹配到的节点作为额外步骤追加，
  原始中文节点名完整保留在「节点日志」折叠面板 —— 零遗漏。

### 5.2 对话模块（整合原 `chat.html`）

- `localStorage` 会话 ID → `GET /history/{session_id}` 回填历史（含 `image_urls`）。
- 非流式 `POST /query`；流式 `POST /query{is_stream:true}` 后连 `GET /stream/{session_id}` SSE，
  监听 `ready / progress / delta / final（兼容 final_answer）/ error`。
- `【图片】` 标记 + 正则兜底提取配图，加载失败自动隐藏；`DELETE /history/{session_id}` 清空历史。
- **消息容器 id 为 `#chatLog`**（详见第七节「变更记录」中的 id 冲突修复）。

---

## 六、Apple 风格设计要点

- **字体**：`-apple-system` / SF Pro / PingFang 系统字体栈优先，紧字号 `letter-spacing:-0.02em`。
- **配色**：大面积中性灰白（`#fbfbfd` / `#f5f5f7` / `#fff`）+ 单一品牌蓝 `#0071e3` 点缀。
- **排版**：`clamp()` 流式大标题、居中产品化节奏、大留白；子页面统一使用 `.page-head`。
- **圆角 / 阴影**：大圆角（卡片 22–32px、胶囊 980px）+ 极浅阴影，hover 阴影加深并轻微上浮。
- **动效**：滚动渐入位移、按钮 hover/active 反馈、卡片阴影过渡、进度条流光、打字机三点、
  毛玻璃导航与下拉菜单 —— 全部克制；`prefers-reduced-motion` 全局降级。
- **响应式**：断点 860px（入口卡片/工作流双列→单列）、720px（导航折叠、隐藏用户名只留头像、
  发送按钮转图标、气泡收窄、装饰文案精简）。

---

## 七、本地预览 / 对接后端

### 7.1 启动两个后端服务（项目根目录下）

```bash
python web/api/import_service.py    # 导入服务 → http://127.0.0.1:8000
python web/api/query_service.py     # 查询服务 → http://127.0.0.1:8001
```

> 导入服务依赖环境变量 `DATA_BASED_ROOT_DIR`，且需先启动 Milvus / MongoDB / MinIO 等基础设施，详见根目录 `AGENTS.md`。

### 7.2 打开前端

用 `edgeone makers dev` 启动后访问 `http://127.0.0.1:8088/`（首页），
导航即可在四个页面间跳转；也可直接把 `web/unified-frontend/` 作为静态目录伺服。

两个后端均已开启 `CORS allow_origins=["*"]`，前端跨端口直连无需代理。

### 7.3 地址不可用时的排查

1. 页脚状态芯片：绿色 = 服务已连接，红色 = 不可达。
2. 后端不在默认端口时，点击右上角「设置」填写实际 Base URL，或用 URL 参数覆盖：
   `index.html?import=http://10.0.0.5:8000&query=http://10.0.0.5:8001`
   （地址优先级：**URL 参数 > localStorage（设置弹窗）> 默认值**）。

---

## 八、变更记录

### 本版本
1. **修复子页顶部大空白**：`.page-head > *` 与 `.page-head-bg` 优先级相同（均 0,1,0）且顺序在后，
   把装饰背景块的 `position:absolute` 覆盖成 `relative`，导致 560px 高的背景块变成普通流式块、
   把标题与功能区整体顶出首屏。现改为 `.page-head > :not(.page-head-bg) { position: relative; }`，
   并收紧 `.page-head` 上边距（`calc(var(--nav-h) + 30px)`）与子页首段 `.section-tight`（`padding-top:34px`）。
2. **修复登录后首屏元素不显示（opacity 仍为 0）**：`IntersectionObserver.observe()` 对
   「已在观察列表中的目标」是**无操作**，登录解锁后再次 `observe()` 不会触发新回调。
   `refreshReveals()` 现改为先 `unobserve` 再处理：视口内元素错峰揭示，视口外重新 `observe`。
3. **修复「聊天内容不在对话框内」**：`id="chat"` 曾同时用于锚点区块与消息容器，
   `$('#chat')` 命中区块，导致消息渲染到对话框卡片之外。消息容器改为唯一 id **`#chatLog`**，
   `app.js` 同步改为 `$('#chatLog')`；`.chat` 为 class，样式无需改动。
4. **拆分为多页站点**：新增 `import.html` / `chat.html` / `workflow.html`，`index.html` 改为首页
   （Hero + 三张入口卡片）；导航改为真实跳转并高亮当前页；`app.js` 改为按页初始化（模块自检元素，缺失即跳过）。
5. **新增右上角用户区**：登录后显示头像 + 用户名 + 已登录状态，下拉含「退出登录」。
6. 保留：设置弹窗（服务地址）、双服务健康检查、建库上传轮询、对话流式/历史、退出登录。

---

## 九、常见问答（FAQ）

**Q：为什么对话页的消息容器 id 是 `chatLog` 而不是 `chat`？**
A：因为 `chat` 曾被同时用作区块 id 与消息容器 id，`querySelector` 命中区块导致消息渲染到卡片外。
现统一为 `chatLog`，并保留 `chat` 仅作 class。

**Q：改一个页面要改四个文件吗？**
A：导航 / 登录视图 / 页脚 / 设置弹窗在四个页面各有一份相同标记，`styles.css` 与 `app.js` 是共用的。
这是静态多页站点的常规做法，无需构建期模板。

**Q：登录后刷新为什么不再要求登录？怎么改账号？**
A：登录成功写入 `localStorage['kb.auth']='ok'`，刷新时 `<head>` 内联脚本据此预置 `html.is-authed`。
改账号请编辑 `app.js` 顶部的 `AUTH` 常量。

**Q：怎么退出登录？**
A：右上角用户区 → 下拉「退出登录」（带确认），或「设置」弹窗底部「账号 → 退出登录」。

**Q：这个登录能保护数据吗？**
A：不能。它是纯前端门禁（明文常量 + localStorage 标记），仅用于展示层「先登录再看到内容」。

---

_本文档由前端工程师维护，随页面结构变更同步更新。_
