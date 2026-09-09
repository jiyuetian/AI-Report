/**
 * 我的看板 - M4-06
 * 列表/检索/筛选/详情抽屉/删除二次确认/数据源更新提醒/空状态
 */

import React, { useState, useEffect } from 'react';
import {
  Card, List, Input, Button, Tag, Badge, Empty, Spin,
  Drawer, Modal, Form, message, Popconfirm, Statistic, Row, Col,
  Dropdown, Tooltip
} from 'antd';
import {
  PlusOutlined, SearchOutlined, FilterOutlined,
  EyeOutlined, EditOutlined, DeleteOutlined,
  MoreOutlined, FileOutlined, CheckCircleOutlined,
  ExclamationCircleOutlined, ClockCircleOutlined,
  BarChartOutlined, DatabaseOutlined, ArrowRightOutlined
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { http } from '../../utils/request';
import './DashboardListPage.css';

const { Search } = Input;

// 看板数据类型
interface Dashboard {
  id: string;
  name: string;
  description?: string;
  status: 'draft' | 'published' | 'archived';
  score?: number;
  passed?: boolean;
  dataset_count: number;
  update_reminder: {
    has_update: boolean;
    message?: string;
  };
  created_at: string;
  updated_at: string;
}

// 统计数据
interface DashboardStats {
  total: number;
  by_status: {
    draft: number;
    published: number;
    archived: number;
  };
  today_created: number;
}

const DashboardListPage: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [dashboards, setDashboards] = useState<Dashboard[]>([]);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedDashboard, setSelectedDashboard] = useState<Dashboard | null>(null);
  const [detailDrawerOpen, setDetailDrawerOpen] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [confirmName, setConfirmName] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // 加载看板列表与统计（真实后端 API）
  useEffect(() => {
    let mounted = true;
    Promise.all([
      http.get<any>('/dashboards/my', { page: 1, page_size: 100 }),
      http.get<any>('/dashboards/stats/overview'),
    ])
      .then(([listRes, statsRes]) => {
        if (!mounted) return;
        setDashboards(listRes.list ?? []);
        setStats({
          total: statsRes.total ?? 0,
          by_status: statsRes.by_status ?? { draft: 0, published: 0, archived: 0 },
          today_created: statsRes.today_created ?? 0,
        });
      })
      .catch((err) => {
        if (!mounted) return;
        message.error(`加载看板失败: ${err?.message || '网络错误'}`);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => { mounted = false; };
  }, []);

  // 状态标签渲染
  const renderStatusTag = (status: string) => {
    const config: Record<string, { color: string; text: string; icon: React.ReactNode }> = {
      draft: { color: 'default', text: '草稿', icon: <FileOutlined /> },
      published: { color: 'success', text: '已发布', icon: <CheckCircleOutlined /> },
      archived: { color: 'warning', text: '已归档', icon: <ClockCircleOutlined /> }
    };
    const cfg = config[status] || config.draft;
    return <Tag color={cfg.color} icon={cfg.icon}>{cfg.text}</Tag>;
  };

  // 过滤后的列表
  const filteredDashboards = dashboards.filter(d => {
    const matchSearch = !searchText || 
      d.name.toLowerCase().includes(searchText.toLowerCase()) ||
      (d.description && d.description.toLowerCase().includes(searchText.toLowerCase()));
    const matchStatus = statusFilter === 'all' || d.status === statusFilter;
    return matchSearch && matchStatus;
  });

  // 打开详情抽屉
  const openDetail = (dashboard: Dashboard) => {
    setSelectedDashboard(dashboard);
    setDetailDrawerOpen(true);
  };

  // 打开删除确认
  const openDeleteModal = (dashboard: Dashboard) => {
    setDeletingId(dashboard.id);
    setConfirmName('');
    setDeleteModalOpen(true);
  };

  // 执行删除
  const handleDelete = async () => {
    const dashboard = dashboards.find(d => d.id === deletingId);
    if (!dashboard) return;

    // 验证确认名称
    if (confirmName !== dashboard.name) {
      message.error(`确认名称不匹配，请输入: ${dashboard.name}`);
      return;
    }

    try {
      await http.delete(`/dashboards/${dashboard.id}`, { confirm_name: confirmName });
      setDashboards(prev => prev.filter(d => d.id !== deletingId));
      message.success(`看板 "${dashboard.name}" 已删除`);
    } catch (err: any) {
      message.error(`删除失败: ${err?.message || '网络错误'}`);
    } finally {
      setDeleteModalOpen(false);
      setDeletingId(null);
    }
  };

  // 操作菜单（AntD5 items API）
  const actionMenu = (dashboard: Dashboard) => ({
    items: [
      { key: 'view', icon: <EyeOutlined />, label: '查看看板' },
      { key: 'edit', icon: <EditOutlined />, label: '编辑' },
      { key: 'detail', icon: <BarChartOutlined />, label: '详情' },
      { type: 'divider' as const },
      { key: 'delete', icon: <DeleteOutlined />, label: '删除', danger: true },
    ],
    onClick: (info: any) => {
      if (info.domEvent) info.domEvent.stopPropagation();
      if (info.key === 'view') navigate(`/dashboard?id=${dashboard.id}`)
      else if (info.key === 'edit') navigate(`/dashboard?id=${dashboard.id}&edit=true`)
      else if (info.key === 'detail') openDetail(dashboard)
      else if (info.key === 'delete') openDeleteModal(dashboard)
    },
  })

  if (loading) {
    return (
      <div className="dashboard-list-loading">
        <Spin size="large" tip="加载看板列表..." />
      </div>
    );
  }

  return (
    <div className="dashboard-list-page">
      {/* 统计卡片 */}
      {stats && (
        <Row gutter={16} className="stats-row">
          <Col span={6}>
            <Card className="stat-card">
              <Statistic title="全部看板" value={stats.total} prefix={<BarChartOutlined />} />
            </Card>
          </Col>
          <Col span={6}>
            <Card className="stat-card draft">
              <Statistic title="草稿" value={stats.by_status.draft} />
            </Card>
          </Col>
          <Col span={6}>
            <Card className="stat-card published">
              <Statistic title="已发布" value={stats.by_status.published} />
            </Card>
          </Col>
          <Col span={6}>
            <Card className="stat-card today">
              <Statistic title="今日创建" value={stats.today_created} />
            </Card>
          </Col>
        </Row>
      )}

      {/* 操作栏 */}
      <Card className="toolbar-card" size="small">
        <div className="toolbar-content">
          <Search
            placeholder="搜索看板名称..."
            allowClear
            onSearch={setSearchText}
            style={{ width: 300 }}
            prefix={<SearchOutlined />}
          />
          
          <div className="filter-group">
            <span className="filter-label">状态筛选:</span>
            <Button 
              type={statusFilter === 'all' ? 'primary' : 'default'}
              onClick={() => setStatusFilter('all')}
            >
              全部
            </Button>
            <Button 
              type={statusFilter === 'draft' ? 'primary' : 'default'}
              onClick={() => setStatusFilter('draft')}
            >
              草稿
            </Button>
            <Button 
              type={statusFilter === 'published' ? 'primary' : 'default'}
              onClick={() => setStatusFilter('published')}
            >
              已发布
            </Button>
          </div>

          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/dashboard')}>
            新建看板
          </Button>
        </div>
      </Card>

      {/* 看板列表 */}
      <Card className="list-card">
        {filteredDashboards.length > 0 ? (
          <List
            dataSource={filteredDashboards}
            renderItem={item => (
              <List.Item
                className="dashboard-list-item"
                onClick={() => navigate(`/dashboard?id=${item.id}`)}
                style={{ cursor: 'pointer' }}
                actions={[
                  <Dropdown menu={actionMenu(item)} placement="bottomRight" trigger={['click']}>
                    <Button icon={<MoreOutlined />} onClick={(e) => e.stopPropagation()} />
                  </Dropdown>
                ]}
              >
                <List.Item.Meta
                  title={
                    <div className="item-title">
                      <span className="name">{item.name}</span>
                      {renderStatusTag(item.status)}
                      {item.update_reminder?.has_update && (
                        <Tooltip title={item.update_reminder.message}>
                          <Badge dot color="red">
                            <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />
                          </Badge>
                        </Tooltip>
                      )}
                    </div>
                  }
                  description={
                    <div className="item-desc">
                      <p>{item.description || '暂无描述'}</p>
                      <div className="item-meta">
                        <span><DatabaseOutlined /> {item.dataset_count} 个数据源</span>
                        {item.score !== undefined && (
                          <Tag color={item.passed ? 'success' : 'warning'}>
                            评分: {item.score}
                          </Tag>
                        )}
                        <span className="update-time">更新于 {new Date(item.updated_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                  }
                />
              </List.Item>
            )}
          />
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="暂无看板"
          >
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/dashboard')}>
              创建第一个看板
            </Button>
          </Empty>
        )}
      </Card>

      {/* 详情抽屉 */}
      <Drawer
        title="看板详情"
        width={480}
        open={detailDrawerOpen}
        onClose={() => setDetailDrawerOpen(false)}
      >
        {selectedDashboard && (
          <div className="detail-content">
            <h3>{selectedDashboard.name}</h3>
            <p className="detail-desc">{selectedDashboard.description || '暂无描述'}</p>
            
            <div className="detail-section">
              <h4>基本信息</h4>
              <p><label>状态:</label> {renderStatusTag(selectedDashboard.status)}</p>
              <p><label>数据源:</label> {selectedDashboard.dataset_count} 个</p>
              {selectedDashboard.score && (
                <p><label>评分:</label> <Tag color={selectedDashboard.passed ? 'success' : 'warning'}>{selectedDashboard.score}</Tag></p>
              )}
            </div>

            {selectedDashboard.update_reminder?.has_update && (
              <div className="update-alert">
                <ExclamationCircleOutlined />
                <span>{selectedDashboard.update_reminder.message}</span>
              </div>
            )}

            <div className="detail-actions">
              <Button type="primary" block icon={<ArrowRightOutlined />} onClick={() => navigate(`/dashboard?id=${selectedDashboard.id}`)}>
                进入看板
              </Button>
            </div>
          </div>
        )}
      </Drawer>

      {/* 删除确认弹窗 */}
      <Modal
        title="删除看板"
        open={deleteModalOpen}
        onCancel={() => setDeleteModalOpen(false)}
        footer={null}
      >
        {deletingId && (
          <div className="delete-confirm">
            <p className="warning-text">
              <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />
              此操作不可恢复，请谨慎操作！
            </p>
            <p>请输入看板名称以确认删除：</p>
            <Input
              placeholder="输入看板名称"
              value={confirmName}
              onChange={e => setConfirmName(e.target.value)}
              style={{ marginBottom: 16 }}
            />
            <div className="delete-actions">
              <Button onClick={() => setDeleteModalOpen(false)}>取消</Button>
              <Button danger type="primary" onClick={handleDelete}>
                确认删除
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default DashboardListPage;
