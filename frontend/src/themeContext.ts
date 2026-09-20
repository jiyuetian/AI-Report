/**
 * 全局主题上下文（明/暗）
 * 单一数据源：App.tsx 持有状态，ConfigProvider 与图表 ThemeProvider 都跟随它。
 */
import { createContext } from 'react';

export type AppTheme = 'light' | 'dark';

export interface AppThemeCtx {
  theme: AppTheme;
  toggle: () => void;
  setTheme: (t: AppTheme) => void;
}

export const AppThemeContext = createContext<AppThemeCtx>({
  theme: 'light',
  toggle: () => {},
  setTheme: () => {},
});
