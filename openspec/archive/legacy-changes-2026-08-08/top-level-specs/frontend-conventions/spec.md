## Requirements

### Requirement: 页面组件结构规范
前端页面组件 SHALL 遵循统一结构：
- 页面位于 `frontend/src/pages/` 目录，每个页面一个文件夹
- 组件文件使用 PascalCase 命名（如 `ImageGen.tsx`）
- 页面组件必须导出 default 函数组件
- 使用 React FC 类型或直接 function 定义

```tsx
// 正确示例：frontend/src/pages/image-gen/ImageGen.tsx
import React from 'react';
import { Card, Button } from 'antd';

const ImageGen: React.FC = () => {
  return <Card title="AI图片生成">{/* ... */}</Card>;
};

export default ImageGen;
```

#### Scenario: 创建新页面
- **WHEN** 需要添加新的前端页面
- **THEN** SHALL 在 `pages/` 下新建目录并创建同名的 TSX 组件文件，同时在 App.tsx 中注册路由

### Requirement: API 调用层规范
前后端通信 SHALL 通过统一的 API 层进行：
- API 调用封装在 `frontend/src/api/` 目录下
- 使用 Axios 实例， baseURL 指向后端地址
- 请求/响应类型使用 TypeScript interface 定义
- 文件上传使用 `FormData`，其他请求使用 JSON

```typescript
// 正确示例：frontend/src/api/image.ts
import request from '@/utils/request';
import { ImageGenerateParams, ImageGenerateResult } from '@/types/image';

export const generateImage = async (params: ImageGenerateParams): Promise<ImageGenerateResult> => {
  const { data } = await request.post('/api/v1/images/generate', params);
  return data;
};
```

#### Scenario: 添加新的 API 调用
- **WHEN** 前端需要调用后端接口
- **THEN** SHALL 在 `api/` 目录下创建或更新对应的 TypeScript 模块，定义请求/响应类型

### Requirement: 路由注册规范
前端路由 SHALL 在 `frontend/src/App.tsx` 中集中管理：
- 使用 `react-router-dom` v6 的 `createBrowserRouter`
- 路由配置包含 `path`、`element`、可选的 `loader`
- 布局路由使用嵌套 `<Outlet>` 结构
- 懒加载非首页组件（`React.lazy` + `Suspense`）

```tsx
// App.tsx 路由结构示例
const router = createBrowserRouter([
  { path: '/', element: <Home /> },
  { path: '/model-config', element: <ModelConfig /> },
  { path: '/image-gen', element: <ImageGen /> },
  { path: '/bilibili/login', element: <BilibiliLogin /> },
]);
```

#### Scenario: 注册新路由
- **WHEN** 新增了页面组件需要访问
- **THEN** SHALL 在 App.tsx 的 router 配置中添加对应的 route 对象

### Requirement: UI 组件使用规范
UI 组件 SHALL 基于 Ant Design 5 构建：
- 优先使用 Ant Design 组件库（`antd`），禁止引入其他 UI 库
- 中文 locale 已全局配置，无需重复设置
- 表单使用 `Form` + `Form.Item` 组合
- 数据展示使用 `Table`、`Descriptions`、`Card` 等
- 反馈使用 `message`、`modal`、`notification` 组件

```tsx
// 正确示例
import { Form, Input, Button, Card, message } from 'antd';

const MyForm = () => {
  const [form] = Form.useForm();
  
  const onFinish = async (values) => {
    try {
      await api.submit(values);
      message.success('提交成功');
    } catch (e) {
      message.error('提交失败');
    }
  };
  
  return (
    <Card>
      <Form form={form} onFinish={onFinish}>
        <Form.Item name="name" label="名称" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Button type="primary" htmlType="submit">提交</Button>
      </Form>
    </Card>
  );
};
```

#### Scenario: 构建用户界面
- **WHEN** 需要实现前端交互界面
- **THEN** SHALL 优先选用 antd 组件，保持与其他页面一致的视觉风格

### Requirement: 状态管理约定
组件状态管理 SHALL 遵循以下原则：
- **局部状态**：使用 `useState` / `useReducer`，足够时不要引入全局状态
- **异步状态**：使用自定义 Hook 封装（如 `useWebSocket`）
- **全局共享状态**：使用 React Context，按领域划分 Context
- **服务端状态**：考虑使用 TanStack Query（如已引入）或自定义缓存

#### Scenario: 管理组件状态
- **WHEN** 需要在组件间共享状态
- **THEN** SHALL 先评估是否真正需要跨组件共享，必要时使用 Context 或提升状态
