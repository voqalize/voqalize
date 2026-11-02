// Generated from demos/fernhollow/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
//   voqalize stage gen demos/fernhollow/frontend/src/stage/scene.json --py demos/fernhollow/backend/stage_gen.py --ts demos/fernhollow/frontend/src/stage/scene.gen.ts
import { defineScene } from "@voqalize/stage";

/** The moves of fernhollow_returns, from its Stage Spec. */
export const scene = defineScene({
  "stage": 1,
  "id": "fernhollow_returns",
  "moves": [
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

export const SPEC_SHA256 = "c2228bce90ec2e32da99e34073a166359b49066a4e5f902acce89a7d06d7776f";
