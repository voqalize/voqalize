// Generated from demos/fernhollow/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
//   voqalize stage gen demos/fernhollow/frontend/src/stage/scene.json --py demos/fernhollow/backend/stage_gen.py --ts demos/fernhollow/frontend/src/stage/scene.gen.ts
import { defineScene } from "@voqalize/stage";

/** The moves of fernhollow, from its Stage Spec. */
export const scene = defineScene({
  "stage": 1,
  "id": "fernhollow",
  "moves": [
    {
      "id": "returns.find",
      "verb": "find",
      "class": "reversible",
      "args": [
        {
          "name": "order_number"
        },
        {
          "name": "email",
          "optional": true
        }
      ]
    },
    {
      "id": "returns.next_step",
      "verb": "next",
      "class": "reversible"
    },
    {
      "id": "returns.open_step",
      "verb": "step",
      "class": "look",
      "args": [
        {
          "name": "step",
          "type": "integer"
        }
      ]
    },
    {
      "id": "returns.fill",
      "verb": "fill",
      "class": "reversible",
      "args": [
        {
          "name": "field"
        },
        {
          "name": "value"
        }
      ]
    },
    {
      "id": "returns.select_item",
      "verb": "item",
      "class": "reversible",
      "args": [
        {
          "name": "product_id"
        },
        {
          "name": "qty",
          "type": "integer",
          "default": 1
        }
      ]
    },
    {
      "id": "returns.submit",
      "class": "confirmed"
    },
    {
      "id": "size.answer",
      "class": "reversible",
      "args": [
        {
          "name": "question",
          "enum": [
            "kind",
            "mattress",
            "sleepers",
            "room",
            "place",
            "layout",
            "drop"
          ]
        },
        {
          "name": "value"
        }
      ]
    },
    {
      "id": "gifts.set",
      "class": "reversible",
      "args": [
        {
          "name": "recipient",
          "enum": [
            "partner",
            "parent",
            "sibling",
            "friend",
            "host",
            "colleague"
          ],
          "optional": true
        },
        {
          "name": "occasion",
          "enum": [
            "housewarming",
            "birthday",
            "thank_you",
            "wedding",
            "just_because"
          ],
          "optional": true
        },
        {
          "name": "budget",
          "type": "integer",
          "optional": true
        }
      ]
    },
    {
      "id": "orders.open",
      "class": "look",
      "args": [
        {
          "name": "order_number"
        }
      ]
    },
    {
      "id": "orders.reschedule",
      "class": "reversible",
      "args": [
        {
          "name": "order_number"
        },
        {
          "name": "slot"
        }
      ]
    },
    {
      "id": "kiosk.start",
      "class": "reversible"
    },
    {
      "id": "kiosk.answer",
      "class": "reversible",
      "args": [
        {
          "name": "question",
          "enum": [
            "room",
            "feel",
            "budget"
          ]
        },
        {
          "name": "value"
        }
      ]
    },
    {
      "id": "kiosk.restart",
      "class": "reversible"
    }
  ],
  "slices": [
    {
      "id": "returns_form",
      "fields": [
        {
          "name": "step",
          "type": "integer",
          "optional": true
        },
        {
          "name": "field",
          "optional": true
        },
        {
          "name": "filled",
          "type": "array"
        },
        {
          "name": "reference",
          "optional": true
        }
      ]
    },
    {
      "id": "size_finder",
      "fields": [
        {
          "name": "question",
          "optional": true
        },
        {
          "name": "value",
          "optional": true
        },
        {
          "name": "size",
          "optional": true
        }
      ]
    },
    {
      "id": "gift_edit",
      "fields": [
        {
          "name": "recipient",
          "optional": true
        },
        {
          "name": "occasion",
          "optional": true
        },
        {
          "name": "budget",
          "type": "integer",
          "optional": true
        }
      ]
    },
    {
      "id": "orders",
      "fields": [
        {
          "name": "order_number",
          "optional": true
        },
        {
          "name": "slot",
          "optional": true
        }
      ]
    },
    {
      "id": "kiosk",
      "fields": [
        {
          "name": "screen",
          "optional": true
        },
        {
          "name": "question",
          "optional": true
        },
        {
          "name": "value",
          "optional": true
        }
      ]
    },
    {
      "id": "view",
      "fields": [
        {
          "name": "thing"
        },
        {
          "name": "label"
        }
      ]
    },
    {
      "id": "form",
      "fields": [
        {
          "name": "form"
        },
        {
          "name": "filled",
          "type": "array"
        },
        {
          "name": "missing",
          "type": "array"
        },
        {
          "name": "left",
          "type": "integer"
        },
        {
          "name": "done",
          "type": "boolean"
        }
      ]
    }
  ],
  "events": [
    {
      "id": "returns.field_filled",
      "slice": "returns_form"
    },
    {
      "id": "returns.step_reached",
      "slice": "returns_form"
    },
    {
      "id": "returns.return_submitted",
      "slice": "returns_form"
    },
    {
      "id": "size.answered",
      "slice": "size_finder"
    },
    {
      "id": "gifts.changed",
      "slice": "gift_edit"
    },
    {
      "id": "orders.opened",
      "slice": "orders"
    },
    {
      "id": "orders.delivery_changed",
      "slice": "orders"
    },
    {
      "id": "kiosk.screen",
      "slice": "kiosk"
    },
    {
      "id": "kiosk.answered",
      "slice": "kiosk"
    },
    {
      "id": "view.changed",
      "slice": "view",
      "op": "set"
    },
    {
      "id": "form.changed",
      "slice": "form",
      "op": "set"
    }
  ]
});

export const SPEC_SHA256 = "64259e444f7dfb12086823142a08d0373ccab6e3ffaefb68c0e1fffee967cb06";
