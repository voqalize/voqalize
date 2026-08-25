/**
 * OrdersStore — the single source of truth for the returns demo's screen state.
 *
 * Both the human (tapping the UI) and the Returns Assistant agent (via
 * `ui-command` RTVI events) call the SAME actions, so the screen stays
 * consistent no matter who is driving. Navigation is plain React state — never
 * the router — so the `PipecatClient` mounted alongside never unmounts and the
 * call stays live as the shopper moves between pages.
 *
 * The store also holds an `agentSend` channel: the voice widget registers a way
 * to push RTVI client messages to the bot, and the return form uses it to send
 * a captured photo (`photo_upload`) and the final submission (`return_submitted`).
 */

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { getOrder } from './catalog';

export type View = 'orders' | 'order' | 'diagnostics' | 'return';

export type RefundMethod = 'original_payment' | 'store_credit';

export type DiagResult = 'pending' | 'ok' | 'issue';

export interface DiagStep {
  label: string;
  summary: string | null;
  result: DiagResult;
}

export interface Diagnostics {
  orderId: string;
  itemId: string;
  steps: DiagStep[];
  currentIndex: number; // which step is highlighted as "now checking"
  complete: boolean;
  resolved: boolean; // true if troubleshooting fixed the item (no return)
}

export interface PhotoCheck {
  matches: boolean;
  boxPresent: boolean;
  passed: boolean;
  note: string;
}

export interface ReturnForm {
  reason: string;
  condition: string;
  refundMethod: RefundMethod;
  notes: string;
}

export interface ReturnState {
  orderId: string;
  itemId: string;
  reason: string; // initial reason from start_return
  form: ReturnForm | null; // populated by the agent's fill_return_form
  photoDataUrl: string | null; // local preview once the shopper uploads
  photoPending: boolean; // photo uploaded, awaiting the agent's verdict
  photoCheck: PhotoCheck | null; // the agent's verification result
  photoRequested: boolean; // request_photo → make the photo button pulse
  submitted: boolean;
  rma: string | null;
}

export interface Highlight {
  orderId: string;
  itemId: string;
  nonce: number;
}

interface State {
  view: View;
  orderId: string | null;
  highlight: Highlight | null;
  diag: Diagnostics | null;
  ret: ReturnState | null;
}

const INITIAL: State = {
  view: 'orders',
  orderId: null,
  highlight: null,
  diag: null,
  ret: null,
};

export type AgentSend = (type: string, data: unknown) => void;

export interface OrdersActions {
  openOrders: () => void;
  openOrder: (orderId: string) => void;
  highlightItem: (orderId: string, itemId: string) => void;
  startDiagnostics: (orderId: string, itemId: string, steps: string[]) => void;
  recordDiagnostic: (step: number, summary: string, result: 'ok' | 'issue') => void;
  completeDiagnostics: (resolved: boolean, reason?: string) => void;
  startReturn: (orderId: string, itemId: string, reason: string) => void;
  requestPhoto: () => void;
  /** Shopper picked/captured a photo (local preview); marks it pending verify. */
  setPhoto: (dataUrl: string) => void;
  /** Agent's photo verification result. */
  setPhotoCheck: (check: PhotoCheck) => void;
  /** Agent fills in the return form fields and enables submit. */
  fillReturnForm: (form: ReturnForm) => void;
  /** Shopper taps "Confirm & submit return"; returns the generated RMA. */
  submitReturn: () => string | null;
}

export interface OrdersStore extends State, OrdersActions {
  /** Push an RTVI client message to the bot (null until the call connects). */
  agentSend: AgentSend | null;
  registerAgentSend: (fn: AgentSend | null) => void;
  /** Dispatch a `ui-command` event's `{ command, payload }` from the agent. */
  handleUiCommand: (command: string, payload: Record<string, unknown>) => void;
}

const Ctx = createContext<OrdersStore | null>(null);

function makeRma(): string {
  const n = Math.floor(1000 + Math.random() * 9000);
  return `RMA-${n}`;
}

