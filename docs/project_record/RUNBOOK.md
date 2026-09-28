<!-- 权威治理源文件：由 _coach_input/ 于 night8 Item3 步骤7 迁入 docs/project_record/。其他文档引用请以本文件为准。 -->


**为什么重要**：

- 你现在出问题"第一时间是问 AI"，AI 又慢又不可靠
    
- 手册在手，90% 的常见问题你自己 1 分钟搞定
    
- **和 FACTS 配合**：FACTS 说"是什么"，RUNBOOK 说"怎么办"

## 启动
1. 起后端：xxx
2. 起前端：xxx
3. 验证：curl http://127.0.0.1:8000/api/v1/health → 200

## 停止
- 按 Ctrl+C 优雅停
- 不要硬杀（DuckDB 会损坏）

## 常见故障
| 症状      | 原因         | 处置                 |
| ------- | ---------- | ------------------ |
| 图表全空    | DuckDB 路由错 | 检查 DUCKDB_PATH     |
| 端口被占    | 残留进程       | netstat + taskkill |
| LLM 不可达 | 代理挂了       | 重启 Clash           |
| 前端白屏    | 构建旧了       | npm run build      |