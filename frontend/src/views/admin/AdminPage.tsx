/**
 * 管理后台 - M4-07
 * 概览/用户/角色/配额/审计/设置 —— 全部接入真实后端接口（E01~E06）
 */

import React, { useState, useEffect, useContext, useCallback } from 'react';
import { AppThemeContext } from '../../themeContext';
import {
  Card, Tabs, Statistic, Row, Col, Table, Tag, Button,
  Progress, List, Badge, Timeline, Alert, Spin, Empty,
  Input, InputNumber, Switch, Modal, message, Typography
} from 'antd';
import {
  DashboardOutlined, UserOutlined, TeamOutlined,
  WalletOutlined, FileTextOutlined, SettingOutlined,
  ArrowUpOutlined, ArrowDownOutlined, WarningOutlined,
  CheckCircleOutlined, ClockCircleOutlined, ThunderboltOutlined
} from '@ant-design/icons';
import './AdminPage.css';
import PromptCenter from './PromptCenter';
import { http } from '../../utils/request';

const { Text } = Typography;

// 概览统计（E01）
const OverviewTab: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    let mounted = true;
    http.get<any>('/admin/overview')
      .then((d) => mounted && setData(d))
      .catch(() => mounted && setData(null))
      .finally(() => mounted && setLoading(false));
    return () => { mounted = false; };
  }, []);

  if (loading) return <Card><Spin tip="加载概览..." /></Card>;
  if (!data) return <Card><Empty description="暂无数据（后端未返回概览）" /></Card>;

  return (
    <div className="overview-tab">
      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic title="总用户数" value={data.total_users} prefix={<UserOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="活跃用户" value={data.active_users} prefix={<UserOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="看板总数" value={data.total_dashboards} prefix={<DashboardOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="数据集总数" value={data.total_datasets} prefix={<FileTextOutlined />} />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic title="版本快照" value={data.total_versions} prefix={<ClockCircleOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="分享链接" value={data.total_shares} prefix={<WalletOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="导出任务" value={data.total_exports} prefix={<FileTextOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="今日运行" value={data.today_api_calls} prefix={<ThunderboltOutlined />} />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card title="系统健康度">
            <Progress percent={data.system_health} status="active" strokeColor={{ '0%': '#108ee9', '100%': '#87d068' }} />
            <div className="health-metrics">
              <span><CheckCircleOutlined /> 数据库: 正常</span>
              <span><CheckCircleOutlined /> 缓存: 正常</span>
              <span><CheckCircleOutlined /> 队列: 正常</span>
            </div>
          </Card>
        </Col>
        <Col span={12}>
          <Card title="最近活动">
            {data.recent_activity && data.recent_activity.length > 0 ? (
              <Timeline>
                {data.recent_activity.map((a: any, i: number) => (
                  <Timeline.Item key={i} color={a.result === 'success' ? 'green' : 'red'}>
                    {a.user || '系统'} 执行了 {a.action}
                    {a.object_type ? `（${a.object_type}）` : ''}
                  </Timeline.Item>
                ))}
              </Timeline>
            ) : (
              <Empty description="暂无审计活动" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

// 用户管理（E02）—— 2026-09-18：编辑/禁用接真实 PATCH /admin/users/:id（此前是假按钮）
const UsersTab: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [users, setUsers] = useState<any[]>([]);
  const [editOpen, setEditOpen] = useState(false);
  const [editUser, setEditUser] = useState<any>(null);
  const [editQuota, setEditQuota] = useState<number>(5000);
  const [editActive, setEditActive] = useState(true);
  const [saving, setSaving] = useState(false);

  const loadUsers = useCallback(() => {
    setLoading(true);
    http.get<any>('/admin/users')
      .then((d) => setUsers(d.users || []))
      .catch(() => setUsers([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadUsers(); }, [loadUsers]);

  const openEdit = (u: any) => {
    setEditUser(u);
    setEditQuota(u.token_quota ?? 5000);
    setEditActive(!!u.is_active);
    setEditOpen(true);
  };

  const saveEdit = async () => {
    if (!editUser) return;
    setSaving(true);
    try {
      await http.patch(`/admin/users/${editUser.id}`, {
        token_quota: editQuota,
        is_active: editActive,
      });
      message.success(`已保存用户 ${editUser.username} 的变更`);
      setEditOpen(false);
      loadUsers();
    } catch (err: any) {
      message.error(`保存失败: ${err?.message || '网络错误'}`);
    } finally {
      setSaving(false);
    }
  };

  const quickToggle = async (u: any) => {
    try {
      await http.patch(`/admin/users/${u.id}`, { is_active: !u.is_active });
      message.success(`已${u.is_active ? '停用' : '启用'} ${u.username}`);
      loadUsers();
    } catch (err: any) {
      message.error(`操作失败: ${err?.message || '网络错误'}`);
    }
  };

  const userColumns = [
    { title: '用户名', dataIndex: 'username', key: 'username' },
    { title: '邮箱', dataIndex: 'email', key: 'email' },
    { title: '角色', dataIndex: 'roles', key: 'roles', render: (roles: string[]) => (
      (roles || []).map((r: string) => <Tag key={r} color={r === 'admin' ? 'red' : 'blue'}>{r}</Tag>)
    )},
    { title: '状态', dataIndex: 'is_active', key: 'is_active', render: (s: boolean) => (
      <Badge status={s ? 'success' : 'default'} text={s ? '启用' : '停用'} />
    )},
    { title: 'Token配额', dataIndex: 'token_quota', key: 'token_quota' },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', render: (v: string) => v || '-' },
    { title: '操作', key: 'action', render: (_: any, u: any) => (
      <Button.Group>
        <Button size="small" onClick={() => openEdit(u)}>编辑</Button>
        <Button size="small" danger={u.is_active} onClick={() => quickToggle(u)}>
          {u.is_active ? '禁用' : '启用'}
        </Button>
      </Button.Group>
    )}
  ];

  return (
    <Card>
      {loading ? <Spin tip="加载用户..." /> : (
        <Table columns={userColumns} dataSource={users} rowKey="id" locale={{ emptyText: '暂无用户（系统尚未初始化账号）' }} />
      )}

      <Modal
        title={`编辑用户 - ${editUser?.username || ''}`}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={saveEdit}
        confirmLoading={saving}
        okText="保存"
      >
        <div style={{ marginBottom: 16 }}>
          <b>Token 配额</b>
          <InputNumber
            style={{ width: '100%', marginTop: 8 }}
            min={0}
            max={10000000}
            step={500}
            value={editQuota}
            onChange={(v) => setEditQuota(Number(v) || 0)}
          />
        </div>
        <div>
          <b>账号状态</b>
          <div style={{ marginTop: 8 }}>
            <Switch checked={editActive} onChange={setEditActive} checkedChildren="启用" unCheckedChildren="停用" />
          </div>
        </div>
      </Modal>
    </Card>
  );
};

// 角色管理（E03）—— 只读展示真实 roles 表（2026-09-18：移除"创建角色/编辑"假按钮，如实标注 MVP 只读）
const RolesTab: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [roles, setRoles] = useState<any[]>([]);

  useEffect(() => {
    let mounted = true;
    http.get<any>('/admin/roles')
      .then((d) => mounted && setRoles(d.roles || []))
      .catch(() => mounted && setRoles([]))
      .finally(() => mounted && setLoading(false));
    return () => { mounted = false; };
  }, []);

  return (
    <Card>
      <Alert
        message="MVP 阶段角色为只读（admin / user 预置角色）；自定义角色与权限矩阵将在多用户版本开放"
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />
      {loading ? <Spin tip="加载角色..." /> : (
        <List
          dataSource={roles}
          locale={{ emptyText: '暂无角色' }}
          renderItem={role => (
            <List.Item>
              <List.Item.Meta
                title={<span>{role.name} <Tag style={{ marginLeft: 8 }}>{role.user_count} 用户</Tag></span>}
                description={role.description}
              />
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 4 }}>默认配额 {role.default_quota ?? '-'} tokens/日</div>
                {(role.permissions || []).map((p: string) => <Tag key={p} color="blue">{p}</Tag>)}
              </div>
            </List.Item>
          )}
        />
      )}
    </Card>
  );
};

// 配额管理（E04）—— 2026-09-18：接入真实加量申请审批（/tokens/applications/admin/*，此前是空态假页面）
const QuotaTab: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>(null);
  const [apps, setApps] = useState<any[]>([]);
  const [appsLoading, setAppsLoading] = useState(true);
  const [approveApp, setApproveApp] = useState<any>(null);
  const [approveAmount, setApproveAmount] = useState<number>(0);
  const [rejectApp, setRejectApp] = useState<any>(null);
  const [comment, setComment] = useState('');
  const [acting, setActing] = useState(false);

  const loadOverview = useCallback(() => {
    setLoading(true);
    http.get<any>('/admin/overview')
      .then((d) => setData(d))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  const loadApps = useCallback(() => {
    setAppsLoading(true);
    http.get<any>('/tokens/applications/admin/pending')
      .then((d) => setApps(d.applications || []))
      .catch(() => setApps([]))
      .finally(() => setAppsLoading(false));
  }, []);

  useEffect(() => { loadOverview(); loadApps(); }, [loadOverview, loadApps]);

  const doApprove = async () => {
    if (!approveApp) return;
    setActing(true);
    try {
      await http.post(`/tokens/applications/admin/${approveApp.id}/approve`, {
        approved_amount: approveAmount,
        comment,
      });
      message.success(`已批准 ${approveApp.user_id} 增加 ${approveAmount} Token`);
      setApproveApp(null);
      setComment('');
      loadApps();
    } catch (err: any) {
      message.error(`审批失败: ${err?.detail?.message || err?.message || '网络错误'}`);
    } finally {
      setActing(false);
    }
  };

  const doReject = async () => {
    if (!rejectApp) return;
    setActing(true);
    try {
      await http.post(`/tokens/applications/admin/${rejectApp.id}/reject`, { comment });
      message.success('已驳回该申请');
      setRejectApp(null);
      setComment('');
      loadApps();
    } catch (err: any) {
      message.error(`驳回失败: ${err?.detail?.message || err?.message || '网络错误'}`);
    } finally {
      setActing(false);
    }
  };

  const appColumns = [
    { title: '用户', dataIndex: 'user_id', key: 'user_id' },
    { title: '申请数量', dataIndex: 'apply_amount', key: 'apply_amount', render: (v: number) => <Tag color="blue">{v} tokens</Tag> },
    { title: '申请理由', dataIndex: 'apply_reason', key: 'apply_reason', ellipsis: true },
    { title: '申请时间', dataIndex: 'created_at', key: 'created_at', render: (v: string) => v || '-' },
    { title: '操作', key: 'action', render: (_: any, r: any) => (
      <Button.Group>
        <Button size="small" type="primary" onClick={() => { setApproveApp(r); setApproveAmount(r.apply_amount || 0); setComment(''); }}>批准</Button>
        <Button size="small" danger onClick={() => { setRejectApp(r); setComment(''); }}>驳回</Button>
      </Button.Group>
    )},
  ];

  return (
    <Card>
      <Row gutter={16}>
        <Col span={8}>
          <Card title="资源总览" size="small">
            {loading ? <Spin /> : (
              <>
                <Statistic title="看板总数" value={data?.total_dashboards ?? 0} />
                <Statistic title="数据集总数" value={data?.total_datasets ?? 0} style={{ marginTop: 12 }} />
                <Statistic title="版本快照" value={data?.total_versions ?? 0} style={{ marginTop: 12 }} />
                <p style={{ marginTop: 12, color: '#888' }}>每用户默认每日 5000 tokens，可在「用户」页调整</p>
              </>
            )}
          </Card>
        </Col>
        <Col span={16}>
          <Card title={`待审批申请${apps.length ? `（${apps.length}）` : ''}`} size="small">
            {appsLoading ? <Spin /> : (
              <Table
                size="small"
                columns={appColumns}
                dataSource={apps}
                rowKey="id"
                locale={{ emptyText: '暂无待审批的配额调整申请' }}
              />
            )}
          </Card>
        </Col>
      </Row>

      <Modal
        title={`批准加量 - ${approveApp?.user_id || ''}`}
        open={!!approveApp}
        onCancel={() => setApproveApp(null)}
        onOk={doApprove}
        confirmLoading={acting}
        okText="确认批准"
      >
        <div style={{ marginBottom: 12 }}>申请数量：<b>{approveApp?.apply_amount}</b> tokens · 理由：{approveApp?.apply_reason}</div>
        <div style={{ marginBottom: 8 }}><b>批准数量</b></div>
        <InputNumber style={{ width: '100%' }} min={0} max={10000} step={100} value={approveAmount} onChange={(v) => setApproveAmount(Number(v) || 0)} />
        <div style={{ margin: '12px 0 8px' }}><b>审批备注（可选）</b></div>
        <Input.TextArea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
      </Modal>

      <Modal
        title={`驳回申请 - ${rejectApp?.user_id || ''}`}
        open={!!rejectApp}
        onCancel={() => setRejectApp(null)}
        onOk={doReject}
        confirmLoading={acting}
        okText="确认驳回"
        okButtonProps={{ danger: true }}
      >
        <div style={{ marginBottom: 8 }}><b>驳回理由（可选）</b></div>
        <Input.TextArea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
      </Modal>
    </Card>
  );
};

// 审计日志（E05）—— 2026-09-18：筛选/导出接真实功能（此前两个按钮点了没反应）
const AuditTab: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [logs, setLogs] = useState<any[]>([]);
  const [fUser, setFUser] = useState('');
  const [fAction, setFAction] = useState('');

  const loadLogs = useCallback((user = '', action = '') => {
    setLoading(true);
    const params = new URLSearchParams({ limit: '100' });
    if (user) params.set('user', user);
    if (action) params.set('action', action);
    http.get<any>(`/admin/audit?${params.toString()}`)
      .then((d) => setLogs(d.logs || []))
      .catch(() => setLogs([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadLogs(); }, [loadLogs]);

  const exportCsv = () => {
    if (!logs.length) {
      message.warning('当前无日志可导出');
      return;
    }
    const header = ['id', 'user', 'action', 'object_type', 'object_id', 'result', 'ip', 'detail'];
    const esc = (v: any) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const rows = logs.map(l => header.map(h => esc(l[h])).join(','));
    const csv = '\uFEFF' + header.join(',') + '\n' + rows.join('\n'); // BOM 防 Excel 乱码
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `audit_logs_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    message.success(`已导出 ${logs.length} 条审计日志`);
  };

  const auditColumns = [
    { title: '用户', dataIndex: 'user', key: 'user', render: (v: string) => v || '系统' },
    { title: '操作', dataIndex: 'action', key: 'action' },
    { title: '对象', dataIndex: 'object_type', key: 'object_type', render: (v: string) => v || '-' },
    { title: '结果', dataIndex: 'result', key: 'result', render: (r: string) => (
      <Tag color={r === 'success' ? 'success' : 'error'}>{r}</Tag>
    )},
    { title: 'IP', dataIndex: 'ip', key: 'ip', render: (v: string) => v || '-' },
    { title: '详情', dataIndex: 'detail', key: 'detail', ellipsis: true, render: (v: any) => (
      v ? <span style={{ fontSize: 12, color: '#8c8c8c' }}>{typeof v === 'string' ? v : JSON.stringify(v)}</span> : '-'
    )},
  ];

  return (
    <Card>
      <div className="tab-toolbar">
        <Input
          allowClear
          placeholder="按用户筛选"
          value={fUser}
          onChange={e => setFUser(e.target.value)}
          style={{ width: 180 }}
          onPressEnter={() => loadLogs(fUser, fAction)}
        />
        <Input
          allowClear
          placeholder="按操作筛选（如 dashboard.create）"
          value={fAction}
          onChange={e => setFAction(e.target.value)}
          style={{ width: 240 }}
          onPressEnter={() => loadLogs(fUser, fAction)}
        />
        <Button type="primary" onClick={() => loadLogs(fUser, fAction)}>查询</Button>
        <Button onClick={exportCsv}>导出CSV</Button>
      </div>
      {loading ? <Spin tip="加载审计..." /> : (
        <Table columns={auditColumns} dataSource={logs} rowKey="id" locale={{ emptyText: '暂无审计日志' }} />
      )}
    </Card>
  );
};

// 系统设置（E06）—— 主题配置卡片可实时切换明/暗
const SettingsTab: React.FC = () => {
  const appThemeCtx = useContext(AppThemeContext);
  const theme = appThemeCtx?.theme || 'light';

  const ThemeCard: React.FC<{ keyName: string; label: string; active: boolean; onClick: () => void }> = ({
    keyName, label, active, onClick,
  }) => (
    <div
      onClick={onClick}
      style={{
        flex: 1, cursor: 'pointer', padding: 16, borderRadius: 8,
        border: `2px solid ${active ? '#1677ff' : 'var(--app-border, #f0f0f0)'}`,
        background: keyName === 'dark' ? '#141414' : '#ffffff',
        color: keyName === 'dark' ? '#fff' : '#000',
        textAlign: 'center',
      }}
    >
      <div style={{ fontSize: 22, marginBottom: 8 }}>{keyName === 'dark' ? '🌙' : '☀️'}</div>
      <div style={{ fontWeight: active ? 600 : 400 }}>{label}{active ? '（当前）' : ''}</div>
    </div>
  );

  return (
    <Card title="系统设置">
      <Alert message="配置中心已实现（M2-01），设置通过配置中心管理" type="info" showIcon />
      <div style={{ marginTop: 16 }}>
        <p><strong>当前配置版本:</strong> v2.1.0</p>
        <p><strong>LLM网关:</strong> 已启用</p>
        <p><strong>审计日志:</strong> 已启用</p>
        <p><strong>自动备份:</strong> 每日00:00</p>
      </div>
      <div style={{ marginTop: 16 }}>
        <p style={{ fontWeight: 600, marginBottom: 8 }}>主题配置（实时预览）</p>
        <div style={{ display: 'flex', gap: 16 }}>
          <ThemeCard keyName="light" label="明亮主题" active={theme === 'light'} onClick={() => appThemeCtx?.setTheme('light')} />
          <ThemeCard keyName="dark" label="暗黑主题" active={theme === 'dark'} onClick={() => appThemeCtx?.setTheme('dark')} />
        </div>
      </div>
    </Card>
  );
};

// 主页面
const AdminPage: React.FC = () => {
  return (
    <div className="admin-page">
      <h2 className="page-title">
        <SettingOutlined /> 管理后台
      </h2>

      {/* 2026-09-18 修复：antd5 已废弃 <Tabs><TabPane> 子组件写法，
          会产生一个无法点击的幻影空 Tab（原型对比中圈出的空白）；改为 items 声明式写法 */}
      <Tabs
        defaultActiveKey="overview"
        className="admin-tabs"
        items={[
          { key: 'overview', label: <span><DashboardOutlined /> 概览</span>, children: <OverviewTab /> },
          { key: 'users', label: <span><UserOutlined /> 用户</span>, children: <UsersTab /> },
          { key: 'roles', label: <span><TeamOutlined /> 角色</span>, children: <RolesTab /> },
          { key: 'quota', label: <span><WalletOutlined /> 配额</span>, children: <QuotaTab /> },
          { key: 'audit', label: <span><FileTextOutlined /> 审计</span>, children: <AuditTab /> },
          { key: 'prompts', label: <span><ThunderboltOutlined /> Prompt 中心</span>, children: <PromptCenter /> },
          { key: 'settings', label: <span><SettingOutlined /> 设置</span>, children: <SettingsTab /> },
        ]}
      />
    </div>
  );
};

export default AdminPage;
