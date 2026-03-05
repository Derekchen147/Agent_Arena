  前端项目结构

  frontend/
  ├── index.html
  ├── package.json
  ├── vite.config.ts          # 含 API/WS 代理配置 → localhost:8000
  ├── tsconfig.json
  └── src/
      ├── main.tsx             # 入口
      ├── index.css            # 全局样式（深色主题）
      ├── App.tsx              # 主组件，三栏布局 + 全局状态管理
      ├── App.css
      ├── types/
      │   └── index.ts         # 所有 TypeScript 类型（对应后端模型）
      ├── api/
      │   └── client.ts        # REST API 客户端（群组/消息/员工 CRUD）
      ├── hooks/
      │   └── useWebSocket.ts  # WebSocket hook（实时消息 + Agent 状态）
      └── components/
          ├── GroupSidebar.tsx/css   # 左栏：群组列表 + 创建群组
          ├── ChatArea.tsx/css      # 中栏：消息流 + @mention 输入
          └── AgentPanel.tsx/css    # 右栏：员工状态 + 成员管理 + 新增员工

  技术选型

  - React 18 + TypeScript + Vite — 类型安全，开发体验好
  - 纯 CSS — 无额外依赖，深色主题风格
  - WebSocket — 实时消息推送 + Agent 状态动画

  核心功能

  1. 群组管理 — 创建/删除群组，左侧列表切换
  2. 对话空间 — 消息历史加载，实时消息推送，@mention 弹窗选人
  3. 员工面板 — 实时状态显示（analyzing/generating/done
  等动画），添加/移除群组成员，新增员工（onboard）
  4. API 代理 — Vite dev server 自动代理 /api 和 /ws 到后端 localhost:8000

  运行方式

  cd frontend
  npm install   # 已完成
  npm run dev   # 启动开发服务器 → http://localhost:3000