/**
 * Flowforge pages: the workflow list and the editor shell.
 *
 * The editor is three columns — a left rail (the request's typed context + the
 * governed catalog you assemble from), the center vertical flow, and a right panel
 * that toggles between the block inspector, the **code** behind a block (the escape
 * hatch), the **tests** + coverage gaps, and the **live runtime** after publish.
 */

import { CONNECTORS, PALETTE, connector, connectorActionLabel } from './data';
import { FlowView } from './flow';
import { useForge, type Panel } from './store';
import { CATEGORY_LABEL, KIND_META, TYPE_LABEL, type ContextField, type Workflow, type WorkflowState } from './types';

// ─── List view ───────────────────────────────────────────────────────────────────

export function ListView() {
  const { model, openWorkflow, dispatch } = useForge();
  return (
    <div className="ff-list">
      <div className="ff-list-head">
        <h1>Service Request Workflows</h1>
        <p>
          Assembled from a governed catalog of connectors and blocks. Ask Ada to open one and change it, or
          author a new one from scratch.
        </p>
      </div>
      <div className="ff-grid">
        {model.workflows.map((w) => (
          <button key={w.id} className="ff-card" onClick={() => openWorkflow(w.id)}>
            <div className="ff-card-top">
              <span className={`ff-tag ff-tag-${w.category}`}>{CATEGORY_LABEL[w.category]}</span>
              <span className={`ff-status ff-status-${w.status}`}>{w.status}</span>
            </div>
            <div className="ff-card-name">{w.name}</div>
            <div className="ff-card-desc">{w.description}</div>
            <div className="ff-card-foot">
              <span>{w.states.length} steps</span>
              <span>v{w.version}</span>
              {w.runsPerMonth ? <span>{w.runsPerMonth.toLocaleString()}/mo</span> : null}
              <span className="ff-card-when">{w.updatedLabel}</span>
            </div>
          </button>
        ))}
        <button
          className="ff-card ff-card-new"
          onClick={() =>
            dispatch({
              command: 'create_workflow',
              payload: {
                id: '',
                name: 'Untitled workflow',
                description: '',
                category: 'ITSM',
                trigger: '',
                channels: [],
                context: [],
              },
            })
          }
        >
          <div className="ff-plus">+</div>
          <div className="ff-card-name">New workflow</div>
          <div className="ff-card-desc">Start from a blank trigger → end and build it up by voice.</div>
        </button>
      </div>
    </div>
  );
}

// ─── Editor shell ────────────────────────────────────────────────────────────────

export function Editor() {
  const { active, model, openList, setPanel, dispatch } = useForge();
  if (!active) return null;
  const wf = active;

  return (
    <div className="ff-editor">
      <header className="ff-ehead">
        <button className="ff-back" onClick={openList}>
          ‹ Workflows
        </button>
        <div className="ff-ehead-mid">
          <span className="ff-ename">{wf.name}</span>
          <span className={`ff-status ff-status-${wf.status}`}>{wf.status}</span>
          <span className="ff-ever">v{wf.version}</span>
          <span className="ff-ewhen">{wf.updatedLabel}</span>
        </div>
        <button
          className={`ff-publish ${wf.status === 'draft' ? 'ff-publish-hot' : ''}`}
          onClick={() => dispatch({ command: 'publish_workflow', payload: {} })}
        >
          ⚡ Publish
        </button>
      </header>

      <div className="ff-cols">
        <LeftRail wf={wf} />
        <main className="ff-center">
          <FlowView />
        </main>
        <section className="ff-right">
          <nav className="ff-tabs">
            {(['flow', 'code', 'tests', 'runtime'] as Panel[]).map((p) => (
              <button key={p} className={model.panel === p ? 'ff-tab ff-tab-on' : 'ff-tab'} onClick={() => setPanel(p)}>
                {p === 'flow' ? 'Inspector' : p === 'runtime' ? 'Live' : p[0].toUpperCase() + p.slice(1)}
              </button>
            ))}
          </nav>
          <div className="ff-panel">
            {model.panel === 'flow' && <Inspector wf={wf} />}
            {model.panel === 'code' && <CodePanel wf={wf} />}
            {model.panel === 'tests' && <TestsPanel wf={wf} />}
            {model.panel === 'runtime' && <RuntimePanel />}
          </div>
        </section>
      </div>
    </div>
  );
}

// ─── Left rail: context + catalog ────────────────────────────────────────────────

