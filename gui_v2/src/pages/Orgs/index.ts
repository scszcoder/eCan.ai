/**
 * Organizations Module Exports
 */

export { default } from './Orgs';
export * from './types';
export * from './constants';
export { useOrgs } from './hooks/useOrgs';

// Component exports
export { default as OrgTree } from './components/OrgTree';
export { default as OrgDetails } from './components/OrgDetails';
export { default as OrgModal } from './components/OrgModal';
export { default as AgentBindingModal } from './components/AgentBindingModal';
export { default as AgentList } from './components/AgentList';

// Backward compatibility aliases
export { useOrgs as useOrganizations } from './hooks/useOrgs';
export { default as OrganizationTree } from './components/OrgTree';
export { default as OrganizationDetails } from './components/OrgDetails';
export { default as OrganizationModal } from './components/OrgModal';
