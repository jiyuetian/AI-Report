/**
 * Prompt 中心 - 管理中心
 * 以卡片网格管理九大提示词板块：编辑 / 启停 / 恢复默认 / 版本
 * 运行时 prompt_loader 读这里的"启用覆盖"；内置种子为 prompts/*.md
 */
import React, { useEffect, useState } from 'react';
import {
  Card, Row, Col, Tag, Switch, Button, Modal, Input, Space, Alert, Spin, Empty, Tooltip
} from 'antd';
import {
  EditOutlined, RollbackOutlined, ThunderboltOutlined,
  BranchesOutlined, CheckCircleOutlined, ClockCircleOutlined, SyncOutlined
} from '@ant-design/icons';
import { message } from 'antd';
import { http } from '../../utils/request';
import './PromptCenter.css';

const { TextArea, Search: _skip } = Input;

interface PromptGroup {
  key: string;
  title: string;
  description: string;
  category: string;
  content: string;
  enabled: boolean;
  version: number;
  is_builtin: boolean;
  remark: string;
  updated_by: string;
  updated_at: string;
}

const PromptCenter: React.FC = () => {
  const [groups, setGroups] = useState<PromptGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<PromptGroup | null>(null);
  const [content, setContent] = useState('');
  const [remark, setRemark] = useState('');
  const [enabled, setEnabled] = useState(true);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState<PromptGroup | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await http.get<any>('/admin/prompts');
      setGroups(res?.groups ?? []);
    } catch (e: any) {
      message.error('加载提示词列表失败：' + (e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const openEdit = (g: PromptGroup) => {
    setEditing(g);
    setContent(g.content);
    setRemark(g.remark);
    setEnabled(g.enabled);
  };

  const doSave = async () => {
    if (!editing) return;
    if (!content || !content.trim()) {
      message.warning('提示词正文不能为空');
      return;
    }
    setSaving(true);
    try {
      const res = await http.put<any>(`/admin/prompts/${editing.key}`, {
        content, enabled, remark: remark || ''
      });
      message.success(`已保存「${editing.title}」，下次报告生成立即生效`);
      setEditing(null);
      await load();
    } catch (e: any) {
      message.error('保存失败：' + (e?.message || e));
    } finally {
      setSaving(false);
    }
  };

  const toggleEnable = async (g: PromptGroup, value: boolean) => {
    try {
      setGroups(prev => prev.map(x => x.key === g.key ? { ...x, enabled: value } : x));
      await http.put<any>(`/admin/prompts/${g.key}`, {
        content: g.content, enabled: value, remark: g.remark || (value ? '' : '停用该板块')
      });
      message.success(value ? `已启用「${g.title}」` : `已停用「${g.title}」（回退为内置默认）`);
      await load();
    } catch (e: any) {
      message.error('操作失败：' + (e?.message || e));
      await load();
    }
  };

  const doReset = async () => {
    if (!resetting) return;
    try {
      await http.post<any>(`/admin/prompts/${resetting.key}/reset`);
      message.success(`已恢复「${resetting.title}」为内置默认`);
      setResetting(null);
      await load();
    } catch (e: any) {
      message.error('恢复失败：' + (e?.message || e));
    }
  };

  const byCategory: Record<string, PromptGroup[]> = {};
  groups.forEach(g => { (byCategory[g.category] = byCategory[g.category] || []).push(g); });

  return (
    <div className="prompt-center">
      <Alert
        type="info"
        showIcon
        className="pc-banner"
        message="Prompt 中心：管理各 AI 加工节点的软约束提示词。编辑保存后下一次报告生成立即生效，无需重启；内置种子保存在 backend/app/core/prompts/*.md，数据准确性红线由六层血缘与规则引擎在代码层保证，提示词仅作业务口径与表达约束。"
      />

      {loading && groups.length === 0 ? (
        <div className="pc-empty"><Spin tip="加载中" /></div>
      ) : groups.length === 0 ? (
        <Empty description="暂无提示词配置" />
      ) : (
        Object.entries(byCategory).map(([cat, list]) => (
          <div className="pc-cat" key={cat}>
            <h4 className="pc-cat-title"><BranchesOutlined /> {cat} <span>{list.length}</span></h4>
            <Row gutter={[16, 16]}>
              {list.map(g => (
                <Col xs={24} md={12} xl={8} key={g.key}>
                  <Card size="small" className="pc-card" bordered>
                    <div className="pc-card-head">
                      <span className="pc-title">
                        <ThunderboltOutlined style={{ color: '#2f6fed' }} /> {g.title}
                      </span>
                      <Tag color={g.enabled ? 'blue' : 'default'}>{g.enabled ? '启用' : '停用'}</Tag>
                      <Tag color={g.is_builtin ? 'green' : 'orange'}>{g.is_builtin ? '内置' : '已自定义'}</Tag>
                    </div>
                    <p className="pc-desc">{g.description}</p>
                    <div className="pc-meta">
                      <span><ClockCircleOutlined /> v{g.version}</span>
                      <span>{g.updated_by || 'system'}</span>
                      {g.remark && <span className="pc-remark" title={g.remark}>{g.remark}</span>}
                    </div>
                    <div className="pc-card-foot">
                      <span className="pc-enable">
                        <Switch size="small" checked={g.enabled} onChange={v => toggleEnable(g, v)} />
                        启用
                      </span>
                      <Space>
                        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(g)}>编辑</Button>
                        {!g.is_builtin && (
                          <Tooltip title="恢复为内置默认文案">
                            <Button size="small" icon={<RollbackOutlined />} onClick={() => setResetting(g)}>恢复默认</Button>
                          </Tooltip>
                        )}
                      </Space>
                    </div>
                  </Card>
                </Col>
              ))}
            </Row>
          </div>
        ))
      )}

      {/* 编辑弹窗 */}
      <Modal
        title={`编辑提示词 · ${editing?.title ?? ''}（${editing?.key ?? ''}）`}
        open={!!editing}
        width={Math.min(860, window.innerWidth * 0.9)}
        centered
        maskClosable={false}
        okText="保存"
        confirmLoading={saving}
        onOk={doSave}
        onCancel={() => setEditing(null)}
        getContainer={false}
      >
        <div className="pc-form">
          <div className="pc-form-row">
            <span>启用该板块</span>
            <Switch checked={enabled} onChange={setEnabled} />
            <Tag color={enabled ? 'blue' : 'default'} style={{ marginLeft: 8 }}>{enabled ? '参与装配' : '停用（回退内置）'}</Tag>
          </div>
          <TextArea
            value={content}
            onChange={e => setContent(e.target.value)}
            autoSize={{ minRows: 14, maxRows: 22 }}
            className="pc-monaco"
            spellCheck={false}
          />
          <Input
            placeholder="修改备注（便于审计，如：补充金额口径说明）"
            value={remark}
            onChange={e => setRemark(e.target.value)}
            style={{ marginTop: 10 }}
          />
        </div>
      </Modal>

      {/* 恢复默认确认 */}
      <Modal
        title="恢复默认"
        open={!!resetting}
        centered
        okText="确认恢复"
        okButtonProps={{ danger: true }}
        onOk={doReset}
        onCancel={() => setResetting(null)}
        getContainer={false}
      >
        <p>确认将「<strong>{resetting?.title}</strong>」恢复为内置默认文案吗？当前自定义内容将被覆盖清除。</p>
      </Modal>
    </div>
  );
};

export default PromptCenter;