/**
 * Flowforge seed data: the governed catalog (connectors + block palette) and the
 * three Service Request Workflows the admin can open and edit by voice, plus a
 * couple of pre-written tests each. The workflows are deliberately *simple* — the
 * interesting edits (a contractor/privileged branch, an eng-only GitHub seat, an
 * SLA freeze for privileged offboarding) are what the copilot adds live.
 */

import type { BlockSpec, Connector, Workflow } from './types';

// ─── The connector library (the "200+ tools", a curated slice) ──────────────────

export const CONNECTORS: Connector[] = [
  {
    id: 'entra',
    name: 'Microsoft Entra ID',
    category: 'Identity',
    icon: '🪪',
    actions: [
      { id: 'create_user', label: 'Create user' },
      { id: 'disable_user', label: 'Disable user' },
      { id: 'add_to_group', label: 'Add to group' },
      { id: 'revoke_sessions', label: 'Revoke sessions' },
    ],
  },
  {
    id: 'intune',
    name: 'Microsoft Intune',
    category: 'Devices',
    icon: '💻',
    actions: [
      { id: 'assign_device', label: 'Assign device' },
      { id: 'wipe_device', label: 'Wipe device' },
      { id: 'expedite_ship', label: 'Expedite shipping' },
    ],
  },
  {
    id: 'okta',
    name: 'Okta',
    category: 'Identity',
    icon: '🔑',
    actions: [
      { id: 'provision_app', label: 'Provision app access' },
      { id: 'deprovision_app', label: 'Deprovision app access' },
    ],
  },
  {
    id: 'jira',
    name: 'Jira',
    category: 'ITSM',
    icon: '📋',
    actions: [
      { id: 'create_issue', label: 'Create issue' },
      { id: 'transition_issue', label: 'Transition issue' },
    ],
  },
  {
    id: 'servicenow',
    name: 'ServiceNow',
    category: 'ITSM',
    icon: '🧾',
    actions: [
      { id: 'create_incident', label: 'Create incident' },
      { id: 'update_record', label: 'Update record' },
    ],
  },
  {
    id: 'workday',
    name: 'Workday',
    category: 'HR',
    icon: '🏢',
    actions: [
      { id: 'get_worker', label: 'Get worker' },
      { id: 'update_worker', label: 'Update worker' },
    ],
  },
  {
    id: 'github',
    name: 'GitHub',
    category: 'Engineering',
    icon: '🐙',
    actions: [
      { id: 'add_seat', label: 'Add seat' },
      { id: 'remove_seat', label: 'Remove seat' },
    ],
  },
  {
    id: 'teams',
    name: 'Microsoft Teams',
    category: 'Collaboration',
    icon: '💬',
    actions: [
      { id: 'notify', label: 'Send message' },
      { id: 'post_approval', label: 'Post approval card' },
    ],
  },
  {
    id: 'slack',
    name: 'Slack',
    category: 'Collaboration',
    icon: '#️⃣',
    actions: [{ id: 'notify', label: 'Send message' }],
  },
  {
    id: 'docusign',
    name: 'DocuSign',
    category: 'Documents',
    icon: '✍️',
    actions: [{ id: 'send_envelope', label: 'Send envelope' }],
  },
  {
    id: 'zoom',
    name: 'Zoom',
    category: 'Collaboration',
    icon: '🎥',
    actions: [{ id: 'schedule_meeting', label: 'Schedule meeting' }],
  },
];

export function connector(id?: string): Connector | undefined {
  return CONNECTORS.find((c) => c.id === id);
}

export function connectorActionLabel(connectorId?: string, actionId?: string): string {
  const c = connector(connectorId);
  const a = c?.actions.find((x) => x.id === actionId);
  return a ? `${c!.name} · ${a.label}` : c?.name ?? '';
}

// ─── The block palette (what you can drop into a flow) ───────────────────────────

export const PALETTE: BlockSpec[] = [
  { kind: 'form', label: 'Form', icon: '📝', blurb: 'Collect fields from the requester' },
  { kind: 'approval', label: 'Approval', icon: '✔', blurb: 'A person approves or rejects' },
  { kind: 'service', label: 'Action', icon: '🔌', blurb: 'Run one connector action' },
  { kind: 'gateway', label: 'Decision', icon: '◇', blurb: 'Route the request on a condition' },
  { kind: 'wait', label: 'Wait / SLA', icon: '⏳', blurb: 'Pause on a timer or SLA' },
  { kind: 'code', label: 'Script', icon: '{ }', blurb: 'Custom logic in JavaScript' },
];

