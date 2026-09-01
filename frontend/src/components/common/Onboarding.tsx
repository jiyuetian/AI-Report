/**
 * 新手引导 - M4-08 打磨包
 */

import React, { useState, useEffect } from 'react';
import { Tour, Button, message } from 'antd';
import type { TourProps } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';

interface OnboardingProps {
  steps: TourProps['steps'];
  storageKey?: string;
}

const Onboarding: React.FC<OnboardingProps> = ({ 
  steps, 
  storageKey = 'onboarding_completed' 
}) => {
  const [open, setOpen] = useState(false);
  const [isNewUser, setIsNewUser] = useState(false);

  useEffect(() => {
    // 检查是否已完成新手引导
    const completed = localStorage.getItem(storageKey);
    if (!completed) {
      setIsNewUser(true);
      // 延迟显示，等页面加载完成
      setTimeout(() => setOpen(true), 1000);
    }
  }, [storageKey]);

  const handleComplete = () => {
    localStorage.setItem(storageKey, 'true');
    setOpen(false);
    setIsNewUser(false);
    message.success('已完成新手引导！');
  };

  const handleRestart = () => {
    setOpen(true);
  };

  return (
    <>
      {isNewUser && (
        <Button
          type="primary"
          icon={<QuestionCircleOutlined />}
          onClick={handleRestart}
          style={{ position: 'fixed', right: 24, bottom: 24, zIndex: 1000 }}
        >
          新手引导
        </Button>
      )}
      
      <Tour
        open={open}
        onClose={handleComplete}
        steps={steps}
        indicatorsRender={(current, total) => (
          <span>
            {current + 1} / {total}
          </span>
        )}
      />
    </>
  );
};

export default Onboarding;
