# 1.10 附录 B 影响行数 — 实测证明

> 拍板：路演前不做行级明细，但加"影响行数"统计（比"策略 winsorize"更具体）。行级明细留路演后。

## 问题根因（已查清）
附录 B 的"影响行数"列后端一直存在，但 **apply（已清洗）阶段 winsorize 规则全部为 `None`**。
原因：`appendix_service._clean_log` 原只取 `QualityIssue.status=="done"` 回填 `rows_map`，
而真实数据中 winsorize 对应的质检问题状态为 `ignored`/`todo`（`affect_rows=2`），导致匹配落空。

## 修复
`backend/app/core/appendix_service.py`：`rows_map` 覆盖 `done/ignored/todo` 三态，并取最大 `affect_rows`
（避免同字段多状态重复计数）。apply 阶段据此匹配 `(dataset_id, target_field, issue_type)` 取数。

## 实测（正常后端）
```
GET /api/v1/dashboards/dash_e8c94106_509515/appendix
clean_log=15  影响行数非空=15  （修复前仅 10，apply 5 条全 None）
  seq=1 stage=apply 算子=transform 策略=winsorize 字段=抵押登记合规率   影响行数=2
  seq=2 stage=apply 算子=transform 策略=winsorize 字段=内部审计问题整改率 影响行数=2
  seq=3 stage=apply 算子=transform 策略=winsorize 字段=档案管理合规率   影响行数=2
  seq=4 stage=apply 算子=transform 策略=winsorize 字段=业务流程合规率   影响行数=2
  seq=5 stage=apply 算子=transform 策略=winsorize 字段=制度执行到位率   影响行数=2
  seq=6 stage=detect 算子=质检发现  策略=distribution 字段=业务流程合规率 影响行数=1
```
✅ apply 阶段 winsorize 现显示真实"影响行数=2"（比"策略 winsorize"更具体）。

## 结论
✅ 1.10（路演前范围）完成：附录 B「影响行数」对清洗规则已填充真实数值。
⌛ 行级明细（old/new/row）：按拍板留路演后（需加表 + 前端加列 + 性能成本）。
