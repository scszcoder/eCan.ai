import React from 'react';
import { Card, Row, Col, Statistic, Typography } from 'antd';
import { CarOutlined, TeamOutlined, RobotOutlined, ScheduleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const { Title } = Typography;

const Dashboard: React.FC = () => {
  const { t } = useTranslation();

  return (
    <div>
      <Title level={2}>{t('pages.dashboard.title')}</Title>
      <Title level={4}>{t('pages.dashboard.welcome')}</Title>
      
      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Card>
            <Statistic
              title={t('pages.dashboard.overview')}
              value={12}
              prefix={<CarOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title={t('pages.dashboard.statistics')}
              value={8}
              prefix={<TeamOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title={t('pages.dashboard.recentActivities')}
              value={24}
              prefix={<RobotOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title={t('pages.dashboard.quickActions')}
              value={15}
              prefix={<ScheduleOutlined />}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default Dashboard; 