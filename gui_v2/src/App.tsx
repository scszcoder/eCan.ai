import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import { LanguageProvider } from './contexts/LanguageContext';
import './i18n';
import Login from './pages/Login';
import MainLayout from './components/Layout/MainLayout';
import Vehicles from './pages/Vehicles';
import Schedule from './pages/Schedule';
import Chat from './pages/Chat';
import Settings from './pages/Settings';
import Skills from './pages/Skills';
import SkillEditor from './pages/SkillEditor';
import Agents from './pages/Agents';
import Analytics from './pages/Analytics';
import Apps from './pages/Apps';
import Tools from './pages/Tools';

const App: React.FC = () => {
    return (
        <LanguageProvider>
            <ConfigProvider>
                <Router>
                    <Routes>
                        <Route path="/login" element={<Login />} />
                        <Route path="/main" element={<MainLayout />}>
                            <Route index element={<Navigate to="chat" replace />} />
                            <Route path="vehicles" element={<Vehicles />} />
                            <Route path="schedule" element={<Schedule />} />
                            <Route path="chat" element={<Chat />} />
                            <Route path="settings" element={<Settings />} />
                            <Route path="skills" element={<Skills />} />
                            <Route path="skill-editor" element={<SkillEditor />} />
                            <Route path="agents" element={<Agents />} />
                            <Route path="analytics" element={<Analytics />} />
                            <Route path="apps" element={<Apps />} />
                            <Route path="tools" element={<Tools />} />
                        </Route>
                        <Route path="*" element={<Navigate to="/login" replace />} />
                    </Routes>
                </Router>
            </ConfigProvider>
        </LanguageProvider>
    );
};

export default App;
