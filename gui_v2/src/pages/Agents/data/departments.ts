export interface Department {
  id: string;
  name: string;
}

const departments: Department[] = [
  { id: 'hr', name: '人力资源部' },
  { id: 'it', name: '信息技术部' },
  { id: 'finance', name: '财务部' },
  { id: 'sales', name: '销售部' },
  { id: 'marketing', name: '市场部' },
  { id: 'operations', name: '运营部' },
  { id: 'customer_service', name: '客服部' },
  { id: 'research', name: '研发部' },
  { id: 'legal', name: '法务部' },
];

export default departments; 