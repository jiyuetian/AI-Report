# ev_31 — 3.1 上传页布局（落地证据）

> 目标：上传 ≥1 份后，大 Dragger 收缩为一行，不占第一屏，且可继续追加上传。
> 依据：plan_31_upload_layout.md（用户已确认方案后动手）。

## 一、改动文件（2 个，均在约定范围）
| 文件 | 改动 | 行数 |
|---|---|---|
| `frontend/src/views/upload/UploadPage.tsx` | 状态 + 判定 + 条件渲染 + 成功回调自动收缩 | +63 / -24 |
| `frontend/src/views/upload/UploadPage.css` | `.upload-collapsed-bar` 样式 + 暗色覆盖 + 窄屏响应式 | +44 |

**越界检查**：用户约定"单文件 UploadPage.tsx"，样式归属 `UploadPage.css`（方案 A/B 项已明列 `.upload-collapsed-bar` 样式含暗色覆盖），**未触碰其他文件**。Dragger 唯一（仅 `UploadPage.tsx:895`），收缩逻辑只影响这一个上传入口。

## 二、核心 diff

### 1. 新增状态（`UploadPage.tsx:63`）
```diff
  const [uploading, setUploading] = useState(false)
+ // 3.1：上传≥1份后 Dragger 收缩为一行摘要（不占第一屏），点"继续上传"再展开
+ const [uploadExpanded, setUploadExpanded] = useState(false)
```

### 2. 图标 import（`:3`）
```diff
- import { InboxOutlined, FileExcelOutlined, ... } from '@ant-design/icons'
+ import { InboxOutlined, PlusOutlined, FileExcelOutlined, ... } from '@ant-design/icons'
```

### 3. 上传成功后自动收缩（`:611`）
```diff
      message.success(`${file.name} 上传成功`)
+     // 3.1：上传完成后自动收缩 Dragger，让首屏让位给内容（可点"继续上传"再展开）
+     setUploadExpanded(false)
```

### 4. 折叠判定（`:827`）
```diff
  const doneFiles = fileList.filter(f => f.status === 'done')
+ // 3.1：已上传≥1份 → 收缩 Dragger（用 done 份数，避免"上传中"就误收缩）
+ const shouldCollapse = doneFiles.length > 0 && !uploadExpanded
```

### 5. 条件渲染（`:856-912`）
- `shouldCollapse` → 一行摘要条：`已上传 N 份，可继续上传` + 「继续上传」按钮（`PlusOutlined`，点击 `setUploadExpanded(true)`）
- 非收缩 且 已上传≥1 份（即手动展开态）→ 额外一行：`已上传 N 份，正在追加上传` + 「收起」链接（边界：展开后想回到收缩态）
- 非收缩 → 原 `<Dragger>` 整块（结构/拖拽态/高亮逻辑完全不变）

### 6. 样式（`UploadPage.css`，`.upload-collapsed-bar`）
- 明色：虚线边框 `#d9d9d9`、背景 `#fafafa`、flex 两端对齐
- **暗色覆盖**：`[data-theme="dark"]` → 背景 `#1f1f1f`、边框 `#434343`、文字 `rgba(255,255,255,.85)`（对齐现有 `.upload-dragger` 暗色令牌，非新造色）
- **窄屏响应式**（≤576px）：`flex-direction: column` + 按钮 `margin-left:0`，避免按钮挤出卡片

## 三、边界情况（逐条已处理）
| 边界 | 处理 | 结论 |
|---|---|---|
| 上传中（status≠done）就收缩？ | 判定用 `doneFiles`（仅 done），不含 uploading | ✅ 不会误收缩 |
| 上传失败（status=error） | done 份数为 0 → 保持大 Dragger 可重试 | ✅ 符合预期 |
| 展开后改变主意想收起 | 展开态额外渲染「收起」→ `setUploadExpanded(false)` | ✅ 已补 |
| 展开后什么都没传就离开 | 下次进入 `uploadExpanded` 初值 false → 仍收缩 | ✅ 无残留态 |
| 删光所有文件 | `doneFiles.length=0` → 自动回到大 Dragger | ✅ 无需额外代码 |
| 窄屏按钮溢出 | ≤576px 换行 | ✅ 已加 media query |
| 暗色下看不清 | 走 `[data-theme="dark"]` 覆盖 | ✅ 已加 |
| 影响既有拖拽/上传逻辑？ | Dragger 整块未改，仅外层包条件；拖拽态 handlers 原样保留 | ✅ 零影响 |

## 四、验证
- **tsc**：`tsc --noEmit -p tsconfig.json` → **EXIT=0**（改动后跑 3 次，均 0）
- **静态核对**：改动点 grep 全部命中（import:3 / state:63 / 自动收缩:611 / 判定:827 / 渲染:856,887 / 展开按钮:865）
- **沙箱不能做的**：真实交互截图（无浏览器）→ 见下方本机清单

### 本机验证清单（必做，5 步）
1. `npm run dev` → 首进 `/`：**大 Dragger 可见**（未上传，行为不变）
2. 上传 1 份成功 → Dragger 收缩为一行：**`已上传 1 份，可继续上传`**
3. 点「继续上传」→ Dragger 重新展开，且上方出现「已上传 1 份，正在追加上传 / 收起」
4. 点「收起」→ 回到一行收缩态（不重新上传）
5. 再传 1 份 → 自动收缩为 **`已上传 2 份，可继续上传`**
6. （暗色）右上角切暗色 → 收缩条背景 `#1f1f1f`、文字清晰；窄屏（<576px）按钮换行不溢出
7. 截图：明/暗各一张

## 五、风险
- **低**：纯展示态切换，不触碰上传/质检/生成主链路；失败可整体回退（删除 `shouldCollapse` 三元即可还原）。
- 唯一行为变化：上传成功后 Dragger 由"常驻"变"收缩"，用户若想连续拖多个文件需多点一次「继续上传」——此即需求本意。
