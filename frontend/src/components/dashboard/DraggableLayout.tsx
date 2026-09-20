/**
 * 拖拽布局 - M4-08 打磨包
 * 使用 react-grid-layout 实现看板拖拽布局
 */

import React, { useState, useCallback } from 'react';
import { Responsive, WidthProvider } from 'react-grid-layout';
import { Card, Button, Tooltip, message } from 'antd';
import {
  DragOutlined, LockOutlined, UnlockOutlined,
  SaveOutlined, ReloadOutlined
} from '@ant-design/icons';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import './DraggableLayout.css';

const ResponsiveGridLayout = WidthProvider(Responsive);

interface LayoutItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minW?: number;
  minH?: number;
  maxW?: number;
  maxH?: number;
  static?: boolean;
}

interface ChartWidget {
  id: string;
  title: string;
  type: string;
  content: React.ReactNode;
}

interface DraggableLayoutProps {
  widgets: ChartWidget[];
  onLayoutChange?: (layout: LayoutItem[]) => void;
  onSave?: (layout: LayoutItem[]) => void;
}

const DraggableLayout: React.FC<DraggableLayoutProps> = ({
  widgets,
  onLayoutChange,
  onSave
}) => {
  const [isDraggable, setIsDraggable] = useState(false);
  const [layouts, setLayouts] = useState<{ lg: LayoutItem[] }>({
    lg: widgets.map((w, i) => ({
      i: w.id,
      x: (i % 2) * 6,
      y: Math.floor(i / 2) * 4,
      w: 6,
      h: 4,
      minW: 3,
      minH: 2
    }))
  });

  const handleLayoutChange = useCallback((currentLayout: LayoutItem[]) => {
    setLayouts({ lg: currentLayout });
    onLayoutChange?.(currentLayout);
  }, [onLayoutChange]);

  const handleSave = () => {
    onSave?.(layouts.lg);
    message.success('布局已保存');
    setIsDraggable(false);
  };

  const toggleDraggable = () => {
    setIsDraggable(!isDraggable);
    if (!isDraggable) {
      message.info('拖拽模式已开启，可拖动调整布局');
    } else {
      message.info('拖拽模式已关闭');
    }
  };

  const resetLayout = () => {
    const defaultLayout = widgets.map((w, i) => ({
      i: w.id,
      x: (i % 2) * 6,
      y: Math.floor(i / 2) * 4,
      w: 6,
      h: 4,
      minW: 3,
      minH: 2
    }));
    setLayouts({ lg: defaultLayout });
    message.success('布局已重置');
  };

  return (
    <div className="draggable-layout">
      <div className="layout-toolbar">
        <Tooltip title={isDraggable ? '关闭拖拽' : '开启拖拽'}>
          <Button
            type={isDraggable ? 'primary' : 'default'}
            icon={isDraggable ? <UnlockOutlined /> : <LockOutlined />}
            onClick={toggleDraggable}
          >
            {isDraggable ? '编辑中' : '编辑布局'}
          </Button>
        </Tooltip>
        
        {isDraggable && (
          <>
            <Tooltip title="保存布局">
              <Button icon={<SaveOutlined />} onClick={handleSave}>
                保存
              </Button>
            </Tooltip>
            <Tooltip title="重置布局">
              <Button icon={<ReloadOutlined />} onClick={resetLayout}>
                重置
              </Button>
            </Tooltip>
          </>
        )}
      </div>

      <ResponsiveGridLayout
        className="layout"
        layouts={layouts}
        breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 }}
        cols={{ lg: 12, md: 10, sm: 6, xs: 4, xxs: 2 }}
        rowHeight={60}
        isDraggable={isDraggable}
        isResizable={isDraggable}
        onLayoutChange={handleLayoutChange}
        margin={[16, 16]}
      >
        {widgets.map(widget => (
          <div key={widget.id} className={`layout-item ${isDraggable ? 'draggable' : ''}`}>
            <Card
              title={
                <div className="widget-header">
                  <span>{widget.title}</span>
                  {isDraggable && <DragOutlined className="drag-handle" />}
                </div>
              }
              className="widget-card"
              extra={<Tag color="blue">{widget.type}</Tag>}
            >
              <div className="widget-content">
                {widget.content}
              </div>
            </Card>
          </div>
        ))}
      </ResponsiveGridLayout>
    </div>
  );
};

// 引入 Tag
import { Tag } from 'antd';

export default DraggableLayout;
