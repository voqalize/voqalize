/**
 * The opinionated vertical-flow renderer.
 *
 * Not a free-form BPMN canvas (too unwieldy on a projector) — a single top-to-
 * bottom **spine** you read like code. The spine follows each state's primary
 * continuation (`next`, or a gateway's `else`); guarded **branches** peel off into
 * indented side-lanes that rejoin the spine, and an approval's reject exit shows as
 * a small side chip. When a persona simulation runs, the visited trail lights up
 * and the current block pulses.
 */

import { connector, connectorActionLabel } from './data';
import { useForge } from './store';
import { KIND_META, type Workflow, type WorkflowState } from './types';

/** Follow the main column: gateways continue on `else`, everything else on `next`. */
function spineNext(s: WorkflowState): string | undefined {
  return s.kind === 'gateway' ? s.else : s.next;
}

function buildSpine(wf: Workflow): string[] {
  const order: string[] = [];
  const seen = new Set<string>();
  let id: string | undefined = wf.startId;
  while (id && !seen.has(id)) {
    seen.add(id);
    order.push(id);
    const s = wf.states.find((x) => x.id === id);
    if (!s) break;
    id = spineNext(s);
  }
  return order;
}

export function FlowView() {
  const { active, model, focusState, showCode } = useForge();
  if (!active) return null;
  const wf = active;
  const sim = model.sim;

  const spine = buildSpine(wf);
  const spineSet = new Set(spine);
  const byId = (id?: string) => wf.states.find((s) => s.id === id);
  const litIndex = sim ? sim.path.indexOf(sim.current ?? '') : -1;
  const litSet = new Set(sim ? sim.path.slice(0, litIndex + 1) : []);

  const isLit = (id: string) => litSet.has(id);
  const isCurrent = (id: string) => sim?.current === id && !sim.done;

  return (
    <div className="ff-flow">
      {sim && (
        <div className="ff-simbar">
          <span className="ff-simdot" /> Simulating · <strong>{sim.personaLabel}</strong>
          {sim.done && sim.restedAt && (
            <span className="ff-simrest"> → rests at “{byId(sim.restedAt)?.label}”</span>
          )}
        </div>
      )}

      {spine.map((id) => {
        const s = byId(id);
        if (!s) return null;
        const branchLanes =
          s.kind === 'gateway'
            ? (s.branches ?? []).filter((b) => !spineSet.has(b.to))
            : [];
        return (
          <div key={id} className="ff-row">
            <Block
              s={s}
              wf={wf}
              lit={isLit(id)}
              current={isCurrent(id)}
              selected={model.selectedId === id}
              onClick={() => focusState(id)}
              onCode={() => showCode(id)}
            />

            {/* guarded side-lanes that rejoin the spine */}
            {branchLanes.map((b) => {
              const chain: WorkflowState[] = [];
              const cseen = new Set<string>();
              let cur = byId(b.to);
              while (cur && !spineSet.has(cur.id) && !cseen.has(cur.id)) {
                cseen.add(cur.id);
                chain.push(cur);
                cur = byId(cur.next);
              }
              const rejoin = cur ? byId(cur.id) : undefined;
              return (
                <div key={b.id} className="ff-lane">
                  <div className="ff-guard">
                    <span className="ff-guardlabel">{b.label}</span>
                    <code>{b.guard}</code>
                  </div>
                  {chain.map((c) => (
                    <Block
                      key={c.id}
                      s={c}
                      wf={wf}
                      small
                      lit={isLit(c.id)}
                      current={isCurrent(c.id)}
                      selected={model.selectedId === c.id}
                      onClick={() => focusState(c.id)}
                      onCode={() => showCode(c.id)}
                    />
                  ))}
                  {rejoin && <div className="ff-rejoin">↩ rejoins at “{rejoin.label}”</div>}
                </div>
              );
            })}

            {spineNext(s) && s.kind !== 'end' && <div className="ff-connector" />}
          </div>
        );
      })}
    </div>
  );
}

function Block({
  s,
  wf,
  lit,
  current,
  selected,
  small,
  onClick,
  onCode,
}: {
  s: WorkflowState;
  wf: Workflow;
  lit?: boolean;
  current?: boolean;
  selected?: boolean;
  small?: boolean;
  onClick: () => void;
  onCode: () => void;
}) {
  const meta = KIND_META[s.kind];
  const hasCode = s.kind === 'code' || s.kind === 'gateway';
  const cls = [
    'ff-block',
    small ? 'ff-block-sm' : '',
    lit ? 'ff-lit' : '',
    current ? 'ff-current' : '',
    selected ? 'ff-selected' : '',
    s.fresh ? 'ff-fresh' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const rejectTarget = s.rejectTo ? wf.states.find((x) => x.id === s.rejectTo) : undefined;

  return (
    <div className={cls} onClick={onClick} style={{ ['--kind' as any]: meta.color }}>
      <div className="ff-badge" style={{ background: meta.color }}>
        <span>{meta.icon}</span>
      </div>
      <div className="ff-body">
        <div className="ff-kind">{meta.label}</div>
        <div className="ff-label">{s.label}</div>
        {s.kind === 'service' && s.connectorId && (
          <div className="ff-meta">
            <span className="ff-conn">{connector(s.connectorId)?.icon}</span>
            {connectorActionLabel(s.connectorId, s.actionId)}
          </div>
        )}
        {s.kind === 'approval' && s.approver && <div className="ff-meta">Approver · {s.approver}</div>}
        {s.kind === 'form' && s.fields && <div className="ff-meta">{s.fields.length} field(s)</div>}
        {s.kind === 'wait' && s.slaHours != null && <div className="ff-meta">SLA · {s.slaHours}h</div>}
        {s.kind === 'end' && s.outcome && <div className="ff-meta">Outcome · {s.outcome}</div>}
        {s.subtitle && <div className="ff-sub">{s.subtitle}</div>}

        {rejectTarget && (
          <div className="ff-reject">✕ reject → {rejectTarget.label}</div>
        )}
      </div>
      {hasCode && (
        <button
          className="ff-codebtn"
          onClick={(e) => {
            e.stopPropagation();
            onCode();
          }}
          title="Show code"
        >
          {'{ }'}
        </button>
      )}
    </div>
  );
}
