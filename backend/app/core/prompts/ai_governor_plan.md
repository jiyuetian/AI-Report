【本次上下文与用户原话】
{context_block}

{node_input}

【节点2·规划】请把每个事项规划成具体图表规格。规则：
① 每个事项单独一张图，title 用该事项的简短名称，禁止把整串原话当标题；
② chart_type 只能是 kpi|bar|line|pie|table，指标卡/卡片/总计卡一律用 kpi；
③ y_field 必须是字段清单里的真实字段名；kpi 不要 x_field；
④ 文本/标识类字段做指标时 aggregation 用 count，数值字段按语义用 sum 或 avg；
⑤ update/delete 必须带 target_chart_id。返回：
{"patches":[{"op":"add|update|delete|query","chart":{"title":"","chart_type":"kpi","y_field":"","x_field":"","aggregation":"count","target_chart_id":""}}],"notes":""}

## 变更契约（强制；违反的 patch 视为不可执行）
- 当用户原话是「新增/添加 N 个卡片、图表」且节点1 的每个事项 op=add 时，所有 patch 的 op 必须保持 add；
  禁止把新增项改成 update/delete 指向已有图表，也禁止漏掉任何一项。
- op=update/delete 必须填写一个在「当前看板图表」里真实存在的 target_chart_id；
  禁止臆造 id，也禁止只写 chart.id 而不写 target_chart_id。
- 节点4 验收必须逐条核对「动作类型是否与节点1 的 op 一致」与「目标图 id 是否真实存在」，
  不能只按字段数量判 ok=true。

## 用户点名项守恒（强制；优先级高于字段形态偏好）
- 节点1 拆出的每个 op=add 事项，都是用户明确点名的交付物；节点3/4/5 一律不得删除、合并或漏掉任何一项。
  只允许调整 chart_type / aggregation / x_field / title 措辞等图表形态，必须保留对应图表。
- 字段是文本 / 维度 / 时间类型，不构成否决理由：用户点名要它就必须保留；
  可以在 questions 或 changes 里提形态建议（改维度轴 / 筛选器），但不得因此把 ok 判为 false 或删图。
- 节点4 的 ok=false 只允许因事实错误：漏项、字段名不存在、目标图 id 不存在、
  会产生无绘制数据的空图、动作类型与节点1 不一致、标题臆造。
- 节点5 返回完整最终版时，patch 必须覆盖节点1 的全部点名项；只改形态不删项。
