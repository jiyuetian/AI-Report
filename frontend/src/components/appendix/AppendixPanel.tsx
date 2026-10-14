/**
 * 看板附录面板（2026-09-18 对齐方案B报告附录）
 * 四件套：A 字段字典 / B 清洗日志 / C 指标计算明细 / D 数据血缘
 * 全部来自后端真实管线元数据（GET /dashboards/{id}/appendix），确定性展示、可复跑复现。
 */
import React, { useEffect, useState } from 'react';
import { Card, Tabs, Table, Tag, Typography, Empty, Spin, Alert, Row, Col, Statistic } from 'antd';
import { http } from '../../utils/request';
// Phase 5：SkillPanel 薄壳收口（展示本面板由哪些后端 skill 驱动，暗色自动继承）
import SkillPanel from '../skills/SkillPanel';

const { Text, Paragraph } = Typography;

const numFmt = (n: any): string => {
  if (n === null || n === undefined) return '-';
  const v = Number(n);
  if (Number.isNaN(v)) return '-';
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
};

const pctFmt = (n: any): string => {
  if (n === null || n === undefined) return '-';
  return `${(Number(n) * 100).toFixed(1)}%`;
};

const severityColor = (t: string): string => {
  if (t.includes('duplicate')) return 'orange';
  if (t.includes('fill')) return 'blue';
  if (t.includes('format')) return 'geekblue';
  if (t.includes('filter')) return 'red';
  return 'default';
};

const RuleTypeLabel: Record<string, string> = {
  fill_null: '空值填充',
  remove_duplicate: '去重',
  format: '格式化',
  filter: '过滤',
  transform: '转换',
};