function LeftRail({ wf }: { wf: Workflow }) {
  return (
    <aside className="ff-left">
      <div className="ff-trigger">
        <div className="ff-eyebrow">Trigger</div>
        <div className="ff-trigger-txt">{wf.trigger}</div>
        <div className="ff-chips">
          {wf.channels.map((c) => (
            <span key={c} className="ff-chip">
              {c}
            </span>
          ))}
        </div>
      </div>

      <div className="ff-section">
        <div className="ff-eyebrow">Request fields</div>
        {wf.context.map((f) => (
          <ContextRow key={f.key} f={f} />
        ))}
        {wf.context.length === 0 && <div className="ff-empty">No fields yet.</div>}
      </div>

      <div className="ff-section">
        <div className="ff-eyebrow">Blocks</div>
        <div className="ff-palette">
          {PALETTE.map((b) => (
            <div key={b.kind} className="ff-pal" title={b.blurb}>
              <span className="ff-pal-ic" style={{ color: KIND_META[b.kind].color }}>
                {b.icon}
              </span>
              {b.label}
            </div>
          ))}
        </div>
      </div>

      <div className="ff-section">
        <div className="ff-eyebrow">Connector catalog</div>
        <div className="ff-cat">
          {CONNECTORS.map((c) => (
            <div key={c.id} className="ff-cat-row" title={c.actions.map((a) => a.label).join(', ')}>
              <span className="ff-cat-ic">{c.icon}</span>
              <span className="ff-cat-name">{c.name}</span>
              <span className="ff-cat-cat">{c.category}</span>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}

function ContextRow({ f }: { f: ContextField }) {
  return (
    <div className="ff-ctx">
      <span className="ff-ctx-label">{f.label}</span>
      <span className="ff-ctx-type">{TYPE_LABEL[f.type]}</span>
      {f.derived && <span className="ff-ctx-derived">auto</span>}
      {f.note && !f.derived && <span className="ff-ctx-note">{f.note}</span>}
    </div>
  );
}

// ─── Inspector ───────────────────────────────────────────────────────────────────

function Inspector({ wf }: { wf: Workflow }) {
  const { model } = useForge();
  const s = wf.states.find((x) => x.id === model.selectedId);
  if (!s) {
    return (
      <div className="ff-inspect ff-inspect-empty">
        <p>{wf.description}</p>
        <p className="ff-hint">Select a block to inspect it — or ask Ada to add, branch, or wire one.</p>
      </div>
    );
  }
  const meta = KIND_META[s.kind];
  return (
    <div className="ff-inspect">
      <div className="ff-inspect-head" style={{ color: meta.color }}>
        <span>{meta.icon}</span> {meta.label}
      </div>
      <h3>{s.label}</h3>
      <dl className="ff-props">
        {s.connectorId && <Prop k="connector" v={connectorActionLabel(s.connectorId, s.actionId)} />}
        {s.approver && <Prop k="approver" v={s.approver} />}
        {s.slaHours != null && <Prop k="SLA" v={`${s.slaHours}h`} />}
        {s.next && <Prop k="on success →" v={label(wf, s.next)} />}
        {s.rejectTo && <Prop k="on reject →" v={label(wf, s.rejectTo)} />}
        {s.else && <Prop k="otherwise →" v={label(wf, s.else)} />}
        {s.outcome && <Prop k="outcome" v={s.outcome} />}
      </dl>
      {s.fields && s.fields.length > 0 && (
        <div className="ff-inspect-sub">
          <div className="ff-eyebrow">Form fields</div>
          {s.fields.map((f) => (
            <div key={f.key} className="ff-ctx">
              <span className="ff-ctx-label">{f.label}</span>
              <span className="ff-ctx-type">{TYPE_LABEL[f.type]}</span>
            </div>
          ))}
        </div>
      )}
      {s.branches && s.branches.length > 0 && (
        <div className="ff-inspect-sub">
          <div className="ff-eyebrow">Branches</div>
          {s.branches.map((b) => (
            <div key={b.id} className="ff-branch">
              <div className="ff-branch-lbl">{b.label} → {label(wf, b.to)}</div>
              <code>{b.guard}</code>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Prop({ k, v }: { k: string; v: string }) {
  return (
    <>
      <dt>{k}</dt>
      <dd>{v}</dd>
    </>
  );
}

function label(wf: Workflow, id?: string): string {
  return wf.states.find((s) => s.id === id)?.label ?? id ?? '—';
}

// ─── Code panel (the escape hatch, behind a toggle) ──────────────────────────────

interface Snippet {
  id: string;
  title: string;
  sub: string;
  code: string;
}

function collectCode(wf: Workflow): Snippet[] {
  const out: Snippet[] = [];
  for (const f of wf.context) {
    if (f.derived && f.expr) out.push({ id: `d_${f.key}`, title: f.key, sub: 'derived field', code: `return ${f.expr};` });
  }
  for (const s of wf.states) {
    if (s.kind === 'gateway') {
      for (const b of s.branches ?? []) {
        out.push({ id: b.id, title: `${s.label} · ${b.label}`, sub: 'decision rule', code: `return ${b.guard};` });
      }
    }
    if (s.kind === 'code' && s.code) out.push({ id: s.id, title: s.label, sub: 'script', code: s.code });
  }
  return out;
}

function CodePanel({ wf }: { wf: Workflow }) {
  const { model } = useForge();
  const snippets = collectCode(wf);
  if (snippets.length === 0) {
    return <div className="ff-inspect-empty">No code yet. Guards, derived fields, and code blocks appear here.</div>;
  }
  return (
    <div className="ff-code">
      <div className="ff-code-lead">Real JavaScript — evaluated on the live request, not a template</div>
      {snippets.map((sn) => (
        <div key={sn.id} className={`ff-snippet ${model.codeStateId === sn.id ? 'ff-snippet-on' : ''}`}>
          <div className="ff-snippet-head">
            <span className="ff-snippet-title">{sn.title}</span>
            <span className="ff-snippet-sub">{sn.sub}</span>
          </div>
          <pre>
            <code>{sn.code}</code>
          </pre>
        </div>
      ))}
    </div>
  );
}

// ─── Tests + coverage ────────────────────────────────────────────────────────────

function TestsPanel({ wf }: { wf: Workflow }) {
  const { dispatch } = useForge();
  const gaps = wf.gaps.filter((g) => !g.resolved);
  const passed = wf.tests.filter((t) => t.status === 'pass').length;
  return (
    <div className="ff-tests">
      <div className="ff-tests-bar">
        <button className="ff-run" onClick={() => dispatch({ command: 'run_tests', payload: {} })}>
          ▶ Run {wf.tests.length} test{wf.tests.length === 1 ? '' : 's'}
        </button>
        {wf.tests.length > 0 && (
          <span className="ff-tests-score">
            {passed}/{wf.tests.length} passing
          </span>
        )}
      </div>

      {wf.tests.map((t) => (
        <div key={t.id} className={`ff-test ff-test-${t.status}`}>
          <div className="ff-test-top">
            <span className={`ff-dot ff-dot-${t.status}`} />
            <span className="ff-test-name">{t.name}</span>
          </div>
          <div className="ff-test-line">
            in <code>{stLabel(wf, t.givenState)}</code>, on <b>{t.event}</b> → expect{' '}
            <code>{stLabel(wf, t.expectState)}</code>
          </div>
          {t.status === 'fail' && t.actualState && (
            <div className="ff-test-fail">got {stLabel(wf, t.actualState)}</div>
          )}
        </div>
      ))}
      {wf.tests.length === 0 && <div className="ff-empty">No tests yet. Ask Ada to add a scenario.</div>}

      <div className="ff-coverage">
        <div className="ff-cov-head">
          <div className="ff-eyebrow">Coverage</div>
          <button className="ff-cov-btn" onClick={() => dispatch({ command: 'review_coverage', payload: {} })}>
            Check for gaps
          </button>
        </div>
        {gaps.length === 0 ? (
          <div className="ff-empty">No open gaps flagged.</div>
        ) : (
          gaps.map((g) => (
            <div key={g.id} className="ff-gap">
              <div className="ff-gap-tag">
                {stLabel(wf, g.state)} · <b>{g.event}</b>
              </div>
              <div className="ff-gap-q">{g.question}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function stLabel(wf: Workflow, id: string): string {
  return wf.states.find((s) => s.id === id)?.label ?? id;
}

// ─── Live (the workflow in production) ───────────────────────────────────────────

function RuntimePanel() {
  const { model, active, dispatch } = useForge();
  const dep = model.deployment;
  if (!dep || !active) {
    return (
      <div className="ff-runtime-empty">
        <div className="ff-live-mark">⚡</div>
        <p>
          Publish to make this version live. Runs are <strong>durable</strong> — a request that's mid-approval keeps
          its place if anything restarts, and every step runs exactly once.
        </p>
        <button className="ff-run" onClick={() => dispatch({ command: 'publish_workflow', payload: {} })}>
          Publish
        </button>
      </div>
    );
  }
  return (
    <div className="ff-runtime">
      <div className="ff-live">
        <span className="ff-live-dot" /> Live in production
      </div>
      <dl className="ff-props">
        <Prop k="workflow" v={active.name} />
        <Prop k="version" v={`v${dep.version}`} />
        <Prop k="latest run" v={dep.runId} />
        <Prop k="environment" v="Production" />
      </dl>
      <div className="ff-eyebrow">Recent activity</div>
      <ol className="ff-history">
        {dep.history.map((h) => (
          <li key={h.id}>
            <span className="ff-hev">{h.type}</span>
            <span className="ff-hdetail">{h.detail}</span>
            <span className="ff-hts">{h.ts}</span>
          </li>
        ))}
      </ol>
      <p className="ff-live-note">
        Every step is checkpointed as it runs, so a request that's in flight when something restarts resumes exactly
        where it left off — no duplicate approvals, no double-provisioning.
      </p>
    </div>
  );
}
