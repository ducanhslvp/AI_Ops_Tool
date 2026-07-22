import { useRouterState } from '@tanstack/react-router'
import { CircleHelp, Lightbulb, ShieldAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

type HelpContent = { title: string; purpose: string; fields: string[]; workflow: string[]; example: string; practices: string[]; notes: string[] }
const guide = (title: string, purpose: string, fields: string[], workflow: string[], example: string, practices: string[], notes: string[]): HelpContent =>
  ({ title, purpose, fields, workflow, example, practices, notes })

const helpByRoute: Array<[RegExp, HelpContent]> = [
  [/\/settings\/account/, guide('SSH Gateway configuration', 'Configure controlled, short-lived connectivity used by backend tools. AI never receives a username, password, key, or raw SSH client.',
    ['Name: operator-facing gateway identifier.', 'Timeout: maximum command runtime before forced termination.', 'Output limit: maximum captured stdout/stderr size.', 'Host-key policy: verification strategy for known hosts.', 'Enabled: whether the gateway can accept governed operations.'],
    ['Create a gateway profile.', 'Set timeout and output limits for the environment.', 'Configure strict host-key verification.', 'Reference encrypted credentials from Inventory.', 'Test with a read-only registered action before enabling writes.'],
    'Production Linux Gateway / 30 second timeout / 1 MB output / strict known-hosts',
    ['Use a non-root SSH account.', 'Separate production and non-production gateways.', 'Permit commands only through Tool Registry and Policy Engine.'],
    ['Never place private keys in gateway metadata.', 'Disabling a gateway immediately blocks new sessions.', 'Connection tests are audited.'])],
  [/\/settings\/appearance/, guide('Plugin configuration', 'Manage capability adapters that extend Tool Registry and Discovery without granting AI direct infrastructure access.',
    ['Name: unique plugin identity.', 'Category: SSH, Docker, Kubernetes, database, cloud, or notification.', 'Version: installed implementation version.', 'Capabilities: reviewed actions exposed by the plugin.', 'Enabled: registration state at runtime.'],
    ['Register metadata and configuration schema.', 'Review every capability risk level.', 'Add policy defaults and target restrictions.', 'Test parsing with bounded sample output.', 'Enable only after validation.'],
    'Docker Inventory / category docker / capability docker_inventory / risk low',
    ['Prefer native SDK adapters where available.', 'Reject duplicate action names.', 'Version parsers with their expected output format.'],
    ['A plugin must not accept free-form shell.', 'Secrets must be referenced, never embedded.', 'Disabling a plugin removes its actions from new AI plans.'])],
  [/\/settings\/notifications/, guide('Notification channels', 'Configure delivery of alerts and approval events through in-app, email, webhook, Slack, or Microsoft Teams adapters.',
    ['Name: channel label.', 'Channel type: delivery adapter.', 'Configuration: non-secret endpoint and routing metadata.', 'Secret reference: encrypted token or credential pointer.', 'Enabled: delivery state.'],
    ['Choose a channel type.', 'Add routing metadata and a Secret Manager reference.', 'Send a test notification.', 'Confirm receipt and audit status.', 'Enable the channel for production events.'],
    'Operations Teams / channel teams / secret ref teams-operations / severity high+',
    ['Use separate channels by severity and environment.', 'Rotate webhook secrets regularly.', 'Configure retries and dead-letter handling.'],
    ['Do not paste webhook tokens into JSON configuration.', 'Test messages are labeled and audited.', 'A disabled channel retains history but sends nothing.'])],
  [/\/settings\/display/, guide('Platform settings', 'Manage database-backed operational, observability, security, and retention settings.',
    ['Scope: subsystem owning the setting.', 'Key: stable configuration identifier.', 'Value: validated JSON configuration.', 'Description: operational intent and ownership.'],
    ['Select the owning scope.', 'Review the accepted schema.', 'Apply the smallest required change.', 'Verify health and audit after saving.'],
    'observability / audit_retention / {"days":365}',
    ['Document owner and rollback expectations.', 'Change production values through approval.', 'Keep environment overrides explicit.'],
    ['Unknown fields are rejected by backend schemas.', 'Settings are not a secret store.', 'Restart requirements depend on the consuming service.'])],
  [/\/settings\/templates/, guide('Report templates', 'Create reusable evidence-based layouts for Markdown, HTML, PDF, and CSV reports.',
    ['Name: unique template label.', 'Format: compatible output renderer.', 'Template body: layout with supported placeholders.', 'Enabled: availability during report generation.'],
    ['Select an output format.', 'Use supported evidence placeholders.', 'Generate a test report.', 'Inspect preview and download output.', 'Enable for operators.'],
    'Daily Operations / markdown / {system}, {servers}, {online}, {alerts}, {evidence}',
    ['Keep templates presentation-only.', 'Escape HTML content.', 'Version templates used for regulated reports.'],
    ['Unsupported placeholders are rejected.', 'Templates cannot execute code.', 'Generated reports retain persisted evidence content.'])],
  [/\/settings\/?$/, guide('AI Provider and Codex configuration', 'Configure AI adapters used by the coordinator. Providers receive governed context and Tool schemas, never credentials or direct database/SSH access.',
    ['Provider type: registered adapter such as codex, openai, claude, gemini, ollama, or mock.', 'Model: provider model identifier.', 'Secret reference: pointer resolved only by backend.', 'Configuration: endpoint and non-secret runtime options.', 'Active: provider selected for new sessions.'],
    ['Choose a registered provider adapter.', 'Enter model and endpoint metadata.', 'Attach a Secret Manager reference when required.', 'Run Test Connection.', 'Activate only after Connected status is returned.'],
    'Codex Development / provider codex / mode cli / executable codex / no inline credential',
    ['Use mock or local adapters in development.', 'Keep provider timeout and token limits bounded.', 'Review data residency before activation.'],
    ['Codex App is not accessed through an undocumented API.', 'CLI execution must use an explicit allow-listed executable and isolated workspace.', 'Provider errors must not fall back to unsafe shell.'])],
  [/\/policy/, guide('Policy and Tool Registry', 'Control which registered actions may run, which are denied, and which require human approval.',
    ['Effect: allow, deny, or approval_required.', 'Priority: lower numbers evaluate first.', 'Role: optional RBAC scope.', 'Environment: operational environment scope.', 'Server type and Action: target capability scope.', 'Risk level: low, medium, high, or critical.', 'Enabled: whether the rule participates in evaluation.'],
    ['Search for overlapping rules.', 'Create the narrowest matching scope.', 'Set effect and priority.', 'Save disabled when reviewing a complex rule.', 'Duplicate for a related environment, then enable.', 'Use bulk actions only after checking selection.'],
    'Production / restart_service / high -> approval_required at priority 10',
    ['Always deny destructive database actions.', 'Require approval for production writes.', 'Keep diagnostic reads explicitly allowed.'],
    ['The first matching active rule wins.', 'Deleting or disabling changes evaluation immediately.', 'An initiator cannot self-approve.'])],
  [/\/inventory/, guide('Infrastructure Inventory', 'Maintain Systems, Environments, Servers, and encrypted Credential references used across operations.',
    ['System: business application ownership boundary.', 'Environment: risk and lifecycle context.', 'Hostname/IP: unambiguous server target identity.', 'OS/Role: capability matching and operator context.', 'Credential: encrypted reference resolved only by backend.', 'Status: current inventory availability state.'],
    ['Create Systems and Environments.', 'Create a Credential reference.', 'Add Server metadata and select its System and Environment.', 'Verify IP, OS, and role.', 'Run Test Connection.', 'Use filters and bulk export for review.'],
    'ERP -> Production -> erp-app-01 / 10.10.1.11 / Ubuntu / Application',
    ['Use stable hostnames and unique IPs.', 'Tag by ownership and workload.', 'Rotate credentials without changing server records.'],
    ['Credential values never return to frontend.', 'Referenced records cannot be deleted.', 'Connection tests use the configured gateway and are audited.'])],
  [/\/memory/, guide('AI Memory', 'Review and maintain the persistent operational memory isolated within each System workspace.',
    ['System: required memory ownership boundary.', 'Session: current provider lifecycle state.', 'Context size: bounded material selected for the latest request.', 'Memory size: active workspace memory on disk.', 'Category: summary, operation, incident, decision, or daily record.', 'Archive: retained memory excluded from the default context.'],
    ['Select a System.', 'Search or filter memory by category.', 'Open a record to inspect its summary and timestamp.', 'Select exactly two records to compare.', 'Export active memory for review.', 'Open Maintain, choose one operation, and type the System code to confirm.'],
    'ERP / incidents / Redis unavailable / confidence 0.92 / audit session reference',
    ['Archive old memory instead of deleting it.', 'Refresh memory after correcting noisy conversations.', 'Keep Knowledge and learned Memory separate.', 'Review incident and decision records before production work.'],
    ['Reset Conversation preserves Memory and Knowledge.', 'Reset Memory preserves conversations and source files.', 'Rebuild Workspace never deletes original uploads.', 'Workspace memory contains summaries and audit references, not raw secrets.'])],
  [/\/chats/, guide('AI Operations Chat', 'Investigate infrastructure through a coordinator that can call only backend-registered, policy-governed tools.',
    ['Conversation: persisted investigation context.', 'System/Environment/Server: hierarchical target scope.', 'Prompt: operational question or requested plan.', 'Timeline: tools and decisions produced during execution.', 'Confidence: score, reason, and need-more-data indicator.'],
    ['Select System, Environment, then Server.', 'Verify hostname, IP, OS, and role.', 'Describe the symptom and desired outcome.', 'Review the proposed plan and tool timeline.', 'Approve dangerous operations only after impact review.'],
    'ERP -> Production -> 10.10.1.11 / Investigate nginx 502 errors without restarting services',
    ['Ask for evidence before remediation.', 'Keep one incident per conversation.', 'Export the session for handoff.'],
    ['AI cannot see credentials or send shell.', 'High-risk actions stop at approval.', 'Low confidence should trigger additional evidence collection.'])],
  [/\/terminal/, guide('Gateway Actions', 'Run normalized operational actions through Policy Engine and the short-lived SSH Gateway; this is not a free-form web SSH terminal.',
    ['System/Environment/Server: mandatory target hierarchy.', 'Action: registered Tool Registry capability.', 'Risk: policy classification.', 'Arguments: validated schema values.', 'Result: bounded stdout/stderr, exit code, and confidence.', 'Test profile: development-only reviewed simulation output.'],
    ['Select System, Environment, then Server.', 'Confirm hostname and IP.', 'Choose a compatible action.', 'Review risk and approval requirement.', 'Execute and inspect audited result.'],
    'ERP -> Production -> erp-app-01 (10.10.1.11) -> check_disk',
    ['Use diagnostics before write actions.', 'Keep output limits conservative.', 'Use least-privilege service accounts.'],
    ['Raw shell is intentionally unavailable.', 'Sessions close after each action.', 'Development profiles cannot operate outside development/local simulation.'])],
  [/\/knowledge/, guide('System Knowledge Base', 'Organize runbooks, architecture, network, and deployment evidence under the System that owns it.',
    ['System tree: mandatory document owner.', 'Document category: README, Architecture, Network, Runbook, Deployment, Diagram, or Documents.', 'Extracted content: text indexed for retrieval.', 'Graph nodes/edges: dependency evidence.', 'Updated time: source/index freshness.'],
    ['Select the owning System.', 'Upload PDF, DOCX, Markdown, or TXT.', 'Preview extracted content.', 'Correct the source if extraction is incomplete.', 'Re-index and verify graph evidence.'],
    'ERP / Runbook / nginx-recovery.md',
    ['Keep runbooks task-oriented.', 'Include owners, prerequisites, rollback, and verification.', 'Re-index after every source change.'],
    ['Documents cannot exist without a System.', 'Uploads are size/type validated.', 'Discovery summaries are maintained as System knowledge.'])],
  [/\/discovery/, guide('Infrastructure Discovery', 'Build a configuration snapshot and dependency graph from governed read-only collectors. Discovery describes capacity and topology, not realtime utilization.',
    ['Scope: one System or an explicit server set.', 'Advanced services: includes default OS services only when enabled.', 'Grouping: System, Environment, Network, Docker, or Kubernetes.', 'Node: hostname, IP, OS, CPU cores, RAM capacity, disks, platform and deployed services.', 'Edge: direction, protocol, port, service, confidence, and evidence reason.', 'Snapshot: immutable baseline used for change comparison.'],
    ['Select System or choose servers through System and Environment.', 'Keep Advanced services disabled for application topology.', 'Run discovery and wait for completed/partial status.', 'Use Fit View, Mini Map, search, grouping, and collapse.', 'Select a node to highlight dependencies and inspect evidence.', 'Schedule incremental scans after validating the first baseline.'],
    'ERP / Production -> erp-app-01 -> redis / tcp:6379 -> erp-redis-01',
    ['Prefer incremental scheduled scans.', 'Investigate low-confidence inferred edges.', 'Maintain accurate roles and IPs in Inventory.'],
    ['No CPU/RAM/disk usage is shown.', 'System services are hidden by default.', 'All collectors pass through Tool Registry, Policy, Gateway, and Audit.'])],
  [/\/audit/, guide('Immutable Audit Timeline', 'Review prompts, policy decisions, mapped commands, bounded output, approvals, duration, and integrity hashes.',
    ['Time/User: actor and event timestamp.', 'Target/Tool: server and normalized action.', 'Decision/Result: policy outcome and execution result.', 'Duration: backend operation time.', 'Integrity hash: chained tamper-evidence value.'],
    ['Filter by result or search loaded records.', 'Sort the relevant column.', 'Open row detail or context menu.', 'Compare prompt, command mapping, output, and decision.', 'Export selected or filtered evidence.'],
    'operator@example.com / erp-app-01 / restart_service / approval_required',
    ['Restrict detail access to auditors.', 'Export evidence for incident records.', 'Monitor integrity verification continuously.'],
    ['Audit rows are immutable.', 'Secrets and process arguments are redacted.', 'A hash is evidence of integrity, not a substitute for external immutable retention.'])],
  [/\/reports/, guide('Reports', 'Generate, preview, compare, and export persisted operational evidence for the platform, a System, or a specific Server.',
    ['Scope: System report or Server report.', 'Target: hierarchical System/Environment/Server selection with IP.', 'Template: approved presentation layout.', 'Format: Markdown, HTML, PDF, or CSV.', 'Compare: diff against the latest compatible report.'],
    ['Choose System or Server scope.', 'For Server scope select System, Environment, then Server and verify IP.', 'Choose template and output format.', 'Generate and preview.', 'Compare revisions before distribution.'],
    'Server report / ERP -> Production -> erp-app-01 (10.10.1.11) / PDF',
    ['Use server scope for incident evidence.', 'Use System scope for daily health summaries.', 'Retain generated files according to audit policy.'],
    ['Reports contain persisted evidence, not live dashboards.', 'Server and System must match.', 'Template placeholders are allow-listed.'])],
  [/\/users/, guide('Users and RBAC', 'Manage user identities, roles, and permissions that control every protected backend operation.',
    ['User: email, full name, active state, and assigned role.', 'Role: named permission bundle.', 'Permission: stable backend capability code.', 'Active: blocks or permits authentication without deleting history.'],
    ['Create permissions only for real backend capabilities.', 'Build least-privilege roles.', 'Create user and assign one role.', 'Test access with a non-admin account.', 'Disable before deleting referenced identities.'],
    'Operator role / inventory:read, tool:execute, policy:read',
    ['Separate administration from operations.', 'Review privileged roles quarterly.', 'Disable dormant accounts.'],
    ['Self-deletion is rejected.', 'Passwords are hashed.', 'Role changes affect subsequent authorization checks.'])],
  [/\/development-test/, guide('Development Test Environment', 'Manage reviewed simulation profiles that exercise the same backend, policy, gateway, and audit path as production.',
    ['Profile: named infrastructure condition.', 'Active profile: default simulation behavior.', 'Action: registered Tool capability.', 'Rendered command: backend-owned command mapping.', 'Output/exit code: reviewed simulated result.', 'Target OS: command rendering platform.'],
    ['Create a failure profile.', 'Add overrides using registered actions and validated arguments.', 'Review the backend-rendered command.', 'Activate the profile.', 'Execute through Gateway Actions and verify AI behavior.'],
    'Disk Full / check_disk / Ubuntu / exit 0 / filesystem at 100%',
    ['Keep a Healthy baseline.', 'Store deterministic output.', 'Add regression tests for new profiles.'],
    ['The module returns 404 outside development/local simulation.', 'Frontend cannot submit shell text.', 'Healthy profile cannot be deleted.'])],
  [/^\/$/, guide('Operations Dashboard', 'Summarize current platform health, alerts, audit activity, AI usage, environments, Systems, and recommendations.',
    ['Health: aggregate server availability.', 'Alerts: unresolved severity counts.', 'Operations trend: audited execution volume and failures.', 'Environment health: online/total servers.', 'Recommendations: prioritized actions derived from database state.'],
    ['Review critical alerts.', 'Check degraded and offline servers.', 'Inspect recent denied or failed operations.', 'Open the affected System or server.', 'Generate a report for handoff.'],
    'Critical alert -> ERP database -> Inventory detail -> Audit -> Report',
    ['Use Dashboard for triage, not configuration.', 'Validate trends against audit details.', 'Assign owners to every critical System.'],
    ['Dashboard refreshes periodically.', 'Metrics reflect stored platform state.', 'Use monitoring integrations for realtime telemetry.'])],
]

const fallback = guide('Using this screen', 'Operate the current module through validated backend APIs and auditable actions.',
  ['Search: filters data already loaded.', 'Selection: chooses rows for bulk actions.', 'Actions: commands available for one record.', 'Status: current persisted state.'],
  ['Confirm scope.', 'Filter and inspect records.', 'Select the intended item.', 'Execute the smallest required action.', 'Review toast, status, and audit result.'],
  'Search -> inspect -> select -> reviewed action -> verify result',
  ['Use least privilege.', 'Prefer reversible changes.', 'Export evidence before destructive operations.'],
  ['Long values may be available in tooltips or detail drawers.', 'Destructive actions can be rejected by backend dependencies.'])

export function ContextualHelp() {
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const content = helpByRoute.find(([pattern]) => pattern.test(pathname))?.[1] ?? fallback
  return <Sheet><Tooltip><TooltipTrigger asChild><SheetTrigger asChild><Button variant='ghost' size='icon' className='shrink-0' aria-label='Help for this screen'><CircleHelp className='size-4' /></Button></SheetTrigger></TooltipTrigger><TooltipContent>Help for this screen</TooltipContent></Tooltip>
    <SheetContent className='w-[min(94vw,720px)] overflow-y-auto sm:max-w-2xl'><SheetHeader><SheetTitle>{content.title}</SheetTitle><SheetDescription>{content.purpose}</SheetDescription></SheetHeader>
      <Tabs defaultValue='overview' className='px-4 pb-6'><TabsList className='grid h-auto w-full grid-cols-2 sm:grid-cols-4'><TabsTrigger value='overview'>Overview</TabsTrigger><TabsTrigger value='fields'>Fields</TabsTrigger><TabsTrigger value='workflow'>Workflow</TabsTrigger><TabsTrigger value='practices'>Practices</TabsTrigger></TabsList>
        <TabsContent value='overview' className='space-y-4 pt-3'><GuideSection title='Purpose' items={[content.purpose]} /><section className='rounded-md border bg-muted/30 p-4'><h3 className='mb-2 flex items-center gap-2 font-medium'><Lightbulb className='size-4' />Configuration example</h3><code className='block whitespace-pre-wrap break-words text-xs text-muted-foreground'>{content.example}</code></section></TabsContent>
        <TabsContent value='fields' className='pt-3'><GuideSection title='Fields and controls' items={content.fields} /></TabsContent>
        <TabsContent value='workflow' className='pt-3'><GuideSection title='Recommended workflow' items={content.workflow} numbered /></TabsContent>
        <TabsContent value='practices' className='space-y-5 pt-3'><GuideSection title='Best practices' items={content.practices} /><GuideSection title='Important notes' items={content.notes} warning /></TabsContent>
      </Tabs></SheetContent></Sheet>
}

function GuideSection({ title, items, numbered = false, warning = false }: { title: string; items: string[]; numbered?: boolean; warning?: boolean }) {
  return <section><h3 className='mb-3 flex items-center gap-2 font-medium'>{warning && <ShieldAlert className='size-4 text-amber-500' />}{title}</h3><div className='space-y-2'>{items.map((item, index) => <div key={item} className='flex gap-3 rounded-md border p-3 text-sm'><span className='grid size-5 shrink-0 place-items-center rounded-full bg-muted text-xs font-medium'>{numbered ? index + 1 : '•'}</span><p className='min-w-0 text-muted-foreground'>{item}</p></div>)}</div></section>
}
