// Generated from holidays/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
//   voqalize stage gen holidays/frontend/src/stage/scene.json --py holidays/backend/stage_gen.py --ts holidays/frontend/src/stage/scene.gen.ts
import { defineScene } from "@voqalize/stage";

/** The moves of wanderloom, from its Stage Spec. */
export const scene = defineScene({
  "stage": 1,
  "id": "wanderloom",
  "moves": [
    {
      "id": "trip.go",
      "verb": "go",
      "class": "navigate",
      "args": [
        {
          "name": "page",
          "enum": [
            "home",
            "plan",
            "checkout"
          ]
        }
      ]
    },
    {
      "id": "trip.step",
      "verb": "step",
      "class": "navigate",
      "args": [
        {
          "name": "step",
          "enum": [
            "brief",
            "flights",
            "hotels",
            "days",
            "package"
          ]
        }
      ]
    },
    {
      "id": "trip.show",
      "verb": "show",
      "class": "look",
      "args": [
        {
          "name": "target"
        }
      ]
    },
    {
      "id": "trip.brief",
      "class": "reversible",
      "args": [
        {
          "name": "from_city",
          "optional": true
        },
        {
          "name": "destination",
          "optional": true
        },
        {
          "name": "start_date",
          "optional": true
        },
        {
          "name": "nights",
          "type": "integer",
          "optional": true
        },
        {
          "name": "adults",
          "type": "integer",
          "optional": true
        },
        {
          "name": "kids",
          "type": "array",
          "optional": true
        },
        {
          "name": "budget",
          "type": "integer",
          "optional": true
        },
        {
          "name": "style",
          "enum": [
            "relaxed",
            "adventure",
            "honeymoon",
            "family"
          ],
          "optional": true
        }
      ]
    },
    {
      "id": "trip.flights",
      "class": "navigate",
      "args": [
        {
          "name": "sort",
          "enum": [
            "recommended",
            "price",
            "duration",
            "departure"
          ],
          "default": "recommended"
        }
      ]
    },
    {
      "id": "trip.flight",
      "class": "reversible",
      "args": [
        {
          "name": "flight_id"
        }
      ]
    },
    {
      "id": "trip.hotels",
      "class": "navigate",
      "args": [
        {
          "name": "city"
        },
        {
          "name": "want",
          "optional": true
        }
      ]
    },
    {
      "id": "trip.hotel",
      "class": "reversible",
      "args": [
        {
          "name": "city"
        },
        {
          "name": "hotel_id"
        },
        {
          "name": "room_id"
        }
      ]
    },
    {
      "id": "trip.nights",
      "class": "reversible",
      "args": [
        {
          "name": "split",
          "type": "array"
        }
      ]
    },
    {
      "id": "trip.add",
      "class": "reversible",
      "args": [
        {
          "name": "activity_id"
        },
        {
          "name": "day",
          "type": "integer"
        }
      ]
    },
    {
      "id": "trip.remove",
      "class": "reversible",
      "args": [
        {
          "name": "activity_id"
        },
        {
          "name": "day",
          "type": "integer"
        }
      ]
    },
    {
      "id": "trip.build",
      "class": "reversible",
      "args": [
        {
          "name": "flight_id"
        },
        {
          "name": "hotels",
          "type": "array"
        },
        {
          "name": "activities",
          "type": "array"
        }
      ]
    }
  ],
  "slices": [
    {
      "id": "trip",
      "fields": [
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
          "name": "flight_id",
          "optional": true
        },
        {
          "name": "city",
          "optional": true
        },
        {
          "name": "hotel_id",
          "optional": true
        },
        {
          "name": "room_id",
          "optional": true
        },
        {
          "name": "split",
          "type": "array",
          "items": {
            "type": "integer"
          },
          "optional": true
        },
        {
          "name": "activity_id",
          "optional": true
        },
        {
          "name": "day",
          "type": "integer",
          "optional": true
        },
        {
          "name": "label",
          "optional": true
        },
        {
          "name": "total",
          "type": "integer",
          "optional": true
        },
        {
          "name": "reference",
          "optional": true
        },
        {
          "name": "page",
          "optional": true
        }
      ]
    }
  ],
  "events": [
    {
      "id": "trip.brief_changed",
      "slice": "trip"
    },
    {
      "id": "trip.flight_picked",
      "slice": "trip"
    },
    {
      "id": "trip.hotel_picked",
      "slice": "trip"
    },
    {
      "id": "trip.nights_changed",
      "slice": "trip"
    },
    {
      "id": "trip.activity_added",
      "slice": "trip"
    },
    {
      "id": "trip.activity_removed",
      "slice": "trip"
    },
    {
      "id": "trip.step_changed",
      "slice": "trip"
    },
    {
      "id": "trip.page_changed",
      "slice": "trip"
    },
    {
      "id": "trip.paid",
      "slice": "trip"
    }
  ]
});

export const SPEC_SHA256 = "aad631e27d5f72b50d7c34911f0b1d742d3ab8da9c089caad7a473cf775d6998";
