/** One menu item: its option groups, quantity, a special request, and "Add to order". */
import { Check, Minus, Plus } from "lucide-react";
import { BottomSheet } from "../components/Shell";
import { DINING, getItem } from "../data";
import { clock, price, money } from "../lib/format";
import { alcoholServed, groupsOf, missingPicks, periodOpen, unitPrice } from "../lib/rules";
import { allergenLine, dietPills } from "../pages/Dining";
import { type Sheet, addFromSheet, closeSheet, setItemNote, setItemQty, stayClock, toggleChoice } from "../state/store";
import "../styles/dining.css";

export default function ItemSheet({ sheet }: { sheet: Extract<Sheet, { kind: "item" }> }) {
  const item = getItem(sheet.outlet, sheet.item_id);
  if (!item) return null;
  const now = stayClock().now;
  const period = sheet.outlet === "dining" ? DINING.periods.find((p) => p.id === item.section) : undefined;
  const closedReason =
    period && !periodOpen(period, now) ? `Served ${period.hours}` : item.alcohol && !alcoholServed(now) ? `Alcohol is sold again from ${clock("06:00")}` : null;
  const missing = missingPicks(item, sheet.choices);
  const unit = unitPrice(sheet.outlet, { item_id: item.id, qty: sheet.qty, choices: sheet.choices, note: sheet.note });
  const total = unit * sheet.qty;
  const blocked = closedReason ?? (missing.length ? `Choose: ${missing.join(", ")}` : null);
  const sub = item.bottle !== undefined ? `${price(item.price)} glass · ${price(item.bottle)} bottle` : price(item.price);

  return (
    <BottomSheet
      title={item.name}
      sub={sub}
      onClose={closeSheet}
      footer={
        <div className="dn-foot">
          {blocked ? <p className="dn-why">{blocked}</p> : null}
          <button type="button" className="dn-primary" disabled={!!blocked} onClick={addFromSheet} data-stage-thing="item-add" data-stage-label="Add to order">
            {sheet.edit !== null ? "Update order" : "Add to order"} · {money(total)}
          </button>
        </div>
      }
    >
      <div className="dn-sheet">
        <p className="dn-sheet-desc">{item.desc}</p>
        {item.diet.length || item.allergens.length || item.alcohol ? (
          <div className="dn-sheet-tags">
            {dietPills(item.diet)}
            {item.alcohol ? <span className="dn-diet is-age">21+</span> : null}
            {item.allergens.length ? <span className="dn-allergens">{allergenLine(item.allergens)}</span> : <span className="dn-allergens">No listed allergens</span>}
          </div>
        ) : null}
        {closedReason ? <p className="dn-note is-closed">{closedReason}. You can look now; ordering opens then.</p> : null}

        {groupsOf(item).map(([gid, g]) => {
          const chosen = sheet.choices.some((c) => c.startsWith(`${gid}:`));
          return (
            <div key={gid} className="dn-group" data-stage-thing={`group-${gid}`} data-stage-label={g.label} data-stage-group>
              <div className="dn-group-head">
                <span className="dn-label">{g.label}</span>
                {g.pick ? <span className={`dn-req${chosen ? " is-done" : ""}`}>{chosen ? "Chosen" : "Choose one"}</span> : <span className="dn-opt-hint">Optional, any</span>}
              </div>
              <div className="dn-choices" role={g.pick ? "radiogroup" : "group"} aria-label={g.label}>
                {g.choices.map(([cid, label, add]) => {
                  const on = sheet.choices.includes(`${gid}:${cid}`);
                  const extra = gid === "size" && item.bottle !== undefined ? price(cid === "bottle" ? item.bottle : item.price) : add ? `+${price(add)}` : "";
                  return (
                    <button
                      key={cid}
                      type="button"
                      role={g.pick ? "radio" : "checkbox"}
                      aria-checked={on}
                      className={`dn-choice${on ? " is-on" : ""}`}
                      onClick={() => toggleChoice(gid, cid, g.pick)}
                      data-stage-thing={`choice-${gid}-${cid}`}
                      data-stage-label={label}
                    >
                      <span className={`dn-mark ${g.pick ? "is-radio" : "is-check"}`}>{!g.pick && on ? <Check size={13} strokeWidth={3} /> : null}</span>
                      <span className="dn-choice-label">{label}</span>
                      {extra ? <span className="dn-choice-add">{extra}</span> : null}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}

        <div className="dn-row">
          <span className="dn-label">Quantity</span>
          <div className="dn-stepper" data-stage-thing="qty" data-stage-label={`Quantity ${sheet.qty}`}>
            <button type="button" aria-label="One less" disabled={sheet.qty <= 1} onClick={() => setItemQty(sheet.qty - 1)}>
              <Minus size={16} />
            </button>
            <output aria-live="polite">{sheet.qty}</output>
            <button type="button" aria-label="One more" disabled={sheet.qty >= 20} onClick={() => setItemQty(sheet.qty + 1)}>
              <Plus size={16} />
            </button>
          </div>
        </div>

        <label className="dn-group">
          <span className="dn-label">Special request</span>
          <input
            className="dn-input"
            type="text"
            value={sheet.note}
            placeholder="Allergies, extra napkins, no ice…"
            onChange={(e) => setItemNote(e.target.value)}
            data-stage-thing="note"
            data-stage-label="Special request"
          />
        </label>
      </div>
    </BottomSheet>
  );
}
