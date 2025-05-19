import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import MainLayout from './components/Layout/MainLayout';
import Login from './pages/Login';
import Chat from './pages/Chat';
import Schedule from './pages/Schedule';
import Skills from './pages/Skills';
import Agents from './pages/Agents';
import Vehicles from './pages/Vehicles';
import Settings from './pages/Settings';
import Analytics from './pages/Analytics';
import Apps from './pages/Apps';
import Tools from './pages/Tools';

const App: React.FC = () => {
    return (
        <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <Routes>
                <Route path="/login" element={<Login />} />
                <Route path="/main" element={<MainLayout />}>
                    <Route index element={<Navigate to="/main/chat" replace />} />
                    <Route path="chat" element={<Chat />} />
                    <Route path="schedule" element={<Schedule />} />
                    <Route path="skills" element={<Skills />} />
                    <Route path="agents" element={<Agents />} />
                    <Route path="vehicles" element={<Vehicles />} />
                    <Route path="settings" element={<Settings />} />
                    <Route path="analytics" element={<Analytics />} />
                    <Route path="apps" element={<Apps />} />
                    <Route path="tools" element={<Tools />} />
                </Route>
                <Route path="*" element={<Navigate to="/login" replace />} />
            </Routes>
        </Router>
    );
};

export default App;
