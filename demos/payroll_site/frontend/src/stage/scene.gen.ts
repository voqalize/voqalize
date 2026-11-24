// Generated from payroll_site/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
//   voqalize stage gen payroll_site/frontend/src/stage/scene.json --py payroll_site/backend/stage_gen.py --ts payroll_site/frontend/src/stage/scene.gen.ts
import { defineScene } from "@voqalize/stage";

/** The moves of paynora_site, from its Stage Spec. */
export const scene = defineScene({
  "stage": 1,
  "id": "paynora_site",
  "moves": [
    {
      "id": "site.go",
      "class": "navigate",
      "args": [
        {
          "name": "path"
        }
      ]
    },
    {
      "id": "site.show",
      "verb": "show",
      "class": "look",
      "args": [
        {
          "name": "thing"
        }
      ]
    },
    {
      "id": "modules.show",
      "verb": "module",
      "class": "look",
      "args": [
        {
          "name": "id"
        }
      ]
    },
    {
      "id": "modules.highlight",
      "class": "reversible",
      "args": [
        {
          "name": "ids",
          "type": "array"
        }
      ]
    },
    {
      "id": "lead.fill",
      "class": "reversible",
      "args": [
        {
          "name": "field",
          "enum": [
            "company",
            "name",
            "headcount",
            "states",
            "current_tool",
            "pains",
            "recommended_plan",
            "email"
          ]
        },
        {
          "name": "value",
          "optional": true
        },
        {
          "name": "items",
          "type": "array",
          "optional": true
        }
      ]
    },
    {
      "id": "pricing.set",
      "class": "reversible",
      "args": [
        {
          "name": "headcount",
          "type": "integer"
        },
        {
          "name": "modules",
          "type": "array"
        },
        {
          "name": "billing",
          "enum": [
            "monthly",
            "annual"
          ],
          "default": "monthly"
        },
        {
          "name": "filing",
          "type": "boolean",
          "default": false
        }
      ]
    },
    {
      "id": "pricing.line",
      "verb": "line",
      "class": "look",
      "args": [
        {
          "name": "item",
          "enum": [
            "base",
            "minimum",
            "filing",
            "subtotal",
            "discount",
            "gst",
            "total",
            "annual",
            "setup"
          ]
        }
      ]
    },
    {
      "id": "calendar.show",
      "class": "reversible",
      "args": [
        {
          "name": "day"
        }
      ]
    },
    {
      "id": "booking.pick",
      "class": "reversible",
      "args": [
        {
          "name": "slot_id"
        }
      ]
    },
    {
      "id": "booking.fill",
      "class": "reversible",
      "args": [
        {
          "name": "field",
          "enum": [
            "company",
            "name",
            "headcount",
            "topic",
            "email"
          ]
        },
        {
          "name": "value"
        }
      ]
    },
    {
      "id": "booking.confirm",
      "class": "confirmed"
    }
  ],
  "slices": [
    {
      "id": "screen",
      "fields": [
        {
          "name": "path"
        },
        {
          "name": "title"
        }
      ]
    },
    {
      "id": "lead",
      "fields": [
        {
          "name": "company",
          "optional": true
        },
        {
          "name": "name",
          "optional": true
        },
        {
          "name": "headcount",
          "type": "integer",
          "optional": true
        },
        {
          "name": "states",
          "type": "array"
        },
        {
          "name": "current_tool",
          "optional": true
        },
        {
          "name": "pains",
          "type": "array"
        },
        {
          "name": "recommended_plan",
          "optional": true
        },
        {
          "name": "modules",
          "type": "array"
        },
        {
          "name": "has_email",
          "type": "boolean"
        },
        {
          "name": "email",
          "optional": true,
          "private": true
        },
        {
          "name": "field",
          "optional": true
        }
      ]
    },
    {
      "id": "pricing",
      "fields": [
        {
          "name": "headcount",
          "type": "integer"
        },
        {
          "name": "modules",
          "type": "array"
        },
        {
          "name": "billing"
        },
        {
          "name": "filing",
          "type": "boolean"
        },
        {
          "name": "plan"
        },
        {
          "name": "monthly",
          "type": "integer"
        }
      ]
    },
    {
      "id": "booking",
      "fields": [
        {
          "name": "day",
          "optional": true
        },
        {
          "name": "slot_id",
          "optional": true
        },
        {
          "name": "filled",
          "type": "array"
        },
        {
          "name": "status"
        },
        {
          "name": "reference",
          "optional": true
        }
      ]
    }
  ],
  "events": [
    {
      "id": "screen.viewed",
      "slice": "screen",
      "op": "set"
    },
    {
      "id": "lead.changed",
      "slice": "lead"
    },
    {
      "id": "pricing.changed",
      "slice": "pricing",
      "op": "set"
    },
    {
      "id": "booking.changed",
      "slice": "booking"
    },
    {
      "id": "booking.confirmed",
      "slice": "booking"
    }
  ]
});

export const SPEC_SHA256 = "19d39696cc2ebb9a38670fe2aa865503e67f230705694d4fbed1f6fd2aad6b0d";
