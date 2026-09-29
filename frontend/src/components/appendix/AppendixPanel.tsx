/**
 * 看板附录面板（2026-09-18 对齐方案B报告附录）
 * 四件套：A 字段字典 / B 清洗日志 / C 指标计算明细 / D 数据血缘
 * 全部来自后端真实管线元数据（GET /dashboards/{id}/appendix），确定性展示、可复跑复现。
 */
import React, { useEffect, useState } from 'react';
import { Card, Tabs, Table, Tag, Typography, Empty, Spin, Alert } from 'antd';
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

  /* ── B. 清洗与质检：行级明细表（ISS-051 night12 改向）──
     用户要求从 night11 的「叙事卡片」改为「行级明细表」。
     重要：管线元数据（后端 _clean_log）仅按「字段 × 问题类型」聚合存储——
     含 issue_type / strategy / stage / affected_rows(影响行数) / status，
     【不记录】原始数据行号、逐行清洗前/清洗后单元格值。
     故下表仅能呈现聚合级行（= 一条 clean_log 记录），无法呈现逐数据行明细。
     若需逐行明细（原始数据行号 | 清洗前 | 清洗后），须在 data_cleaner 落 change_log，超出本轮范围。 */
  const cleanLogTable = (() => {
    const log: any[] = data.clean_log || [];
    if (!log.length) {
      return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本看板暂无清洗与质检记录" />;
    }
    const rows = log.map((e: any, i: number) => {
      const stageLabel = e.stage === 'apply' ? '已执行清洗' : '质检发现';
      let statusLabel = '-';
      if (e.stage === 'apply') statusLabel = '已执行';
      else {
        const st = e.detail || '';
        if (st.includes('已修复') || st.includes('done')) statusLabel = '已修复';
        else if (st.includes('已忽略') || st.includes('ignored')) statusLabel = '已忽略';
        else if (st.includes('待处理') || st.includes('todo')) statusLabel = '待处理';
        else statusLabel = e.detail || '-';
      }
      const strategyLabel = e.strategy ? `${e.rule_type || ''}·${e.strategy}` : (e.rule_type || '-');
      return {
        key: i,
        field: e.target_field || '-',
        stage: stageLabel,
        issueType: e.issue_type || e.rule_type || '-',
        strategy: strategyLabel,
        affected: e.affected_rows ?? null,
        status: statusLabel,
      };
    });
    return (
      <div>
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="元数据未记录逐行明细"
          description="管线仅按「字段×问题类型」聚合存储（影响行数 + 状态），未落原始数据行号与逐行清洗前后值。下表为聚合级行（= 一条清洗/质检记录）。如需逐行明细（行号/清洗前/清洗后），须在 data_cleaner 落 change_log，建议单列需求。"
        />
        <Table
          size="small"
          rowKey="key"
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
          dataSource={rows}
          scroll={{ x: 'max-content' }}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无清洗与质检记录" /> }}
          columns={[
            { title: '字段', dataIndex: 'field', key: 'field', width: 160, fixed: 'left' as const },
            { title: '阶段', dataIndex: 'stage', key: 'stage', width: 110, render: (s: string) => <Tag color={s === '已执行清洗' ? 'blue' : 'default'}>{s}</Tag> },
            { title: '问题类型', dataIndex: 'issueType', key: 'issueType', width: 130 },
            { title: '清洗策略', dataIndex: 'strategy', key: 'strategy', width: 180 },
            { title: '影响行数', dataIndex: 'affected', key: 'affected', width: 100, align: 'right' as const, render: (v: any) => (v === null ? <Text type="secondary">-</Text> : numFmt(v)) },
            { title: '清洗后状态', dataIndex: 'status', key: 'status', width: 120, render: (s: string) => {
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
          { key: 'clean', label: `B. 清洗与质检${(data.clean_log || []).length ? ` (${data.clean_log.length})` : ''}`, children: cleanLogTable },
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
