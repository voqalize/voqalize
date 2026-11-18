// Generated from university/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
//   voqalize stage gen university/frontend/src/stage/scene.json --py university/backend/stage_gen.py --ts university/frontend/src/stage/scene.gen.ts
import { defineScene } from "@voqalize/stage";

/** The moves of varenya_university, from its Stage Spec. */
export const scene = defineScene({
  "stage": 1,
  "id": "varenya_university",
  "moves": [
    {
      "id": "catalogue.filter",
      "verb": "filter",
      "class": "reversible",
      "args": [
        {
          "name": "facet"
        },
        {
          "name": "value"
        }
      ]
    },
    {
      "id": "catalogue.clear",
      "verb": "clear",
      "class": "reversible",
      "args": [
        {
          "name": "facet",
          "optional": true
        }
      ]
    },
    {
      "id": "catalogue.pick",
      "verb": "pick",
      "class": "reversible",
      "args": [
        {
          "name": "first"
        },
        {
          "name": "second",
          "optional": true
        },
        {
          "name": "third",
          "optional": true
        }
      ]
    },
    {
      "id": "catalogue.compare",
      "verb": "compare",
      "class": "look",
      "args": [
        {
          "name": "first"
        },
        {
          "name": "second"
        },
        {
          "name": "third",
          "optional": true
        }
      ]
    },
    {
      "id": "site.open",
      "verb": "open",
      "class": "navigate",
      "args": [
        {
          "name": "program"
        }
      ]
    },
    {
      "id": "site.go",
      "verb": "go",
      "class": "navigate",
      "args": [
        {
          "name": "page"
        }
      ]
    },
    {
      "id": "site.show",
      "verb": "show",
      "class": "look",
      "args": [
        {
          "name": "target"
        }
      ]
    },
    {
      "id": "apply.fill",
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
      "id": "apply.step",
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
      "id": "apply.next",
      "verb": "next",
      "class": "reversible"
    }
  ],
  "slices": [
    {
      "id": "catalogue",
      "fields": [
        {
          "name": "filters",
          "type": "array"
        },
        {
          "name": "count",
          "type": "integer"
        },
        {
          "name": "top",
          "type": "array"
        },
        {
          "name": "picks",
          "type": "array"
        },
        {
          "name": "compared",
          "type": "array"
        }
      ]
    },
    {
      "id": "application",
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
          "name": "missing",
          "type": "array"
        },
        {
          "name": "program",
          "optional": true
        },
        {
          "name": "campus",
          "optional": true
        },
        {
          "name": "intake",
          "optional": true
        },
        {
          "name": "class12_stream",
          "optional": true
        },
        {
          "name": "class12_percent",
          "optional": true
        },
        {
          "name": "graduation_percent",
          "optional": true
        },
        {
          "name": "entrance_exam",
          "optional": true
        },
        {
          "name": "hostel",
          "optional": true
        },
        {
          "name": "room_type",
          "optional": true
        },
        {
          "name": "scholarship",
          "optional": true
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
      "id": "catalogue.changed",
      "slice": "catalogue",
      "op": "set"
    },
    {
      "id": "application.changed",
      "slice": "application"
    },
    {
      "id": "application.step_reached",
      "slice": "application"
    },
    {
      "id": "application.submitted",
      "slice": "application"
    }
  ]
});

export const SPEC_SHA256 = "05631922ba54c020208467a6d7ae7a348abadbce3e08a61ab11cb2aa74c89223";