const AppendixPanel: React.FC<{ dashboardId: string }> = ({ dashboardId }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    http
      .get<any>(`/dashboards/${dashboardId}/appendix`)
      .then((res: any) => {
        // http.get 直接返回解析后的 JSON（无 axios res.data 包装）
        if (mounted) setData(res);
      })
      .catch(() => {
        if (mounted) setData(null);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [dashboardId]);

  if (loading) {
    return (
      <Card variant="outlined" style={{ marginTop: 20, borderRadius: 12 }}>
        <div style={{ textAlign: 'center', padding: '32px 0' }}>
          <Spin tip="正在汇编附录（字段实测 / 清洗日志 / 指标口径）" />
        </div>
      </Card>
    );
  }

  if (!data) return null;

  /* ── A. 字段字典 ── */
  const fieldDictTables = (data.field_dict || []).map((ds: any, idx: number) => {
    const multi = (data.field_dict || []).length > 1;
    return (
      <div key={ds.dataset_id || idx} style={{ marginBottom: multi ? 20 : 0 }}>
        {multi && (
          <div style={{ marginBottom: 8 }}>
            <Tag color="blue">{ds.dataset_name || ds.dataset_id}</Tag>
            <Text type="secondary" style={{ fontSize: 12 }}>
              表 {ds.table || '-'} · {numFmt(ds.row_count)} 行
            </Text>
          </div>
        )}
        <Table
          size="small"
          rowKey={(r: any, i?: number) => `${r.name}-${i}`}
          pagination={false}
          dataSource={ds.columns || []}
          columns={[
            // 2026-09-18 修复：取值范围列此前未设宽度，被拉伸到表格最右侧，离"唯一值数"隔了一大截。
            // 现在给它固定宽度，把弹性空间让给第一列"字段名"。
            { title: '字段名', dataIndex: 'name', key: 'name' },
            { title: '类型', dataIndex: 'type', key: 'type', width: 90, render: (t: string) => <Tag>{t}</Tag> },
            { title: '空值率', dataIndex: 'null_rate', key: 'null_rate', width: 90, render: pctFmt, align: 'right' as const },
            { title: '唯一值数', dataIndex: 'unique_count', key: 'unique_count', width: 100, render: numFmt, align: 'right' as const },
            {
              title: '取值范围',
              key: 'range',
              width: 180,
              render: (_: any, r: any) =>
                r.min !== null && r.max !== null ? `${numFmt(r.min)} ~ ${numFmt(r.max)}` : '-',
              align: 'right' as const,
            },
          ]}
          scroll={{ y: 360 }}
        />
      </div>
    );
  });

  /* ── B. 清洗明细：行级逐行表（night45 行级化，2026-10-12 收紧）──
     统一格式：原始文件行 | 字段 | 数据问题 | 清洗策略 | 清洗前结果 | 清洗后结果 | 状态。
     后端 _clean_log 仅返 quality_row_changes（已执行清洗的逐行改动 = 你改动影响的行），不聚合、
     不混入待处理质检发现；无改动时 data.clean_log 为空，此处显示空态。 */
  const cleanLogTable = (() => {
    const log: any[] = data.clean_log || [];
    if (!log.length) {
      return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本看板暂无清洗与质检记录" />;
    }
    const rows = log.map((e: any, i: number) => ({
      key: i,
      srcRow: e.src_row == null ? '—' : `行 ${e.src_row}`,
      field: e.field || '-',
      issueType: e.issue_type || '-',
      strategy: e.strategy || '-',
      before: e.before === '' || e.before == null ? '—' : e.before,
      after: e.after === '' || e.after == null ? '—' : e.after,
      status: e.status || '-',
    }));
    // ── 整体汇总（2026-10-14 补回）：此前该 tab 只有逐行明细，缺少"这次清洗到底做了什么"的总览
    const _bump = (m: Map<string, number>, k: string) => m.set(k, (m.get(k) || 0) + 1);
    const fieldSet = new Set<string>();
    const rowSet = new Set<string>();
    const issueMap = new Map<string, number>();
    const strategyMap = new Map<string, number>();
    const statusMap = new Map<string, number>();
    log.forEach((e: any) => {
      if (e.field) fieldSet.add(e.field);
      if (e.src_row != null) rowSet.add(String(e.src_row));
      if (e.issue_type) _bump(issueMap, String(e.issue_type));
      if (e.strategy) _bump(strategyMap, String(e.strategy));
      if (e.status) _bump(statusMap, String(e.status));
    });
    const _sorted = (m: Map<string, number>) => [...m.entries()].sort((a, b) => b[1] - a[1]);
    const _fixed = statusMap.get('已修复') || 0;
    const _pending = statusMap.get('待处理') || 0;
    const cleanSummary = (
      <div
        style={{
          background: 'linear-gradient(180deg, rgba(24,144,255,0.06) 0%, rgba(24,144,255,0.02) 100%)',
          border: '1px solid rgba(24,144,255,0.25)',
          borderRadius: 10,
          padding: '14px 16px',
          marginBottom: 14,
        }}
      >
        <div style={{ fontWeight: 600, marginBottom: 10, fontSize: 14 }}>整体汇总</div>
        <Row gutter={16}>
          <Col span={4}><Statistic title="清洗改动" value={log.length} suffix="处" /></Col>
          <Col span={5}><Statistic title="涉及字段" value={fieldSet.size} suffix="个" /></Col>
          <Col span={5}><Statistic title="涉及数据行" value={rowSet.size} suffix="行" /></Col>
          <Col span={5}>
            <Statistic title="已修复" value={_fixed} valueStyle={{ color: '#52c41a' }} />
          </Col>
          <Col span={5}>
            <Statistic title="待处理" value={_pending} valueStyle={{ color: _pending ? '#fa8c16' : undefined }} />
          </Col>
        </Row>
        <div style={{ marginTop: 12 }}>
          <Text strong style={{ marginRight: 8 }}>问题类型分布</Text>
          {_sorted(issueMap).map(([k, v]) => (
            <Tag key={k} color="volcano" style={{ marginBottom: 4 }}>{k} · {v}</Tag>
          ))}
        </div>
        <div style={{ marginTop: 6 }}>
          <Text strong style={{ marginRight: 8 }}>清洗策略分布</Text>
          {_sorted(strategyMap).map(([k, v]) => (
            <Tag key={k} color="blue" style={{ marginBottom: 4 }}>{k} · {v}</Tag>
          ))}
        </div>
      </div>
    );
    return (
      <div>
        {cleanSummary}
      <Table
        size="small"
        rowKey="key"
        pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
        dataSource={rows}
        scroll={{ x: 'max-content' }}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无清洗与质检记录" /> }}
        columns={[
          { title: '原始文件行', dataIndex: 'srcRow', key: 'srcRow', width: 110, fixed: 'left' as const },
          { title: '字段', dataIndex: 'field', key: 'field', width: 150 },
          { title: '数据问题', dataIndex: 'issueType', key: 'issueType', width: 140 },
          { title: '清洗策略', dataIndex: 'strategy', key: 'strategy', width: 170 },
          { title: '清洗前结果', dataIndex: 'before', key: 'before', width: 200, ellipsis: true },
          { title: '清洗后结果', dataIndex: 'after', key: 'after', width: 200, ellipsis: true },
          { title: '状态', dataIndex: 'status', key: 'status', width: 110, render: (s: string) => {
            if (s === '已修复') return <Tag color="green">已修复</Tag>;
            if (s === '已忽略') return <Tag>已忽略</Tag>;
            if (s === '待处理') return <Tag color="orange">待处理</Tag>;
            return <span>{s}</span>;
          } },
        ]}
      />
      </div>
    );
  })();

  /* ── C. 指标计算明细（产品化：SQL 翻译成口径公式，SQL 仅作可折叠技术细节） ── */
  const metricsTable = (
    <>
      <Table
        size="small"
        rowKey={(r: any, i?: number) => `${r.title}-${i}`}
        pagination={false}
        dataSource={data.metrics || []}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无指标" /> }}
        columns={[
          { title: '指标', dataIndex: 'title', key: 'title', width: 200 },
          { title: '类型', dataIndex: 'chart_type', key: 'chart_type', width: 80, render: (t: string) => <Tag>{t}</Tag> },
          {
            title: '计算口径（公式）',
            dataIndex: 'formula',
            key: 'formula',
            render: (f: string, r: any) => (
              <div>
                <div style={{ fontWeight: 500 }}>{f || '-'}</div>
                <details style={{ marginTop: 4 }}>
                  <summary style={{ cursor: 'pointer', color: '#1677ff', fontSize: 12 }}>查看计算 SQL</summary>
                  <pre style={{ margin: '6px 0 0', padding: 8, background: 'rgba(0,0,0,.03)', borderRadius: 6, fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{r.sql}</pre>
                </details>
              </div>
            ),
          },
          {
            title: '返回行数',
            dataIndex: 'rows',
            key: 'rows',
            width: 100,
            align: 'right' as const,
            render: (r: any) => (r === null ? <Text type="warning">-</Text> : numFmt(r)),
          },
        ]}
      />
      <Paragraph type="secondary" style={{ marginTop: 10, fontSize: 12, marginBottom: 0 }}>
        以上计算口径由图表配置反推，可在清洗后的数据集上复跑，结果与看板一致。
      </Paragraph>
    </>
  );

  /* ── D. 数据血缘：已移至独立的「数据血缘」页，附录不再重复（2026-09-18 产品化） ── */

  return (
    <SkillPanel panelKind="appendix" title="附录">
    <Card
      variant="outlined"
      style={{ marginTop: 20, borderRadius: 12 }}
      styles={{ body: { padding: '16px 20px' } }}
      title={
        <span style={{ fontSize: 15, fontWeight: 600 }}>
          附录
          <Text type="secondary" style={{ fontSize: 12, fontWeight: 400, marginLeft: 10 }}>
            数据加工全过程白盒：字段 → 清洗 → 指标
          </Text>
        </span>
      }
    >
      <Tabs
        defaultActiveKey="dict"
        items={[
          { key: 'dict', label: 'A. 字段字典', children: fieldDictTables },
          { key: 'clean', label: `B. 清洗明细${(data.clean_log || []).length ? ` (${data.clean_log.length})` : ''}`, children: cleanLogTable },
          { key: 'metric', label: 'C. 指标计算明细', children: metricsTable },
        ]}
      />
      <Paragraph type="secondary" style={{ marginTop: 8, fontSize: 12, marginBottom: 0 }}>
        {data.note}
      </Paragraph>
    </Card>
    </SkillPanel>
  );
};

export default AppendixPanel;
