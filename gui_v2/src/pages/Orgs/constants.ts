/**
 * Org Management Constants
 */

import type { OrgType, OrgStatus } from './types';

export const ORG_TYPES: { value: OrgType; label: string; key: string }[] = [
  { value: 'company', label: 'Company', key: 'org.types.company' },
  { value: 'department', label: 'Department', key: 'org.types.department' },
  { value: 'team', label: 'Team', key: 'org.types.team' },
  { value: 'group', label: 'Group', key: 'org.types.group' },
];

export const ORG_STATUSES: { value: OrgStatus; label: string; key: string; color: string }[] = [
  { value: 'active', label: 'Active', key: 'org.status.active', color: 'green' },
  { value: 'inactive', label: 'Inactive', key: 'org.status.inactive', color: 'orange' },
  { value: 'archived', label: 'Archived', key: 'org.status.archived', color: 'red' },
];

export const DEFAULT_ORG_TYPE: OrgType = 'department';
export const DEFAULT_ORG_STATUS: OrgStatus = 'active';



export const MODAL_CONFIG = {
  CREATE_ORG: {
    width: 600,
    centered: true,
  },
  BIND_AGENTS: {
    width: 800,
    centered: true,
  },
};



export const TREE_CONFIG = {
  showLine: true,
  showIcon: true,
  draggable: true,
  blockNode: true,
};

export const LIST_CONFIG = {
  pagination: {
    pageSize: 10,
    showSizeChanger: true,
    showQuickJumper: true,
  },
};

export const FORM_LAYOUT = {
  labelCol: { span: 6 },
  wrapperCol: { span: 18 },
};

export const FORM_RULES = {
  name: [
    { required: true, message: 'org.form.validation.nameRequired' },
    { min: 2, max: 50, message: 'org.form.validation.nameLength' },
  ],
  description: [
    { max: 200, message: 'org.form.validation.descriptionLength' },
  ],
  org_type: [
    { required: true, message: 'org.form.validation.typeRequired' },
  ],

};