export function OrdersProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(INITIAL);
  const agentSendRef = useRef<AgentSend | null>(null);
  const [, forceTick] = useState(0);

  const registerAgentSend = useCallback((fn: AgentSend | null) => {
    agentSendRef.current = fn;
    forceTick((t) => t + 1); // re-render consumers so `agentSend` reflects connection
  }, []);

  const openOrders = useCallback(() => {
    setState((s) => ({ ...s, view: 'orders', highlight: null }));
  }, []);

  const openOrder = useCallback((orderId: string) => {
    if (!getOrder(orderId)) return;
    setState((s) => ({ ...s, view: 'order', orderId, highlight: null }));
  }, []);

  const highlightItem = useCallback((orderId: string, itemId: string) => {
    if (!getOrder(orderId)) return;
    setState((s) => ({
      ...s,
      view: 'order',
      orderId,
      highlight: { orderId, itemId, nonce: (s.highlight?.nonce ?? 0) + 1 },
    }));
  }, []);

  const startDiagnostics = useCallback((orderId: string, itemId: string, steps: string[]) => {
    if (!getOrder(orderId)) return;
    const clean = steps
      .filter((s) => typeof s === 'string' && s.trim())
      .map<DiagStep>((s) => ({ label: s, summary: null, result: 'pending' }));
    if (!clean.length) return;
    setState((s) => ({
      ...s,
      view: 'diagnostics',
      orderId,
      highlight: null,
      diag: { orderId, itemId, steps: clean, currentIndex: 0, complete: false, resolved: false },
    }));
  }, []);

  const recordDiagnostic = useCallback((step: number, summary: string, result: 'ok' | 'issue') => {
    setState((s) => {
      if (!s.diag) return s;
      const idx =
        Number.isFinite(step) && step >= 1 && step <= s.diag.steps.length
          ? step - 1
          : s.diag.currentIndex;
      const steps = s.diag.steps.map((st, i) => (i === idx ? { ...st, summary, result } : st));
      let next = idx + 1;
      while (next < steps.length && steps[next].result !== 'pending') next++;
      return { ...s, diag: { ...s.diag, steps, currentIndex: Math.min(next, steps.length) } };
    });
  }, []);

  const completeDiagnostics = useCallback((resolved: boolean, reason?: string) => {
    setState((s) => {
      if (!s.diag) return s;
      const diag = { ...s.diag, complete: true, resolved, currentIndex: s.diag.steps.length };
      if (resolved) return { ...s, diag };
      // Not resolved → flow straight into the return form (photo step).
      return {
        ...s,
        diag,
        view: 'return',
        orderId: diag.orderId,
        ret: {
          orderId: diag.orderId,
          itemId: diag.itemId,
          reason: reason || s.ret?.reason || '',
          form: null,
          photoDataUrl: null,
          photoPending: false,
          photoCheck: null,
          photoRequested: false,
          submitted: false,
          rma: null,
        },
      };
    });
  }, []);

  const startReturn = useCallback((orderId: string, itemId: string, reason: string) => {
    if (!getOrder(orderId)) return;
    setState((s) => ({
      ...s,
      view: 'return',
      orderId,
      highlight: null,
      ret: {
        orderId,
        itemId,
        reason,
        form: null,
        photoDataUrl: null,
        photoPending: false,
        photoCheck: null,
        photoRequested: false,
        submitted: false,
        rma: null,
      },
    }));
  }, []);

  const requestPhoto = useCallback(() => {
    setState((s) => (s.ret ? { ...s, ret: { ...s.ret, photoRequested: true } } : s));
  }, []);

  const setPhoto = useCallback((dataUrl: string) => {
    setState((s) =>
      s.ret
        ? {
            ...s,
            ret: {
              ...s.ret,
              photoDataUrl: dataUrl,
              photoPending: true,
              photoCheck: null,
              photoRequested: false,
            },
          }
        : s,
    );
  }, []);

  const setPhotoCheck = useCallback((check: PhotoCheck) => {
    setState((s) =>
      s.ret ? { ...s, ret: { ...s.ret, photoCheck: check, photoPending: false } } : s,
    );
  }, []);

  const fillReturnForm = useCallback((form: ReturnForm) => {
    setState((s) =>
      s.ret ? { ...s, ret: { ...s.ret, form, reason: form.reason || s.ret.reason } } : s,
    );
  }, []);

  const submitReturn = useCallback((): string | null => {
    let rma: string | null = null;
    setState((s) => {
      if (!s.ret || s.ret.submitted) return s;
      rma = makeRma();
      return { ...s, ret: { ...s.ret, submitted: true, rma } };
    });
    return rma;
  }, []);

  const handleUiCommand = useCallback(
    (command: string, payload: Record<string, unknown>) => {
      const str = (v: unknown) => (typeof v === 'string' && v ? v : undefined);
      const num = (v: unknown) => (typeof v === 'number' ? v : undefined);
      const bool = (v: unknown) => v === true;
      switch (command) {
        case 'open_orders':
          openOrders();
          break;
        case 'open_order':
          if (str(payload.order_id)) openOrder(str(payload.order_id)!);
          break;
        case 'highlight_item':
          if (str(payload.order_id) && str(payload.item_id)) {
            highlightItem(str(payload.order_id)!, str(payload.item_id)!);
          }
          break;
        case 'start_diagnostics':
          if (str(payload.order_id) && str(payload.item_id) && Array.isArray(payload.steps)) {
            startDiagnostics(
              str(payload.order_id)!,
              str(payload.item_id)!,
              (payload.steps as unknown[]).map(String),
            );
          }
          break;
        case 'record_diagnostic':
          recordDiagnostic(
            num(payload.step) ?? 0,
            str(payload.summary) ?? '',
            payload.result === 'issue' ? 'issue' : 'ok',
          );
          break;
        case 'complete_diagnostics':
          completeDiagnostics(bool(payload.resolved), str(payload.reason));
          break;
        case 'start_return':
          if (str(payload.order_id) && str(payload.item_id)) {
            startReturn(str(payload.order_id)!, str(payload.item_id)!, str(payload.reason) ?? '');
          }
          break;
        case 'request_photo':
          requestPhoto();
          break;
        case 'set_photo_check':
          setPhotoCheck({
            matches: bool(payload.matches),
            boxPresent: bool(payload.box_present),
            passed: bool(payload.passed),
            note: str(payload.note) ?? '',
          });
          break;
        case 'fill_return_form':
          fillReturnForm({
            reason: str(payload.reason) ?? '',
            condition: str(payload.condition) ?? 'Opened — defective',
            refundMethod: (str(payload.refund_method) as RefundMethod) ?? 'original_payment',
            notes: str(payload.notes) ?? '',
          });
          break;
        default:
          break;
      }
    },
    [
      openOrders,
      openOrder,
      highlightItem,
      startDiagnostics,
      recordDiagnostic,
      completeDiagnostics,
      startReturn,
      requestPhoto,
      setPhotoCheck,
      fillReturnForm,
    ],
  );

  // Built fresh each render (like the shopping store) so `agentSend` always
  // reflects the latest registered channel — `registerAgentSend` bumps a tick
  // to force the re-render when the call connects or drops.
  const store: OrdersStore = {
    ...state,
    agentSend: agentSendRef.current,
    registerAgentSend,
    openOrders,
    openOrder,
    highlightItem,
    startDiagnostics,
    recordDiagnostic,
    completeDiagnostics,
    startReturn,
    requestPhoto,
    setPhoto,
    setPhotoCheck,
    fillReturnForm,
    submitReturn,
    handleUiCommand,
  };

  return <Ctx.Provider value={store}>{children}</Ctx.Provider>;
}

export function useOrders(): OrdersStore {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useOrders must be used within OrdersProvider');
  return ctx;
}
