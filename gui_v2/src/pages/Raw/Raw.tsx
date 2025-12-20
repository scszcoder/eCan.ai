import React, { useState, useCallback, useEffect } from 'react';
import { Layout, List, Table, Input, Button, Select, Space } from 'antd';
import { SearchOutlined, SaveOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { IPCAPI } from '@/services/ipc/api';

const { Content } = Layout;
const { TextArea } = Input;

const RawContainer = styled(Layout)`
  height: calc(100vh - 112px);
`;

const TableList = styled.div`
  width: 25%;
  border-right: 1px solid #f0f0f0;
  overflow-y: auto;
`;

const TableMain = styled.div`
  width: 75%;
  display: flex;
  flex-direction: column;
`;

const TableContent = styled.div`
  flex: 3;
  padding: 20px;
  overflow-x: hidden;
  overflow-y: auto;
`;

const QueryArea = styled.div`
  flex: 1;
  padding: 20px;
  border-top: 1px solid #f0f0f0;
`;

const ActionBar = styled.div`
  flex: 1;
  padding: 20px;
  border-top: 1px solid #f0f0f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
`;

const Raw: React.FC = () => {
  const [tables] = useState([
    'users',
    'agents',
    'missions',
    'skills',
    'vehicles',
  ]);

  const [selectedTable] = useState(tables[0]);

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      fixed: 'left' as const,
    },
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
      fixed: 'left' as const,
    },
    {
      title: 'Type',
      dataIndex: 'type',
      key: 'type',
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
    },
    {
      title: 'Created At',
      dataIndex: 'createdAt',
      key: 'createdAt',
    },
    {
      title: 'Updated At',
      dataIndex: 'updatedAt',
      key: 'updatedAt',
    },
  ];

  const data = [
    {
      id: 1,
      name: 'Item 1',
      type: 'Type A',
      status: 'Active',
      createdAt: '2024-01-01',
      updatedAt: '2024-01-02',
    },
    {
      id: 2,
      name: 'Item 2',
      type: 'Type B',
      status: 'Inactive',
      createdAt: '2024-01-03',
      updatedAt: '2024-01-04',
    },
  ];

  return (
    <RawContainer>
      <TableList>
        <List
          dataSource={tables}
          renderItem={item => (
            <List.Item>
              <List.Item.Meta title={item} />
            </List.Item>
          )}
        />
      </TableList>
      <TableMain>
        <TableContent>
          <Table
            columns={columns}
            dataSource={data}
            scroll={{ x: 1500, y: 500 }}
            pagination={false}
          />
        </TableContent>
        <QueryArea>
          <TextArea
            placeholder="Enter your SQL query here..."
            autoSize={{ minRows: 2, maxRows: 6 }}
          />
        </QueryArea>
        <ActionBar>
          <Button type="primary" icon={<SaveOutlined />}>
            Save Table
          </Button>
          <Space>
            <Select
              defaultValue="export"
              style={{ width: 120 }}
              options={[
                { value: 'export', label: 'Export' },
                { value: 'delete', label: 'Delete' },
                { value: 'update', label: 'Update' },
              ]}
            />
            <Button type="primary">Apply</Button>
          </Space>
        </ActionBar>
      </TableMain>
    </RawContainer>
  );
};

export default Raw; 