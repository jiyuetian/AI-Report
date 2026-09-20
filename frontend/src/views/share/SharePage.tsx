/**
 * 分享中心 - M4-04
 * 生成分享链接/二维码/权限设置/有效期/撤销
 */

import React, { useState, useEffect } from 'react';
import {
  Card, Button, Form, Input, Select, DatePicker, Switch,
  Table, Tag, QRCode, Modal, message, Tooltip, Empty,
  Radio, Space, Divider, Popconfirm
} from 'antd';
import {
  ShareAltOutlined, CopyOutlined, QrcodeOutlined,
  EyeOutlined, EditOutlined, DeleteOutlined, LinkOutlined,
  ClockCircleOutlined, LockOutlined, GlobalOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import './SharePage.css';
import { http } from '../../utils/request';

const { Option } = Select;

interface ShareItem {
  id: string;
  share_code: string;
  dashboard_id: string;
  dashboard_name: string;
  permission: 'view' | 'edit';
  expires_at: string;
  status: 'active' | 'revoked' | 'expired';
  access_count: number;
  has_password: boolean;
}

const SharePage: React.FC = () => {
  const [form] = Form.useForm();
  const [shares, setShares] = useState<ShareItem[]>([]);
  const [dashboards, setDashboards] = useState<Array<{ id: string; name: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [qrModalVisible, setQrModalVisible] = useState(false);
  const [currentShare, setCurrentShare] = useState<ShareItem | null>(null);
  const [shareResult, setShareResult] = useState<any>(null);

  // 加载分享列表 + 看板列表（真实后端 API）
  useEffect(() => {
    let mounted = true;
    Promise.all([
      http.get<any>('/shares/my/list'),
      http.get<any>('/dashboards/my', { page: 1, page_size: 100 }),
    ])
      .then(([shareRes, dashRes]) => {
        if (!mounted) return;
        const nameMap: Record<string, string> = {};
        (dashRes.list || []).forEach((d: any) => { nameMap[d.id] = d.name; });
        setDashboards((dashRes.list || []).map((d: any) => ({ id: d.id, name: d.name })));
        setShares((shareRes.shares || []).map((s: any) => ({
          id: s.id,
          share_code: s.share_code,
          dashboard_id: s.dashboard_id,
          dashboard_name: nameMap[s.dashboard_id] || s.dashboard_id,
          permission: s.permission,
          expires_at: s.expires_at || '',
          status: s.status,
          access_count: s.access_count || 0,
          has_password: s.has_password || false,
        })));
      })
      .catch((err) => message.error(`加载分享列表失败: ${err?.message || '网络错误'}`))
      .finally(() => mounted && setLoading(false));
    return () => { mounted = false; };
  }, []);

  // 创建分享（真实后端 API）
  const handleCreateShare = async (values: any) => {
    setLoading(true);
    try {
      const res = await http.post<any>('/shares/create', {
        dashboard_id: values.dashboard_id,
        permission: values.permission,
        expires_days: values.expires_days,
        password: values.has_password ? values.password : null,
      });
      setShareResult(res);
      message.success('分享链接创建成功');
      // 刷新分享列表
      const shareRes = await http.get<any>('/shares/my/list');
      setShares((shareRes.shares || []).map((s: any) => ({
        id: s.id,
        share_code: s.share_code,
        dashboard_id: s.dashboard_id,
        dashboard_name: s.dashboard_id,
        permission: s.permission,
        expires_at: s.expires_at || '',
        status: s.status,
        access_count: s.access_count || 0,
        has_password: s.has_password || false,
      })));
    } catch (err: any) {
      message.error(`创建分享失败: ${err?.message || '网络错误'}`);
    } finally {
      setLoading(false);
    }
  };

  // 复制链接
  const copyLink = (code: string) => {
    const link = `${window.location.origin}/s/${code}`;
    navigator.clipboard.writeText(link);
    message.success('链接已复制到剪贴板');
  };

  // 撤销分享（真实后端 API）
  const handleRevoke = async (id: string) => {
    try {
      await http.post(`/shares/${id}/revoke`);
      setShares(prev => prev.map(s => s.id === id ? { ...s, status: 'revoked' } : s));
      message.success('分享已撤销');
    } catch (err: any) {
      message.error(`撤销失败: ${err?.message || '网络错误'}`);
    }
  };

  // 显示二维码
  const showQRCode = (share: ShareItem) => {
    setCurrentShare(share);
    setQrModalVisible(true);
  };

  const columns: ColumnsType<ShareItem> = [
    {
      title: '看板名称',
      dataIndex: 'dashboard_name',
      key: 'dashboard_name'
    },
    {
      title: '权限',
      dataIndex: 'permission',
      key: 'permission',
      render: (perm: string) => (
        <Tag color={perm === 'edit' ? 'orange' : 'blue'} icon={perm === 'edit' ? <EditOutlined /> : <EyeOutlined />}>
          {perm === 'edit' ? '可编辑' : '仅查看'}
        </Tag>
      )
    },
    {
      title: '访问控制',
      key: 'access',
      render: (_, record) => (
        <Space>
          {record.has_password && <LockOutlined style={{ color: '#faad14' }} />}
          <span>{record.access_count} 次访问</span>
        </Space>
      )
    },
    {
      title: '有效期',
      dataIndex: 'expires_at',
      key: 'expires_at',
      render: (date: string) => (
        <span><ClockCircleOutlined /> {new Date(date).toLocaleDateString()}</span>
      )
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const colors: Record<string, string> = {
          active: 'success',
          revoked: 'default',
          expired: 'error'
        };
        const labels: Record<string, string> = {
          active: '有效',
          revoked: '已撤销',
          expired: '已过期'
        };
        return <Tag color={colors[status]}>{labels[status]}</Tag>;
      }
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Tooltip title="复制链接">
            <Button icon={<CopyOutlined />} onClick={() => copyLink(record.share_code)} />
          </Tooltip>
          <Tooltip title="查看二维码">
            <Button icon={<QrcodeOutlined />} onClick={() => showQRCode(record)} />
          </Tooltip>
          {record.status === 'active' && (
            <Popconfirm
              title="确认撤销此分享？"
              onConfirm={() => handleRevoke(record.id)}
            >
              <Button danger icon={<DeleteOutlined />}>撤销</Button>
            </Popconfirm>
          )}
        </Space>
      )
    }
  ];

  return (
    <div className="share-page">
      <h2 className="page-title"><ShareAltOutlined /> 协同分发</h2>

      <div className="share-content">
        {/* 创建分享 */}
        <Card title="创建分享" className="create-card">
          <Form
            form={form}
            layout="vertical"
            onFinish={handleCreateShare}
            initialValues={{ permission: 'view', expires_days: 7, has_password: false }}
          >
            <Form.Item
              label="选择看板"
              name="dashboard_id"
              rules={[{ required: true, message: '请选择要分享的看板' }]}
            >
              <Select placeholder="选择看板">
                {dashboards.map(d => (
                  <Option key={d.id} value={d.id}>{d.name}</Option>
                ))}
              </Select>
            </Form.Item>

            <Form.Item label="权限设置" name="permission">
              <Radio.Group>
                <Radio.Button value="view"><EyeOutlined /> 仅查看</Radio.Button>
                <Radio.Button value="edit"><EditOutlined /> 可编辑</Radio.Button>
              </Radio.Group>
            </Form.Item>

            <Form.Item label="有效期" name="expires_days">
              <Select>
                <Option value={1}>1天</Option>
                <Option value={7}>7天</Option>
                <Option value={30}>30天</Option>
                <Option value={90}>90天</Option>
              </Select>
            </Form.Item>

            <Form.Item label="密码保护" name="has_password" valuePropName="checked">
              <Switch />
            </Form.Item>

            <Form.Item
              noStyle
              shouldUpdate={(prev, curr) => prev.has_password !== curr.has_password}
            >
              {({ getFieldValue }) =>
                getFieldValue('has_password') ? (
                  <Form.Item
                    label="访问密码"
                    name="password"
                    rules={[{ required: true, message: '请设置访问密码' }]}
                  >
                    <Input.Password placeholder="设置访问密码" />
                  </Form.Item>
                ) : null
              }
            </Form.Item>

            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} icon={<LinkOutlined />}>
                生成分享链接
              </Button>
            </Form.Item>
          </Form>

          {/* 分享结果 */}
          {shareResult && (
            <div className="share-result">
              <Divider />
              <h4>分享链接已生成</h4>
              <div className="share-link-box">
                <Input
                  value={`${window.location.origin}/s/${shareResult.share_code}`}
                  readOnly
                  addonAfter={
                    <Button icon={<CopyOutlined />} onClick={() => copyLink(shareResult.share_code)}>
                      复制
                    </Button>
                  }
                />
              </div>
              <div className="qr-preview">
                <QRCode value={`${window.location.origin}/s/${shareResult.share_code}`} size={128} />
                <p>扫码访问</p>
              </div>
            </div>
          )}
        </Card>

        {/* 分享列表 */}
        <Card title="我的分享" className="list-card">
          {shares.length > 0 ? (
            <Table
              columns={columns}
              dataSource={shares}
              rowKey="id"
              pagination={false}
              size="small"
            />
          ) : (
            <Empty description="暂无分享链接" />
          )}
        </Card>
      </div>

      {/* 二维码弹窗 */}
      <Modal
        title="分享二维码"
        open={qrModalVisible}
        onCancel={() => setQrModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setQrModalVisible(false)}>关闭</Button>
        ]}
      >
        {currentShare && (
          <div className="qr-modal-content">
            <QRCode
              value={`${window.location.origin}/s/${currentShare.share_code}`}
              size={256}
              style={{ margin: '0 auto', display: 'block' }}
            />
            <p style={{ textAlign: 'center', marginTop: 16 }}>
              扫描二维码访问「{currentShare.dashboard_name}」
            </p>
            <p style={{ textAlign: 'center', color: '#999' }}>
              权限: {currentShare.permission === 'edit' ? '可编辑' : '仅查看'}
            </p>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default SharePage;
