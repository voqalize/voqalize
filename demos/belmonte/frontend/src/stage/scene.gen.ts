// Generated from belmonte/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
//   voqalize stage gen belmonte/frontend/src/stage/scene.json --py belmonte/backend/stage_gen.py --ts belmonte/frontend/src/stage/scene.gen.ts
import { defineScene } from "@voqalize/stage";

/** The moves of belmonte, from its Stage Spec. */
export const scene = defineScene({
  "stage": 1,
  "id": "belmonte",
  "moves": [
    {
      "id": "app.go",
      "verb": "go",
      "class": "navigate",
      "args": [
        {
          "name": "page",
          "enum": [
            "home",
            "dining",
            "bar",
            "spa",
            "activities",
            "meetings",
            "requests",
            "visitors",
            "stay",
            "checkin",
            "checkout",
            "info"
          ]
        }
      ]
    },
    {
      "id": "app.show",
      "verb": "show",
      "class": "look",
      "args": [
        {
          "name": "target"
        }
      ]
    },
    {
      "id": "sheet.close",
      "class": "reversible"
    },
    {
      "id": "info.open",
      "class": "navigate",
      "args": [
        {
          "name": "topic",
          "enum": [
            "checkin",
            "house_rules",
            "quiet",
            "pets",
            "smoking",
            "pools",
            "wifi",
            "parking",
            "dining_hours",
            "fitness",
            "accessibility",
            "contact"
          ]
        }
      ]
    },
    {
      "id": "checkin.open",
      "class": "navigate",
      "args": [
        {
          "name": "step",
          "enum": [
            "reservation",
            "id",
            "room",
            "early",
            "review"
          ],
          "default": "reservation"
        }
      ]
    },
    {
      "id": "checkin.confirm",
      "class": "reversible"
    },
    {
      "id": "checkin.prefs",
      "class": "reversible",
      "args": [
        {
          "name": "arrival",
          "enum": [
            "now",
            "15:00",
            "16:00",
            "17:00",
            "19:00"
          ],
          "optional": true
        },
        {
          "name": "floor",
          "enum": [
            "high",
            "low",
            "any"
          ],
          "optional": true
        },
        {
          "name": "bed",
          "enum": [
            "king",
            "queens"
          ],
          "optional": true
        },
        {
          "name": "quiet",
          "enum": [
            "yes",
            "no"
          ],
          "optional": true
        }
      ]
    },
    {
      "id": "checkin.early",
      "class": "reversible",
      "args": [
        {
          "name": "want",
          "enum": [
            "yes",
            "no"
          ]
        }
      ]
    },
    {
      "id": "checkout.open",
      "class": "navigate",
      "args": [
        {
          "name": "part",
          "enum": [
            "folio",
            "late",
            "express"
          ],
          "default": "folio"
        }
      ]
    },
    {
      "id": "folio.dispute",
      "class": "reversible",
      "args": [
        {
          "name": "line_id"
        },
        {
          "name": "reason"
        },
        {
          "name": "send",
          "type": "boolean",
          "default": false
        }
      ]
    },
    {
      "id": "late.pick",
      "class": "reversible",
      "args": [
        {
          "name": "time",
          "enum": [
            "12:00",
            "13:00",
            "14:00",
            "16:00"
          ]
        }
      ]
    },
    {
      "id": "menu.open",
      "class": "navigate",
      "args": [
        {
          "name": "outlet",
          "enum": [
            "dining",
            "bar"
          ]
        },
        {
          "name": "section",
          "optional": true
        }
      ]
    },
    {
      "id": "menu.item",
      "class": "reversible",
      "args": [
        {
          "name": "outlet",
          "enum": [
            "dining",
            "bar"
          ]
        },
        {
          "name": "item_id"
        },
        {
          "name": "qty",
          "type": "integer",
          "default": 1
        },
        {
          "name": "choices",
          "type": "array",
          "optional": true
        },
        {
          "name": "note",
          "optional": true
        },
        {
          "name": "add",
          "type": "boolean",
          "default": true
        }
      ]
    },
    {
      "id": "cart.remove",
      "class": "reversible",
      "args": [
        {
          "name": "outlet",
          "enum": [
            "dining",
            "bar"
          ]
        },
        {
          "name": "item_id"
        }
      ]
    },
    {
      "id": "cart.open",
      "class": "navigate",
      "args": [
        {
          "name": "outlet",
          "enum": [
            "dining",
            "bar"
          ]
        },
        {
          "name": "tip",
          "type": "integer",
          "optional": true
        },
        {
          "name": "deliver_to",
          "enum": [
            "room",
            "cabana"
          ],
          "optional": true
        },
        {
          "name": "cabana",
          "optional": true
        }
      ]
    },
    {
      "id": "spa.open",
      "class": "navigate",
      "args": [
        {
          "name": "category",
          "enum": [
            "massage",
            "facial",
            "ritual",
            "nails"
          ],
          "optional": true
        }
      ]
    },
    {
      "id": "spa.treatment",
      "class": "navigate",
      "args": [
        {
          "name": "treatment_id"
        },
        {
          "name": "date",
          "optional": true
        },
        {
          "name": "therapist",
          "optional": true
        }
      ]
    },
    {
      "id": "spa.slot",
      "class": "reversible",
      "args": [
        {
          "name": "treatment_id"
        },
        {
          "name": "date"
        },
        {
          "name": "time"
        },
        {
          "name": "therapist_id"
        }
      ]
    },
    {
      "id": "activity.show",
      "class": "look",
      "args": [
        {
          "name": "activity_id"
        },
        {
          "name": "map",
          "type": "boolean",
          "default": false
        }
      ]
    },
    {
      "id": "activity.pick",
      "class": "reversible",
      "args": [
        {
          "name": "activity_id"
        },
        {
          "name": "date"
        },
        {
          "name": "time"
        },
        {
          "name": "guests",
          "type": "integer",
          "default": 1
        }
      ]
    },
    {
      "id": "meeting.filter",
      "class": "navigate",
      "args": [
        {
          "name": "headcount",
          "type": "integer",
          "optional": true
        },
        {
          "name": "layout",
          "enum": [
            "boardroom",
            "u_shape",
            "classroom",
            "theatre",
            "banquet"
          ],
          "optional": true
        },
        {
          "name": "date",
          "optional": true
        }
      ]
    },
    {
      "id": "meeting.pick",
      "class": "reversible",
      "args": [
        {
          "name": "room_id"
        },
        {
          "name": "date"
        },
        {
          "name": "block",
          "enum": [
            "morning",
            "afternoon",
            "full",
            "hours"
          ]
        },
        {
          "name": "start",
          "optional": true
        },
        {
          "name": "hours",
          "type": "integer",
          "optional": true
        },
        {
          "name": "headcount",
          "type": "integer"
        },
        {
          "name": "layout",
          "enum": [
            "boardroom",
            "u_shape",
            "classroom",
            "theatre",
            "banquet"
          ]
        },
        {
          "name": "catering",
          "type": "array",
          "optional": true
        },
        {
          "name": "av",
          "type": "array",
          "optional": true
        }
      ]
    },
    {
      "id": "visitor.open",
      "class": "reversible",
      "args": [
        {
          "name": "visitor_id"
        },
        {
          "name": "meet",
          "enum": [
            "room",
            "lobby"
          ],
          "optional": true
        }
      ]
    },
    {
      "id": "visitor.expect",
      "class": "reversible",
      "args": [
        {
          "name": "name"
        },
        {
          "name": "arrive_from"
        },
        {
          "name": "arrive_to"
        },
        {
          "name": "meet",
          "enum": [
            "room",
            "lobby"
          ],
          "optional": true
        },
        {
          "name": "note",
          "optional": true
        }
      ]
    },
    {
      "id": "request.fill",
      "class": "reversible",
      "args": [
        {
          "name": "kind",
          "enum": [
            "housekeeping",
            "maintenance",
            "wakeup",
            "valet",
            "transport",
            "lost_found"
          ]
        },
        {
          "name": "items",
          "type": "array",
          "optional": true
        },
        {
          "name": "issue",
          "optional": true
        },
        {
          "name": "option",
          "optional": true
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
          "name": "details",
          "optional": true
        },
        {
          "name": "send",
          "type": "boolean",
          "default": false
        }
      ]
    }
  ],
  "slices": [
    {
      "id": "stay",
      "fields": [
        {
          "name": "page",
          "optional": true
        },
        {
          "name": "scenario",
          "optional": true
        },
        {
          "name": "step",
          "optional": true
        },
        {
          "name": "field",
          "optional": true
        },
        {
          "name": "value",
          "optional": true
        },
        {
          "name": "id",
          "optional": true
        },
        {
          "name": "outlet",
          "optional": true
        },
        {
          "name": "qty",
          "type": "integer",
          "optional": true
        },
        {
          "name": "choices",
          "type": "array",
          "optional": true
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
          "name": "therapist",
          "optional": true
        },
        {
          "name": "guests",
          "type": "integer",
          "optional": true
        },
        {
          "name": "room",
          "optional": true
        },
        {
          "name": "kind",
          "optional": true
        },
        {
          "name": "total",
          "type": "number",
          "optional": true
        },
        {
          "name": "label",
          "optional": true
        }
      ]
    }
  ],
  "events": [
    {
      "id": "stay.page",
      "slice": "stay"
    },
    {
      "id": "stay.scenario",
      "slice": "stay"
    },
    {
      "id": "checkin.step",
      "slice": "stay"
    },
    {
      "id": "checkin.confirmed",
      "slice": "stay"
    },
    {
      "id": "checkin.id_verified",
      "slice": "stay"
    },
    {
      "id": "checkin.prefs",
      "slice": "stay"
    },
    {
      "id": "checkin.early",
      "slice": "stay"
    },
    {
      "id": "checkin.done",
      "slice": "stay"
    },
    {
      "id": "cart.changed",
      "slice": "stay"
    },
    {
      "id": "order.placed",
      "slice": "stay"
    },
    {
      "id": "spa.picked",
      "slice": "stay"
    },
    {
      "id": "spa.booked",
      "slice": "stay"
    },
    {
      "id": "activity.picked",
      "slice": "stay"
    },
    {
      "id": "activity.booked",
      "slice": "stay"
    },
    {
      "id": "meeting.picked",
      "slice": "stay"
    },
    {
      "id": "meeting.booked",
      "slice": "stay"
    },
    {
      "id": "visitor.decided",
      "slice": "stay"
    },
    {
      "id": "visitor.added",
      "slice": "stay"
    },
    {
      "id": "request.sent",
      "slice": "stay"
    },
    {
      "id": "folio.disputed",
      "slice": "stay"
    },
    {
      "id": "late.picked",
      "slice": "stay"
    },
    {
      "id": "late.requested",
      "slice": "stay"
    },
    {
      "id": "checkout.done",
      "slice": "stay"
    },
    {
      "id": "sheet.closed",
      "slice": "stay"
    }
  ]
});

export const SPEC_SHA256 = "eb0bd4926d2a85f340417c12d87d539967bcc51857462fde4a4b57e93dd6eb2a";
