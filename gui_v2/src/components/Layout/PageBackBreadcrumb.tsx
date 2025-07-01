import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Button, Breadcrumb } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const PageBackBreadcrumb: React.FC = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const { t } = useTranslation();
    const path = location.pathname;
    // 匹配 /xxx/yyy/zzz... 至少两级
    const segments = path.split('/').filter(Boolean);
    if (segments.length < 2) return null;
    // 只在二级及以上页面显示
    const parentPath = '/' + segments.slice(0, -1).join('/');
    const items = segments.map((seg, idx) => {
        const segPath = '/' + segments.slice(0, idx + 1).join('/');
        const isLast = idx === segments.length - 1;
        let label = t(`breadcrumb.${seg}`);
        if (label === `breadcrumb.${seg}`) label = decodeURIComponent(seg);
        return {
            key: segPath,
            title: isLast ? (
                <span>{label}</span>
            ) : (
                <span style={{ cursor: 'pointer', color: 'var(--ant-primary-color)' }} onClick={() => navigate(segPath)}>{label}</span>
            )
        };
    });
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, position: 'absolute', top: 0, left: 0, zIndex: 10, padding: '8px 16px' }}>
            <Button
                type="text"
                icon={<ArrowLeftOutlined />}
                onClick={() => navigate(parentPath)}
                style={{ color: 'var(--ant-primary-color)', paddingLeft: 0 }}
            >
                {t('common.back', '返回')}
            </Button>
            <Breadcrumb items={items} />
        </div>
    );
};

export default PageBackBreadcrumb; 