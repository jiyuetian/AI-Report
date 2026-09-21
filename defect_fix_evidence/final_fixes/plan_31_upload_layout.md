# plan_31 — 3.1 上传页布局（方案，待确认后改）

> 目的：上传首屏不被大拖拽区占满；上传后收缩成一行摘要，可继续追加。
> 状态：**先给方案，未改代码**。用户确认后再动手。

## 一、现状（UploadPage.tsx）
- `home-hero`（标语）+ `Steps`（四步进度）+ `upload-card` 内 `<Dragger>`（全尺寸拖拽区，lines 849-879）
  —— **无论是否已上传，Dragger 都占满首屏**。
- `upload-list-card`（line 883-）：`fileList.length>0` 时显示上传队列。

## 二、目标交互
1. 首次进入 / 尚未上传：仍显示完整大 Dragger（不变）。
2. **已上传 ≥1 份后**：Dragger 收缩为一行摘要条，不再占第一屏：
   - 文案：`已上传 N 份，可继续上传`（N = `doneFiles.length`）
   - 右侧一个「继续上传」按钮（点击展开完整 Dragger，可再选文件）
3. 点「继续上传」→ 展开完整 Dragger → 追加文件 → 成功后再次收缩。

## 三、改动点（预计 2 文件，低风险）
### 文件 A：`frontend/src/views/upload/UploadPage.tsx`
1. 组件内新增状态（约 line 60-125 附近，与其他 `useState` 并列）：
   ```ts
   const [uploadExpanded, setUploadExpanded] = useState(false)
   ```
2. 推导折叠判定（在 `doneFiles` 计算之后，约 line 820 附近）：
   ```ts
   const shouldCollapse = doneFiles.length > 0 && !uploadExpanded
   ```
3. 渲染处（line 849 `upload-card` 内）改为条件渲染：
   - `shouldCollapse` 为真 → 渲染紧凑摘要条：
     ```tsx
     <div className="upload-collapsed-bar">
       <span>已上传 {doneFiles.length} 份，可继续上传</span>
       <Button size="small" icon={<PlusOutlined />} onClick={() => setUploadExpanded(true)}>继续上传</Button>
     </div>
     ```
   - 否则 → 原 `<Dragger>` 整块（不变）。
4. 上传成功回调（约 line 596 `message.success` 附近）追加：
   ```ts
   setUploadExpanded(false)   // 上传完成后自动收缩
   ```

### 文件 B：`frontend/src/views/upload/UploadPage.css`
新增 `.upload-collapsed-bar` 样式（一行、虚线边框、浅底，紧凑不占屏）：
```css
.upload-collapsed-bar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; border: 1px dashed #d9d9d9; border-radius: 8px;
  background: #fafafa; color: rgba(0,0,0,.65); font-size: 14px;
}
.upload-collapsed-bar .ant-btn { margin-left: 12px; }
```

## 四、风险与注意
- **低风险**：纯展示态切换，不影响上传/质检/生成主链路。
- 折叠判定用 `doneFiles.length>0`（已完成上传的份数），避免"上传中"就误收缩。
- 暗色模式下 `.upload-collapsed-bar` 背景/文字需走现有 `[data-theme="dark"]` 覆盖体系（参考 theme.css），否则暗底下看不清——落地时一并加暗色覆盖。
- 不改动 `upload-list-card`（上传队列）本身，仅收缩上面的 Dragger。

## 五、验证（必须）
1. 首进上传页 → 大 Dragger 可见（不变）。
2. 上传 1 份成功 → Dragger 收缩为一行「已上传 1 份，可继续上传」。
3. 点「继续上传」→ Dragger 重新展开，可再选。
4. 再传 1 份 → 收缩为「已上传 2 份，可继续上传」。
5. 截图（沙箱无浏览器 → 本机 `npm run dev` 截图确认）。

## 六、待拍板
- 收缩触发条件：用「已上传份数 > 0」还是「已生成看板」？本方案取**已上传份数 > 0**（更贴合"上传后收缩"字面）。
- 是否需要在收缩条上直接显示已上传文件名列表（点击展开队列）？本方案不展开，保持一行最简。
