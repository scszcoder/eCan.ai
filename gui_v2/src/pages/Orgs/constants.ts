/**
 * Org Management Constants
 */

import type { OrgType, OrgStatus } from './types';

export const ORG_TYPES: { value: OrgType; key: string }[] = [
  { value: 'company', key: 'pages.org.types.company' },
  { value: 'department', key: 'pages.org.types.department' },
  { value: 'team', key: 'pages.org.types.team' },
  { value: 'group', key: 'pages.org.types.group' },
];

export const ORG_STATUSES: { value: OrgStatus; key: string; color: string }[] = [
  { value: 'active', key: 'pages.org.status.active', color: 'green' },
  { value: 'inactive', key: 'pages.org.status.inactive', color: 'orange' },
  { value: 'archived', key: 'pages.org.status.archived', color: 'red' },
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
    { required: true, message: 'pages.org.form.validation.nameRequired' },
    { min: 2, max: 50, message: 'pages.org.form.validation.nameLength' },
  ],
  description: [
    { max: 200, message: 'pages.org.form.validation.descriptionLength' },
  ],
  org_type: [
    { required: true, message: 'pages.org.form.validation.typeRequired' },
  ],

};
