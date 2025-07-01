export interface Department {
  id: string;
  name: string;
}

const departments: Department[] = [
  { id: 'hr', name: 'department.hr' },
  { id: 'it', name: 'department.it' },
  { id: 'finance', name: 'department.finance' },
  { id: 'sales', name: 'department.sales' },
  { id: 'marketing', name: 'department.marketing' },
  { id: 'operations', name: 'department.operations' },
  { id: 'customer_service', name: 'department.customer_service' },
  { id: 'research', name: 'department.research' },
  { id: 'legal', name: 'department.legal' },
];

export default departments; 