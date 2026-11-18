// Generated from insurance/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
//   voqalize stage gen insurance/frontend/src/stage/scene.json --py insurance/backend/stage_gen.py --ts insurance/frontend/src/stage/scene.gen.ts
import { defineScene } from "@voqalize/stage";

/** The moves of chhatri_insurance, from its Stage Spec. */
export const scene = defineScene({
  "stage": 1,
  "id": "chhatri_insurance",
  "moves": [
    {
      "id": "site.go",
      "class": "navigate",
      "args": [
        {
          "name": "page"
        }
      ]
    },
    {
      "id": "site.language",
      "class": "reversible",
      "args": [
        {
          "name": "language"
        }
      ]
    },
    {
      "id": "quote.open",
      "class": "navigate",
      "args": [
        {
          "name": "product",
          "enum": [
            "car",
            "bike",
            "health",
            "term",
            "home",
            "travel"
          ]
        }
      ]
    },
    {
      "id": "quote.fill",
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
      "id": "quote.addon",
      "class": "reversible",
      "args": [
        {
          "name": "addon"
        },
        {
          "name": "on",
          "type": "boolean"
        }
      ]
    },
    {
      "id": "quote.show",
      "class": "look"
    },
    {
      "id": "policy.open",
      "class": "navigate",
      "args": [
        {
          "name": "policy_id"
        },
        {
          "name": "section",
          "optional": true
        }
      ]
    },
    {
      "id": "policy.mark",
      "class": "look",
      "args": [
        {
          "name": "policy_id"
        },
        {
          "name": "clause_id"
        },
        {
          "name": "verdict",
          "enum": [
            "covered",
            "not_covered",
            "covered_with_limits",
            "depends"
          ]
        }
      ]
    },
    {
      "id": "claim.start",
      "class": "reversible",
      "args": [
        {
          "name": "claim_type",
          "enum": [
            "motor",
            "health"
          ]
        },
        {
          "name": "policy_id",
          "optional": true
        }
      ]
    },
    {
      "id": "claim.fill",
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
      "id": "claim.section",
      "class": "look",
      "args": [
        {
          "name": "section"
        }
      ]
    },
    {
      "id": "claim.review",
      "class": "reversible"
    }
  ],
  "slices": [
    {
      "id": "quote",
      "fields": [
        {
          "name": "product",
          "optional": true
        },
        {
          "name": "field",
          "optional": true
        },
        {
          "name": "answers",
          "type": "array",
          "fields": [
            {
              "name": "field"
            },
            {
              "name": "value"
            }
          ]
        },
        {
          "name": "addons",
          "type": "array"
        },
        {
          "name": "missing",
          "type": "array"
        },
        {
          "name": "total",
          "type": "integer",
          "optional": true
        }
      ]
    },
    {
      "id": "policy_view",
      "fields": [
        {
          "name": "policy_id",
          "optional": true
        },
        {
          "name": "section",
          "optional": true
        }
      ]
    },
    {
      "id": "claim_form",
      "fields": [
        {
          "name": "claim_type",
          "optional": true
        },
        {
          "name": "policy_id",
          "optional": true
        },
        {
          "name": "section",
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
          "name": "documents",
          "type": "array"
        },
        {
          "name": "reference",
          "optional": true
        }
      ]
    },
    {
      "id": "site",
      "fields": [
        {
          "name": "language",
          "optional": true
        }
      ]
    }
  ],
  "events": [
    {
      "id": "quote.changed",
      "slice": "quote",
      "op": "set"
    },
    {
      "id": "policy.viewed",
      "slice": "policy_view",
      "op": "set"
    },
    {
      "id": "claim.changed",
      "slice": "claim_form"
    },
    {
      "id": "claim.document_uploaded",
      "slice": "claim_form"
    },
    {
      "id": "claim.submitted",
      "slice": "claim_form"
    },
    {
      "id": "site.language_chosen",
      "slice": "site",
      "op": "set"
    }
  ]
});

export const SPEC_SHA256 = "53a37187127da92aa6770e7ae44a3488b427b5807e40ba774bba3ee9364fd7a6";