// ─── Seed workflow 1: Software Access Request (ITSM) ─────────────────────────────
// The hero. Linear as seeded; the admin adds the contractor/privileged branch live.

const accessRequest: Workflow = {
  id: 'access-request',
  name: 'Software Access Request',
  description: 'An employee requests access to a SaaS app; manager approves; access is granted.',
  category: 'ITSM',
  status: 'published',
  version: 4,
  trigger: 'Employee raises "Request app access" from Teams, Slack, or the portal',
  channels: ['Teams', 'Slack', 'Web'],
  runsPerMonth: 1240,
  updatedLabel: 'edited 3 days ago',
  context: [
    { key: 'requester.name', label: 'Requester', type: 'string', note: 'from Entra ID' },
    {
      key: 'requester.type',
      label: 'Requester type',
      type: 'enum',
      enumValues: ['employee', 'contractor'],
      note: 'from Entra ID',
    },
    {
      key: 'app',
      label: 'Requested app',
      type: 'enum',
      enumValues: ['Figma', 'Salesforce', 'GitHub', 'AWS Console', 'Datadog'],
    },
    {
      key: 'privilegedApp',
      label: 'Privileged app?',
      type: 'boolean',
      derived: true,
      expr: "['AWS Console','GitHub','Datadog'].includes(ctx.app)",
      note: 'derived · guards read ctx.privilegedApp',
    },
    { key: 'justification', label: 'Business justification', type: 'string' },
  ],
  startId: 's_start',
  states: [
    { id: 's_start', kind: 'start', label: 'Access request raised', subtitle: 'Teams · Slack · Web', next: 's_form' },
    {
      id: 's_form',
      kind: 'form',
      label: 'Access details',
      subtitle: 'App, duration, justification',
      fields: [
        { key: 'app', label: 'Which app', type: 'enum', enumValues: ['Figma', 'Salesforce', 'GitHub', 'AWS Console', 'Datadog'] },
        { key: 'justification', label: 'Business justification', type: 'string' },
      ],
      next: 's_mgr',
    },
    {
      id: 's_mgr',
      kind: 'approval',
      label: 'Manager approval',
      approver: 'Reporting manager',
      next: 's_provision',
      rejectTo: 's_rejected',
    },
    {
      id: 's_provision',
      kind: 'service',
      label: 'Grant access',
      connectorId: 'okta',
      actionId: 'provision_app',
      next: 's_notify',
    },
    {
      id: 's_notify',
      kind: 'service',
      label: 'Notify requester',
      connectorId: 'teams',
      actionId: 'notify',
      next: 's_done',
    },
    { id: 's_done', kind: 'end', label: 'Access granted', outcome: 'Provisioned' },
    { id: 's_rejected', kind: 'end', label: 'Request declined', outcome: 'Rejected' },
  ],
  tests: [
    {
      id: 't_a1',
      name: 'Standard employee, manager approves',
      givenState: 's_mgr',
      context: { 'requester.type': 'employee', app: 'Figma' },
      event: 'approve',
      expectState: 's_done',
      status: 'idle',
    },
    {
      id: 't_a2',
      name: 'Manager rejects',
      givenState: 's_mgr',
      context: { 'requester.type': 'employee', app: 'Figma' },
      event: 'reject',
      expectState: 's_rejected',
      status: 'idle',
    },
  ],
  gaps: [],
};

// ─── Seed workflow 2: New-Hire Onboarding (HR + IT) ──────────────────────────────

