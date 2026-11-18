// Generated from payroll_app/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
//   voqalize stage gen payroll_app/frontend/src/stage/scene.json --py payroll_app/backend/stage_gen.py --ts payroll_app/frontend/src/stage/scene.gen.ts
import { defineScene } from "@voqalize/stage";

/** The moves of tankora_app, from its Stage Spec. */
export const scene = defineScene({
  "stage": 1,
  "id": "tankora_app",
  "moves": [
    {
      "id": "app.go",
      "verb": "go",
      "class": "navigate",
      "args": [
        {
          "name": "page"
        }
      ]
    },
    {
      "id": "app.show",
      "verb": "show",
      "class": "look",
      "args": [
        {
          "name": "thing"
        }
      ]
    },
    {
      "id": "app.open",
      "class": "navigate",
      "args": [
        {
          "name": "path"
        }
      ]
    },
    {
      "id": "payslip.compare",
      "class": "navigate",
      "args": [
        {
          "name": "employee_id"
        },
        {
          "name": "month"
        },
        {
          "name": "against",
          "optional": true
        }
      ]
    },
    {
      "id": "regime.compare",
      "class": "navigate",
      "args": [
        {
          "name": "employee_id"
        }
      ]
    },
    {
      "id": "leave.decide",
      "class": "confirmed",
      "args": [
        {
          "name": "request_id"
        },
        {
          "name": "decision",
          "enum": [
            "approve",
            "reject"
          ]
        }
      ]
    },
    {
      "id": "claim.fix",
      "class": "confirmed",
      "args": [
        {
          "name": "claim_id"
        },
        {
          "name": "amount",
          "type": "integer"
        }
      ]
    },
    {
      "id": "claim.decide",
      "class": "confirmed",
      "args": [
        {
          "name": "claim_id"
        },
        {
          "name": "decision",
          "enum": [
            "approve",
            "reject"
          ]
        }
      ]
    },
    {
      "id": "employee.fill",
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
      "id": "employee.save",
      "class": "confirmed"
    },
    {
      "id": "regime.switch",
      "class": "confirmed",
      "args": [
        {
          "name": "employee_id"
        },
        {
          "name": "regime",
          "enum": [
            "new",
            "old"
          ]
        }
      ]
    },
    {
      "id": "ticket.draft",
      "class": "reversible",
      "args": [
        {
          "name": "subject"
        },
        {
          "name": "summary"
        },
        {
          "name": "employee_id",
          "optional": true
        }
      ]
    },
    {
      "id": "ticket.submit",
      "class": "confirmed"
    },
    {
      "id": "setup.step",
      "class": "navigate",
      "args": [
        {
          "name": "step",
          "enum": [
            "company",
            "structure",
            "import",
            "leave",
            "test_run",
            "done"
          ]
        }
      ]
    },
    {
      "id": "setup.fill",
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
      "id": "setup.import",
      "class": "reversible"
    },
    {
      "id": "setup.test_run",
      "class": "reversible"
    },
    {
      "id": "setup.finish",
      "class": "confirmed"
    },
    {
      "id": "me.view",
      "class": "navigate",
      "args": [
        {
          "name": "employee_id"
        },
        {
          "name": "tab",
          "enum": [
            "payslips",
            "tax",
            "declarations",
            "leave"
          ],
          "default": "payslips"
        }
      ]
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
        },
        {
          "name": "employee_id",
          "optional": true
        },
        {
          "name": "tab",
          "optional": true
        }
      ]
    },
    {
      "id": "leave",
      "fields": [
        {
          "name": "request_id"
        },
        {
          "name": "decision"
        },
        {
          "name": "employee_id"
        },
        {
          "name": "lop_days",
          "type": "number"
        }
      ]
    },
    {
      "id": "claim",
      "fields": [
        {
          "name": "claim_id"
        },
        {
          "name": "status"
        },
        {
          "name": "amount",
          "type": "integer"
        }
      ]
    },
    {
      "id": "joiner",
      "fields": [
        {
          "name": "employee_id"
        },
        {
          "name": "name"
        },
        {
          "name": "gender"
        },
        {
          "name": "department"
        },
        {
          "name": "title"
        },
        {
          "name": "grade"
        },
        {
          "name": "location"
        },
        {
          "name": "joined"
        },
        {
          "name": "annual_ctc",
          "type": "integer"
        },
        {
          "name": "tax_regime"
        },
        {
          "name": "email",
          "private": true
        }
      ]
    },
    {
      "id": "regime",
      "fields": [
        {
          "name": "employee_id"
        },
        {
          "name": "regime"
        }
      ]
    },
    {
      "id": "ticket",
      "fields": [
        {
          "name": "ticket_id"
        },
        {
          "name": "subject"
        }
      ]
    },
    {
      "id": "run",
      "fields": [
        {
          "name": "run_id"
        },
        {
          "name": "status"
        }
      ]
    },
    {
      "id": "setup",
      "fields": [
        {
          "name": "step"
        },
        {
          "name": "filled",
          "type": "array"
        },
        {
          "name": "imported",
          "type": "integer",
          "optional": true
        },
        {
          "name": "test_run",
          "type": "boolean",
          "optional": true
        },
        {
          "name": "finished",
          "type": "boolean",
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
      "id": "leave.decided",
      "slice": "leave",
      "op": "set"
    },
    {
      "id": "claim.changed",
      "slice": "claim",
      "op": "set"
    },
    {
      "id": "employee.added",
      "slice": "joiner",
      "op": "set"
    },
    {
      "id": "regime.switched",
      "slice": "regime",
      "op": "set"
    },
    {
      "id": "ticket.created",
      "slice": "ticket",
      "op": "set"
    },
    {
      "id": "run.approved",
      "slice": "run",
      "op": "set"
    },
    {
      "id": "setup.changed",
      "slice": "setup",
      "op": "set"
    }
  ]
});

export const SPEC_SHA256 = "1501794a573db8417cdd56e33354a6f8528c8abb55d43087d0a7782d02aa71f2";
