// Generated from dental/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
//   voqalize stage gen dental/frontend/src/stage/scene.json --py dental/backend/stage_gen.py --ts dental/frontend/src/stage/scene.gen.ts
import { defineScene } from "@voqalize/stage";

/** The moves of dantika_front_desk, from its Stage Spec. */
export const scene = defineScene({
  "stage": 1,
  "id": "dantika_front_desk",
  "moves": [
    {
      "id": "site.go",
      "verb": "go",
      "class": "navigate",
      "args": [
        {
          "name": "page",
          "enum": [
            "home",
            "book",
            "my-appointments"
          ]
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
      "id": "book.slots",
      "class": "reversible",
      "args": [
        {
          "name": "service_id"
        },
        {
          "name": "date"
        },
        {
          "name": "branch_id",
          "optional": true
        },
        {
          "name": "dentist_id",
          "optional": true
        },
        {
          "name": "view",
          "enum": [
            "day",
            "week"
          ],
          "default": "day"
        }
      ]
    },
    {
      "id": "book.hold",
      "class": "reversible",
      "args": [
        {
          "name": "service_id"
        },
        {
          "name": "branch_id"
        },
        {
          "name": "date"
        },
        {
          "name": "time"
        },
        {
          "name": "dentist_id",
          "optional": true
        },
        {
          "name": "chair_id",
          "optional": true
        },
        {
          "name": "resource_id",
          "optional": true
        },
        {
          "name": "sittings",
          "type": "array",
          "optional": true
        }
      ]
    },
    {
      "id": "book.confirm",
      "class": "confirmed",
      "args": [
        {
          "name": "booking_id"
        },
        {
          "name": "patient_id"
        },
        {
          "name": "service_id"
        },
        {
          "name": "branch_id"
        },
        {
          "name": "date"
        },
        {
          "name": "time"
        },
        {
          "name": "dentist_id",
          "optional": true
        },
        {
          "name": "chair_id",
          "optional": true
        },
        {
          "name": "resource_id",
          "optional": true
        },
        {
          "name": "sittings",
          "type": "array",
          "optional": true
        },
        {
          "name": "sitting_ids",
          "type": "array",
          "optional": true
        }
      ]
    },
    {
      "id": "patient.phone",
      "class": "reversible",
      "args": [
        {
          "name": "phone"
        }
      ]
    },
    {
      "id": "patient.otp",
      "class": "reversible",
      "args": [
        {
          "name": "code"
        }
      ]
    },
    {
      "id": "patient.name",
      "class": "reversible",
      "args": [
        {
          "name": "name"
        }
      ]
    },
    {
      "id": "appt.focus",
      "class": "look",
      "args": [
        {
          "name": "appointment_id"
        }
      ]
    },
    {
      "id": "appt.propose",
      "class": "reversible",
      "args": [
        {
          "name": "appointment_id"
        },
        {
          "name": "action",
          "enum": [
            "reschedule",
            "cancel"
          ]
        },
        {
          "name": "fee",
          "type": "integer",
          "default": 0
        },
        {
          "name": "date",
          "optional": true
        },
        {
          "name": "time",
          "optional": true
        },
        {
          "name": "branch_id",
          "optional": true
        },
        {
          "name": "dentist_id",
          "optional": true
        },
        {
          "name": "chair_id",
          "optional": true
        },
        {
          "name": "resource_id",
          "optional": true
        }
      ]
    },
    {
      "id": "appt.apply",
      "class": "confirmed",
      "args": [
        {
          "name": "appointment_id"
        },
        {
          "name": "action",
          "enum": [
            "reschedule",
            "cancel"
          ]
        },
        {
          "name": "fee",
          "type": "integer",
          "default": 0
        },
        {
          "name": "date",
          "optional": true
        },
        {
          "name": "time",
          "optional": true
        },
        {
          "name": "branch_id",
          "optional": true
        },
        {
          "name": "dentist_id",
          "optional": true
        },
        {
          "name": "chair_id",
          "optional": true
        },
        {
          "name": "resource_id",
          "optional": true
        }
      ]
    },
    {
      "id": "callback.request",
      "class": "reversible",
      "args": [
        {
          "name": "callback_id"
        },
        {
          "name": "reason"
        },
        {
          "name": "urgency",
          "enum": [
            "urgent",
            "today",
            "routine"
          ]
        },
        {
          "name": "window"
        },
        {
          "name": "phone",
          "optional": true
        }
      ]
    },
    {
      "id": "cal.view",
      "class": "look",
      "args": [
        {
          "name": "date"
        },
        {
          "name": "dentist_id",
          "optional": true
        },
        {
          "name": "resource_id",
          "optional": true
        },
        {
          "name": "mode",
          "enum": [
            "day",
            "week"
          ],
          "default": "week"
        }
      ]
    }
  ]
});

export const SPEC_SHA256 = "b6179d19ca39b7d99cfe526be40c428fc7e9031f3124c1c4eaec06c6eb653487";
