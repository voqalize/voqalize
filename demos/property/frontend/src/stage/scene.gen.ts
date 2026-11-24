// Generated from demos/property/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
//   voqalize stage gen demos/property/frontend/src/stage/scene.json --py demos/property/backend/stage_gen.py --ts demos/property/frontend/src/stage/scene.gen.ts
import { defineScene } from "@voqalize/stage";

/** The moves of kosha_homes, from its Stage Spec. */
export const scene = defineScene({
  "stage": 1,
  "id": "kosha_homes",
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
      "id": "listings.filter",
      "class": "reversible",
      "args": [
        {
          "name": "city",
          "enum": [
            "bengaluru",
            "pune",
            "hyderabad"
          ],
          "optional": true
        },
        {
          "name": "deal",
          "enum": [
            "buy",
            "rent"
          ],
          "optional": true
        },
        {
          "name": "bhk",
          "type": "array",
          "optional": true
        },
        {
          "name": "budget_min",
          "type": "integer",
          "optional": true
        },
        {
          "name": "budget_max",
          "type": "integer",
          "optional": true
        },
        {
          "name": "possession",
          "enum": [
            "ready",
            "under_construction"
          ],
          "optional": true
        },
        {
          "name": "localities",
          "type": "array",
          "optional": true
        },
        {
          "name": "office",
          "optional": true
        },
        {
          "name": "max_km",
          "type": "number",
          "optional": true
        },
        {
          "name": "school_km",
          "type": "number",
          "optional": true
        },
        {
          "name": "metro_km",
          "type": "number",
          "optional": true
        },
        {
          "name": "amenities",
          "type": "array",
          "optional": true
        }
      ]
    },
    {
      "id": "listings.show",
      "verb": "show",
      "class": "look",
      "args": [
        {
          "name": "listing_id"
        }
      ]
    },
    {
      "id": "compare.show",
      "class": "navigate",
      "args": [
        {
          "name": "ids",
          "type": "array"
        }
      ]
    },
    {
      "id": "emi.show",
      "class": "reversible",
      "args": [
        {
          "name": "listing_id"
        },
        {
          "name": "down_pct",
          "type": "number",
          "optional": true
        },
        {
          "name": "tenure_years",
          "type": "integer",
          "optional": true
        },
        {
          "name": "lender",
          "optional": true
        }
      ]
    },
    {
      "id": "shortlist.set",
      "class": "reversible",
      "args": [
        {
          "name": "listing_id"
        },
        {
          "name": "on",
          "type": "boolean",
          "default": true
        }
      ]
    },
    {
      "id": "visit.slots",
      "class": "look",
      "args": [
        {
          "name": "listing_id"
        },
        {
          "name": "day"
        },
        {
          "name": "part",
          "enum": [
            "morning",
            "afternoon",
            "evening",
            "any"
          ],
          "optional": true
        }
      ]
    },
    {
      "id": "visit.fill",
      "class": "reversible",
      "args": [
        {
          "name": "listing_id"
        },
        {
          "name": "slot"
        },
        {
          "name": "name"
        },
        {
          "name": "visitors",
          "type": "integer",
          "default": 1
        }
      ]
    },
    {
      "id": "visit.book",
      "class": "confirmed",
      "args": [
        {
          "name": "listing_id"
        },
        {
          "name": "slot"
        },
        {
          "name": "name"
        },
        {
          "name": "visitors",
          "type": "integer",
          "default": 1
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
          "name": "page"
        },
        {
          "name": "listing_id",
          "optional": true
        },
        {
          "name": "title",
          "optional": true
        }
      ]
    },
    {
      "id": "search",
      "fields": [
        {
          "name": "summary"
        },
        {
          "name": "count",
          "type": "integer"
        },
        {
          "name": "city",
          "optional": true
        },
        {
          "name": "deal",
          "optional": true
        },
        {
          "name": "bhk",
          "type": "array",
          "items": {
            "type": "integer"
          },
          "optional": true
        },
        {
          "name": "budget_min",
          "type": "integer",
          "optional": true
        },
        {
          "name": "budget_max",
          "type": "integer",
          "optional": true
        },
        {
          "name": "possession",
          "optional": true
        },
        {
          "name": "localities",
          "type": "array",
          "optional": true
        },
        {
          "name": "office",
          "optional": true
        },
        {
          "name": "max_km",
          "type": "number",
          "optional": true
        },
        {
          "name": "school_km",
          "type": "number",
          "optional": true
        },
        {
          "name": "metro_km",
          "type": "number",
          "optional": true
        },
        {
          "name": "amenities",
          "type": "array",
          "optional": true
        },
        {
          "name": "ids",
          "type": "array",
          "optional": true
        }
      ]
    },
    {
      "id": "shortlist",
      "fields": [
        {
          "name": "count",
          "type": "integer"
        },
        {
          "name": "ids",
          "type": "array"
        }
      ]
    },
    {
      "id": "visit",
      "fields": [
        {
          "name": "listing_id"
        },
        {
          "name": "slot",
          "optional": true
        },
        {
          "name": "reference",
          "optional": true
        },
        {
          "name": "typed",
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
      "id": "search.changed",
      "slice": "search",
      "op": "set"
    },
    {
      "id": "shortlist.changed",
      "slice": "shortlist",
      "op": "set"
    },
    {
      "id": "visit.slot_picked",
      "slice": "visit"
    },
    {
      "id": "visit.phone_typed",
      "slice": "visit"
    },
    {
      "id": "visit.booked",
      "slice": "visit",
      "op": "set"
    }
  ]
});

export const SPEC_SHA256 = "0cb6a031857eb735084c07602b706dc8fd1bfd43ec2135ce3b7f92ecba4f4b73";
