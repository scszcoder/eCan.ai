import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import MainLayout from './components/Layout/MainLayout';
import Dashboard from './pages/Dashboard';
import Tools from './pages/Tools';
import Settings from './pages/Settings';

function App() {
    return (
        <ConfigProvider locale={zhCN}>
            <HashRouter>
                <Routes>
                    <Route path="/" element={<MainLayout />}>
                        <Route index element={<Navigate to="/dashboard" replace />} />
                        <Route path="dashboard" element={<Dashboard />} />
                        <Route path="tools" element={<Tools />} />
                        <Route path="settings" element={<Settings />} />
                    </Route>
                </Routes>
            </HashRouter>
        </ConfigProvider>
    );
}

export default App;
