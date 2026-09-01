/**
 * 管理后台 - M4-07
 * 概览/用户/角色/配额/审计/设置
 */

import React, { useState } from 'react';
import {
  Card, Tabs, Statistic, Row, Col, Table, Tag, Button,
  Progress, List, Badge, Timeline, Alert
} from 'antd';
import {
  DashboardOutlined, UserOutlined, TeamOutlined,
  WalletOutlined, FileTextOutlined, SettingOutlined,
  ArrowUpOutlined, ArrowDownOutlined, WarningOutlined,
  CheckCircleOutlined, ClockCircleOutlined
} from '@ant-design/icons';
import './AdminPage.css';

const { TabPane } = Tabs;

// 概览统计
const OverviewTab: React.FC = () => {
  const stats = {
    total_users: 156,
    active_users: 142,
    total_dashboards: 328,
    total_datasets: 512,
    today_api_calls: 12580,
    system_health: 98
  };

  return (
    <div className="overview-tab">
      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic title="总用户数" value={stats.total_users} prefix={<UserOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="活跃看板" value={stats.total_dashboards} prefix={<DashboardOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="数据集" value={stats.total_datasets} prefix={<FileTextOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="今日调用" value={stats.today_api_calls} prefix={<WalletOutlined />} />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card title="系统健康度">
            <Progress percent={stats.system_health} status="active" strokeColor={{ '0%': '#108ee9', '100%': '#87d068' }} />
            <div className="health-metrics">
              <span><CheckCircleOutlined /> 数据库: 正常</span>
              <span><CheckCircleOutlined /> 缓存: 正常</span>
              <span><CheckCircleOutlined /> 队列: 正常</span>
            </div>
          </Card>
        </Col>
        <Col span={12}>
          <Card title="最近活动">
            <Timeline>
              <Timeline.Item color="green">用户张三创建了看板"担保风控"</Timeline.Item>
              <Timeline.Item color="blue">系统完成数据备份</Timeline.Item>
              <Timeline.Item color="orange">用户李四申请Token加量</Timeline.Item>
            </Timeline>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

// 用户管理
const UsersTab: React.FC = () => {
  const userColumns = [
    { title: '用户名', dataIndex: 'username', key: 'username' },
    { title: '邮箱', dataIndex: 'email', key: 'email' },
    { title: '角色', dataIndex: 'role', key: 'role', render: (role: string) => (
      <Tag color={role === 'admin' ? 'red' : role === 'analyst' ? 'blue' : 'default'}>{role}</Tag>
    )},
    { title: '状态', dataIndex: 'status', key: 'status', render: (status: string) => (
      <Badge status={status === 'active' ? 'success' : 'default'} text={status} />
    )},
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at' },
    { title: '操作', key: 'action', render: () => (
      <Button.Group>
        <Button size="small">编辑</Button>
        <Button size="small" danger>禁用</Button>
      </Button.Group>
    )}
  ];

  const userData = [
    { key: '1', username: 'admin', email: 'admin@company.com', role: 'admin', status: 'active', created_at: '2026-01-01' },
    { key: '2', username: '张三', email: 'zhangsan@company.com', role: 'analyst', status: 'active', created_at: '2026-08-01' },
    { key: '3', username: '李四', email: 'lisi@company.com', role: 'viewer', status: 'inactive', created_at: '2026-08-10' }
  ];

  return (
    <Card>
      <div className="tab-toolbar">
        <Button type="primary">批量导入</Button>
        <Button>重置密码</Button>
      </div>
      <Table columns={userColumns} dataSource={userData} />
    </Card>
  );
};

// 角色管理
const RolesTab: React.FC = () => {
  const roles = [
    { name: 'admin', description: '系统管理员', permissions: ['全部权限'], user_count: 2 },
    { name: 'analyst', description: '数据分析师', permissions: ['看板编辑', '数据查看'], user_count: 45 },
    { name: 'viewer', description: '只读用户', permissions: ['看板查看'], user_count: 89 },
    { name: 'operator', description: '运营人员', permissions: ['看板查看', '分享'], user_count: 20 }
  ];

  return (
    <Card>
      <div className="tab-toolbar">
        <Button type="primary">创建角色</Button>
        <Alert message="自定义角色权限矩阵通过JSON配置" type="info" showIcon style={{ marginTop: 8 }} />
      </div>
      <List
        dataSource={roles}
        renderItem={role => (
          <List.Item
            actions={[<Button size="small">编辑</Button>, <Button size="small">权限</Button>]}
          >
            <List.Item.Meta
              title={role.name}
              description={role.description}
            />
            <div>
              <Tag>{role.user_count} 用户</Tag>
              {role.permissions.map(p => <Tag key={p} color="blue">{p}</Tag>)}
            </div>
          </List.Item>
        )}
      />
    </Card>
  );
};

// 配额管理
const QuotaTab: React.FC = () => {
  return (
    <Card>
      <Row gutter={16}>
        <Col span={8}>
          <Card title="Token配额概览">
            <Statistic title="总配额" value={50000} suffix="/日" />
            <Progress percent={75} status="active" />
            <p>已分配: 37,500 / 50,000</p>
          </Card>
        </Col>
        <Col span={16}>
          <Card title="待审批申请">
            <Table
              columns={[
                { title: '用户', dataIndex: 'user' },
                { title: '申请数量', dataIndex: 'amount' },
                { title: '理由', dataIndex: 'reason' },
                { title: '操作', render: () => (
                  <Button.Group>
                    <Button type="primary" size="small">批准</Button>
                    <Button size="small">拒绝</Button>
                  </Button.Group>
                )}
              ]}
              dataSource={[
                { key: '1', user: '张三', amount: 2000, reason: '月度报表生成' }
              ]}
            />
          </Card>
        </Col>
      </Row>
    </Card>
  );
};

// 审计日志
const AuditTab: React.FC = () => {
  return (
    <Card>
      <div className="tab-toolbar">
        <Button>筛选</Button>
        <Button type="primary">导出CSV</Button>
      </div>
      <Table
        columns={[
          { title: '时间', dataIndex: 'time' },
          { title: '用户', dataIndex: 'user' },
          { title: '操作', dataIndex: 'action' },
          { title: '资源', dataIndex: 'resource' },
          { title: '结果', dataIndex: 'result', render: (r: string) => (
            <Tag color={r === '成功' ? 'success' : 'error'}>{r}</Tag>
          )}
        ]}
        dataSource={[
          { key: '1', time: '2026-08-20 10:00:00', user: '张三', action: '创建看板', resource: 'dash_001', result: '成功' },
          { key: '2', time: '2026-08-20 09:30:00', user: '李四', action: '导出数据', resource: 'ds_001', result: '成功' },
          { key: '3', time: '2026-08-20 09:00:00', user: '王五', action: '删除图表', resource: 'chart_003', result: '失败' }
        ]}
      />
    </Card>
  );
};

// 系统设置
const SettingsTab: React.FC = () => {
  return (
    <Card title="系统设置">
      <Alert message="配置中心已实现（M2-01），设置通过配置中心管理" type="info" showIcon />
      <div style={{ marginTop: 16 }}>
        <p><strong>当前配置版本:</strong> v2.1.0</p>
        <p><strong>LLM网关:</strong> 已启用</p>
        <p><strong>审计日志:</strong> 已启用</p>
        <p><strong>自动备份:</strong> 每日00:00</p>
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
      
      <Tabs defaultActiveKey="overview" className="admin-tabs">
        <TabPane tab={<span><DashboardOutlined /> 概览</span>} key="overview">
          <OverviewTab />
        </TabPane>
        <TabPane tab={<span><UserOutlined /> 用户</span>} key="users">
          <UsersTab />
        </TabPane>
        <TabPane tab={<span><TeamOutlined /> 角色</span>} key="roles">
          <RolesTab />
        </TabPane>
        <TabPane tab={<span><WalletOutlined /> 配额</span>} key="quota">
          <QuotaTab />
        </TabPane>
        <TabPane tab={<span><FileTextOutlined /> 审计</span>} key="audit">
          <AuditTab />
        </TabPane>
        <TabPane tab={<span><SettingOutlined /> 设置</span>} key="settings">
          <SettingsTab />
        </TabPane>
      </Tabs>
    </div>
  );
};

export default AdminPage;