const onboarding: Workflow = {
  id: 'onboarding',
  name: 'New-Hire Onboarding',
  description: 'Provision identity, device, apps, and orientation when a new hire is confirmed.',
  category: 'HR',
  status: 'published',
  version: 7,
  trigger: 'New hire reaches "Confirmed" in Workday',
  channels: ['Workday'],
  runsPerMonth: 85,
  updatedLabel: 'edited 2 weeks ago',
  context: [
    { key: 'hire.name', label: 'New hire', type: 'string', note: 'from Workday' },
    {
      key: 'hire.department',
      label: 'Department',
      type: 'enum',
      enumValues: ['Engineering', 'Sales', 'Finance', 'Operations'],
      note: 'from Workday',
    },
    { key: 'hire.startDate', label: 'Start date', type: 'string', note: 'from Workday' },
    {
      key: 'hire.isEngineering',
      label: 'Engineering hire?',
      type: 'boolean',
      derived: true,
      expr: "ctx.hire.department === 'Engineering'",
      note: 'derived',
    },
  ],
  startId: 'o_start',
  states: [
    { id: 'o_start', kind: 'start', label: 'New hire confirmed', subtitle: 'Workday', next: 'o_identity' },
    { id: 'o_identity', kind: 'service', label: 'Create identity', connectorId: 'entra', actionId: 'create_user', next: 'o_device' },
    { id: 'o_device', kind: 'service', label: 'Assign laptop', connectorId: 'intune', actionId: 'assign_device', next: 'o_apps' },
    { id: 'o_apps', kind: 'service', label: 'Provision baseline apps', connectorId: 'okta', actionId: 'provision_app', next: 'o_orientation' },
    { id: 'o_orientation', kind: 'service', label: 'Schedule orientation', connectorId: 'zoom', actionId: 'schedule_meeting', next: 'o_welcome' },
    { id: 'o_welcome', kind: 'service', label: 'Send welcome message', connectorId: 'teams', actionId: 'notify', next: 'o_done' },
    { id: 'o_done', kind: 'end', label: 'Onboarded', outcome: 'Onboarded' },
  ],
  tests: [
    {
      id: 't_o1',
      name: 'Sales hire onboards',
      givenState: 'o_start',
      context: { 'hire.department': 'Sales' },
      event: 'elapsed',
      expectState: 'o_done',
      status: 'idle',
    },
  ],
  gaps: [],
};

// ─── Seed workflow 3: Employee Offboarding (Security / HR) ───────────────────────
// Already carries a `code` block, so the escape hatch is visible before any edit.

const offboarding: Workflow = {
  id: 'offboarding',
  name: 'Employee Offboarding',
  description: 'Disable accounts, revoke access, reclaim the device, and hand off data on exit.',
  category: 'Security',
  status: 'published',
  version: 5,
  trigger: 'Termination is filed in Workday',
  channels: ['Workday'],
  runsPerMonth: 60,
  updatedLabel: 'edited 5 days ago',
  context: [
    { key: 'employee.name', label: 'Employee', type: 'string', note: 'from Workday' },
    {
      key: 'employee.hadPrivilegedAccess',
      label: 'Had privileged access?',
      type: 'boolean',
      note: 'from Entra ID',
    },
    {
      key: 'termination.type',
      label: 'Termination type',
      type: 'enum',
      enumValues: ['voluntary', 'involuntary'],
      note: 'from Workday',
    },
  ],
  startId: 'x_start',
  states: [
    { id: 'x_start', kind: 'start', label: 'Termination filed', subtitle: 'Workday', next: 'x_disable' },
    { id: 'x_disable', kind: 'service', label: 'Disable accounts', connectorId: 'entra', actionId: 'disable_user', next: 'x_revoke' },
    { id: 'x_revoke', kind: 'service', label: 'Revoke app access', connectorId: 'okta', actionId: 'deprovision_app', next: 'x_reclaim' },
    { id: 'x_reclaim', kind: 'service', label: 'Reclaim & wipe device', connectorId: 'intune', actionId: 'wipe_device', next: 'x_plan' },
    {
      id: 'x_plan',
      kind: 'code',
      label: 'Compute data-handoff plan',
      subtitle: 'Custom logic · JavaScript',
      code: "// Decide where the departing employee's files go.\nconst manager = ctx.employee.manager || 'IT Custody';\nctx.handoff = { owner: manager, retainDays: 90 };\nreturn ctx;",
      next: 'x_notify',
    },
    { id: 'x_notify', kind: 'service', label: 'Notify manager', connectorId: 'teams', actionId: 'notify', next: 'x_done' },
    { id: 'x_done', kind: 'end', label: 'Offboarded', outcome: 'Offboarded' },
  ],
  tests: [
    {
      id: 't_x1',
      name: 'Voluntary exit completes',
      givenState: 'x_start',
      context: { 'termination.type': 'voluntary', 'employee.hadPrivilegedAccess': false },
      event: 'elapsed',
      expectState: 'x_done',
      status: 'idle',
    },
  ],
  gaps: [],
};

export const SEED_WORKFLOWS: Workflow[] = [accessRequest, onboarding, offboarding];

/** The signed-in admin (greeted by name). */
export const ADMIN = { name: 'Priya', role: 'Workflow Administrator' };
