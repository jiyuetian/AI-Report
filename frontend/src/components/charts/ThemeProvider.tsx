/**
 * M2-14 双主题图表换肤
 * 明/暗主题切换图表实时换肤
 */

import React, { createContext, useContext, useState, useEffect } from 'react';
import { AppThemeContext } from '../../themeContext';

// 主题配置
export const CHART_THEMES = {
  light: {
    backgroundColor: 'transparent',
    color: ['#5B8FF9', '#5AD8A6', '#F6BD16', '#E86452', '#6DC8EC', '#945FB9', '#FF9845', '#1E9493'],
    textColor: '#333',
    axisLineColor: '#ddd',
    splitLineColor: '#f0f0f0',
  },
  dark: {
    backgroundColor: 'transparent',
    color: ['#5B8FF9', '#5AD8A6', '#F6BD16', '#E86452', '#6DC8EC', '#945FB9', '#FF9845', '#1E9493'],
    textColor: '#ddd',
    axisLineColor: '#444',
    splitLineColor: '#333',
  },
};

// 主题上下文
type ThemeType = 'light' | 'dark';

interface ThemeContextType {
  theme: ThemeType;
  chartTheme: typeof CHART_THEMES.light;
  toggleTheme: () => void;
  setTheme: (theme: ThemeType) => void;
}

const ThemeContext = createContext<ThemeContextType>({
  theme: 'light',
  chartTheme: CHART_THEMES.light,
  toggleTheme: () => {},
  setTheme: () => {},
});

// 主题Provider
export const ChartThemeProvider: React.FC<{children: React.ReactNode}> = ({ children }) => {
  // 跟随全局 AppThemeContext（单一数据源），图表与 AntD 组件同步换肤
  const appCtx = useContext(AppThemeContext);
  const theme: ThemeType = appCtx?.theme || 'light';
  const chartTheme = CHART_THEMES[theme];

  const toggleTheme = () => appCtx?.toggle();
  const setTheme = (newTheme: ThemeType) => appCtx?.setTheme(newTheme);

  return (
    <ThemeContext.Provider value={{ theme, chartTheme, toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

// 使用主题的Hook
export const useChartTheme = () => useContext(ThemeContext);

// 图表主题配置生成器
export const getChartThemeConfig = (theme: ThemeType) => {
  const t = CHART_THEMES[theme];
  
  return {
    // 全局配置
    theme: theme === 'dark' ? 'dark' : 'light',
    
    // 颜色配置
    color: t.color,
    
    // 坐标轴配置
    axis: {
      line: {
        style: {
          stroke: t.axisLineColor,
        },
      },
      label: {
        style: {
          fill: t.textColor,
        },
      },
      grid: {
        line: {
          style: {
            stroke: t.splitLineColor,
          },
        },
      },
    },
    
    // 图例配置
    legend: {
      itemName: {
        style: {
          fill: t.textColor,
        },
      },
    },
    
    // 提示框配置
    tooltip: {
      domStyles: {
        'g2-tooltip': {
          backgroundColor: theme === 'dark' ? '#333' : '#fff',
          color: t.textColor,
          boxShadow: theme === 'dark' ? '0 2px 8px rgba(0,0,0,0.5)' : '0 2px 8px rgba(0,0,0,0.15)',
        },
      },
    },
    
    // 标签配置
    label: {
      style: {
        fill: t.textColor,
      },
    },
  };
};

export default ThemeContext;