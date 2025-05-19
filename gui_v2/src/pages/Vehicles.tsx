import React, { useState } from 'react';
import { Layout, List, Avatar, Select, Card, Typography, Progress, Row, Col } from 'antd';
import { CarOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';

const { Content } = Layout;
const { Text } = Typography;

const VehiclesContainer = styled(Layout)`
  height: calc(100vh - 112px);
`;

const VehicleList = styled.div`
  width: 25%;
  border-right: 1px solid #f0f0f0;
  overflow-y: auto;
`;

const VehicleMain = styled.div`
  width: 75%;
  display: flex;
  flex-direction: column;
`;

const VehicleDetails = styled.div`
  flex: 1;
  padding: 20px;
  overflow-y: auto;
`;

const VehicleAgents = styled.div`
  flex: 1;
  padding: 20px;
  border-top: 1px solid #f0f0f0;
`;

const SortSelect = styled(Select)`
  width: 100%;
  margin-bottom: 16px;
`;

const Vehicles: React.FC = () => {
  const [vehicles] = useState([
    {
      id: 1,
      name: 'Vehicle 1',
      ip: '192.168.1.1',
      capacity: 100,
      vacancy: 80,
    },
    {
      id: 2,
      name: 'Vehicle 2',
      ip: '192.168.1.2',
      capacity: 200,
      vacancy: 150,
    },
  ]);

  const [selectedVehicle] = useState(vehicles[0]);

  return (
    <VehiclesContainer>
      <VehicleList>
        <SortSelect
          defaultValue="name"
          options={[
            { value: 'name', label: 'By Name' },
            { value: 'ip', label: 'By IP' },
            { value: 'capacity', label: 'By Capacity' },
            { value: 'vacancy', label: 'By Vacancy Level' },
          ]}
        />
        <List
          dataSource={vehicles}
          renderItem={item => (
            <List.Item>
              <List.Item.Meta
                avatar={<Avatar icon={<CarOutlined />} />}
                title={item.name}
                description={`IP: ${item.ip}`}
              />
            </List.Item>
          )}
        />
      </VehicleList>
      <VehicleMain>
        <VehicleDetails>
          <Card>
            <Row gutter={16}>
              <Col span={8}>
                <Avatar size={64} icon={<CarOutlined />} />
              </Col>
              <Col span={16}>
                <Text strong>Name: </Text>
                <Text>{selectedVehicle.name}</Text>
                <br />
                <Text strong>IP Address: </Text>
                <Text>{selectedVehicle.ip}</Text>
                <br />
                <Text strong>Role: </Text>
                <Text>Worker</Text>
                <br />
                <Text strong>Capacity: </Text>
                <Text>{selectedVehicle.capacity}</Text>
                <br />
                <Text strong>Vacancy: </Text>
                <Text>{selectedVehicle.vacancy}</Text>
                <br />
                <Text strong>Hardware: </Text>
                <br />
                <Text>CPU: Intel i7</Text>
                <br />
                <Text>Memory: 16GB</Text>
                <br />
                <Text>Storage: 1TB SSD</Text>
                <br />
                <Text strong>OS: </Text>
                <Text>Ubuntu 20.04 LTS</Text>
              </Col>
            </Row>
          </Card>
        </VehicleDetails>
        <VehicleAgents>
          <Card title="Assigned Agents">
            <List
              dataSource={[
                { id: 1, name: 'Agent 1' },
                { id: 2, name: 'Agent 2' },
                { id: 3, name: 'Agent 3' },
              ]}
              renderItem={item => (
                <List.Item>
                  <List.Item.Meta
                    avatar={<Avatar>{item.name[0]}</Avatar>}
                    title={item.name}
                    description={`ID: ${item.id}`}
                  />
                </List.Item>
              )}
            />
          </Card>
          <Card title="Resource Utilization (Past 30 Days)" style={{ marginTop: 16 }}>
            <Row gutter={16}>
              <Col span={8}>
                <Text>CPU Utilization</Text>
                <Progress percent={75} />
              </Col>
              <Col span={8}>
                <Text>Memory Utilization</Text>
                <Progress percent={60} />
              </Col>
              <Col span={8}>
                <Text>Time Utilization</Text>
                <Progress percent={85} />
              </Col>
            </Row>
          </Card>
        </VehicleAgents>
      </VehicleMain>
    </VehiclesContainer>
  );
};

export default Vehicles; 