# ev_36 — 3.6 管理后台设置页占位项（隐藏/标注）

## 一、复查发现：设置页（SettingsTab）是**全站唯一零 API 的 Tab**

| Tab | 数据来源 | 是否真实 |
|---|---|---|
| 概览 | `/admin/overview` | ✅ 真 |
| 用户 | `/admin/users` | ✅ 真 |
| 角色 | `/admin/roles` | ✅ 真 |
| 配额 | `/admin/overview` + `/tokens/applications/...` | ✅ 真 |
| 审计 | `/admin/audit` | ✅ 真 |
| Prompt 中心 | PromptCenter 组件 | ✅ 真 |
| **设置** | **无（纯静态硬编码）** | ❌ **全假** |

### 三类问题（严重性递增）
1. **硬编码假状态**（4 条，无任何数据源）：
   - `当前配置版本: v2.1.0`
   - `LLM网关: 已启用`
   - `审计日志: 已启用`
   - `自动备份: 每日00:00`
2. **"LLM网关: 已启用"是谎报**：后端 `/api/v1/health` 的 `llm_reachable` 可能为 `false`（沙箱实测就是 false），页面仍写死"已启用"——**直接违背 2.1 AI 能力鉴定与 2.4 绿/灰标的诚实原则**（那边刚做完"不可达就显示灰标"，这边还在说"已启用"）。
3. **失效声明 Alert**：`"配置中心已实现（M2-01），设置通过配置中心管理"` —— 全站检索 `配置中心` **仅命中这一行**，并无对应页面/功能，属失效/误导声明。

## 二、修复（`AdminPage.tsx` 单文件）

### 1. LLM 网关改为实时真取数（三态，不谎报）
```diff
+ const [llmReachable, setLlmReachable] = useState<boolean | null>(null);
+ useEffect(() => {
+   let alive = true;
+   http.get<any>('/health')
+     .then((res) => { const v = res?.llm_reachable ?? res?.data?.llm_reachable;
+                      if (alive) setLlmReachable(typeof v === 'boolean' ? v : null); })
+     .catch(() => { if (alive) setLlmReachable(null); });
+   return () => { alive = false; };
+ }, []);
```
```diff
- <p><strong>LLM网关:</strong> 已启用</p>
+ {llmReachable === true  && <Tag color="green">已启用（实时检测可达）</Tag>}
+ {llmReachable === false && <Tag color="red">当前不可达（将自动降级为规则生成）</Tag>}
+ {llmReachable === null  && <Tag color="default">状态未知（健康检查未返回）</Tag>}
```
> 三态设计：可达/不可达/**未知**——健康检查失败时不默认"已启用"，避免又一次谎报。

### 2. 其余三条假值 → 标注「即将上线」（不再展示假数字）
```diff
- <p><strong>当前配置版本:</strong> v2.1.0</p>
- <p><strong>审计日志:</strong> 已启用</p>
- <p><strong>自动备份:</strong> 每日00:00</p>
+ <p><strong>当前配置版本:</strong> <Tag>即将上线</Tag></p>
+ <p><strong>审计日志:</strong> <Tag>即将上线</Tag></p>
+ <p><strong>自动备份:</strong> <Tag>即将上线</Tag></p>
```

### 3. 失效 Alert 改为如实说明
```diff
- <Alert message="配置中心已实现（M2-01），设置通过配置中心管理" type="info" showIcon />
+ <Alert message="系统设置：仅「主题配置」为真实可操作项；其余状态项尚未接入数据源，
+         暂标注为「即将上线」，不做假展示。" type="info" showIcon />
```

### 4. 保留项（说明）
- **主题配置（明亮/暗黑）**：真实可操作（接 `AppThemeContext`），保留且在 Alert 中如实说明它是唯一真项。
- **角色页 Alert**（:250）`"MVP 阶段角色为只读…自定义角色与权限矩阵将在多用户版本开放"`：**本身已是诚实披露**（等价于"即将上线"），符合用户要求，保留未动。

## 三、验证
- **tsc**：`--noEmit` → **EXIT=0**
- **落盘核对**：grep 命中 `llmReachable`(505/548-550) 与 3 处 `即将上线`(553-555)、新 Alert(539-541)
- **数据源确认**：`/api/v1/health` → `llm_reachable`（`backend/app/api/health.py:96`），`http` 已在 :21 导入（复用，未新增依赖）

## 四、边界覆盖
| 边界 | 处理 |
|---|---|
| /health 请求失败 | `catch` → `null` → 显示"状态未知"，不谎报 |
| 组件卸载后返回 | `alive` 标志位，避免 setState 警告 |
| `llm_reachable` 字段嵌套在 data 下 | 兼容 `res.llm_reachable` 与 `res.data.llm_reachable` |
| 返回值非 boolean | 判定为 `null`（未知） |
| 主题切换 | 未改动，仍是真实功能 |
| 暗色模式 | 用 AntD `Tag`/`Alert` 语义色，自动适配暗色 |

## 五、本机验证清单
1. 打开 `/admin` → 设置 Tab
2. 确认**不再出现** `v2.1.0` / `每日00:00` / 写死的"已启用"
3. 确认三条显示「即将上线」Tag
4. 确认 LLM 网关显示**实时**状态：
   - 后端正常且 LLM 可达 → 绿色"已启用（实时检测可达）"
   - 断网/LLM 不可达 → 红色"当前不可达（将自动降级为规则生成）"。
   
   **路演价值**：这一条可直接当"诚实降级"的佐证——设置页与看板徽标口径一致。
5. 确认 Alert 文案已改（不再提"配置中心已实现"）
6. 截图 1-2 张（含 LLM 不可达场景）

## 六、风险
- **低**：仅改设置 Tab 渲染，新增一个只读 GET `/health`（与其它 Tab 同样的 `http` 用法），不改任何写操作。
- 若 `/health` 需要管理员权限则可能取不到 → 已用"状态未知"兜底，不会崩。
- 待拍板：是否要把"配置版本/审计日志/自动备份"接真实后端？当前标注"即将上线"是诚实的最小改动；若路演需要，可优先接**审计日志**（`/admin/audit` 已有数据）。
