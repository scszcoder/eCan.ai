import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import enUS from 'antd/locale/en_US';
import { useTranslation, I18nextProvider } from 'react-i18next';
import i18n from './i18n';
import { routes } from './routes';

const App: React.FC = () => {
  const { i18n: i18nInstance } = useTranslation();
  const currentLocale = i18nInstance.language === 'zh-CN' ? zhCN : enUS;

  return (
    <I18nextProvider i18n={i18n}>
      <ConfigProvider locale={currentLocale}>
        <Router>
          <Routes>
            {routes.map((route) => (
              <Route
                key={route.path}
                path={route.path}
                element={route.element}
              />
            ))}
          </Routes>
        </Router>
      </ConfigProvider>
    </I18nextProvider>
  );
};

export default App;
