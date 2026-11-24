// Generated from bank/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
//   voqalize stage gen bank/frontend/src/stage/scene.json --py bank/backend/stage_gen.py --ts bank/frontend/src/stage/scene.gen.ts
import { defineScene } from "@voqalize/stage";

/** The moves of global_bank, from its Stage Spec. */
export const scene = defineScene({
  "stage": 1,
  "id": "global_bank",
  "moves": [
    {
      "id": "ui.show",
      "verb": "show",
      "class": "look",
      "args": [
        {
          "name": "thing"
        }
      ]
    },
    {
      "id": "nav.open",
      "class": "navigate",
      "args": [
        {
          "name": "screen",
          "enum": [
            "home",
            "login",
            "dashboard",
            "account",
            "transactions",
            "insights",
            "cards_hub",
            "debit_card",
            "credit_card",
            "payments",
            "bills",
            "deposits",
            "statements",
            "offers",
            "open_account",
            "cards",
            "card_detail",
            "cards_compare",
            "cards_apply",
            "cards_emi",
            "loans",
            "loan",
            "loan_apply"
          ]
        },
        {
          "name": "id",
          "optional": true
        }
      ]
    },
    {
      "id": "accounts.show",
      "class": "look",
      "args": [
        {
          "name": "account",
          "enum": [
            "sb",
            "ca"
          ],
          "optional": true
        }
      ]
    },
    {
      "id": "txn.find",
      "class": "reversible",
      "args": [
        {
          "name": "account",
          "enum": [
            "all",
            "bank",
            "sb",
            "ca",
            "cc"
          ],
          "optional": true
        },
        {
          "name": "category",
          "optional": true
        },
        {
          "name": "query",
          "optional": true
        },
        {
          "name": "from_days_ago",
          "type": "integer",
          "optional": true
        },
        {
          "name": "to_days_ago",
          "type": "integer",
          "optional": true
        },
        {
          "name": "min_amount",
          "type": "number",
          "optional": true
        },
        {
          "name": "max_amount",
          "type": "number",
          "optional": true
        },
        {
          "name": "direction",
          "enum": [
            "any",
            "debit",
            "credit"
          ],
          "optional": true
        },
        {
          "name": "label",
          "optional": true
        }
      ]
    },
    {
      "id": "txn.open",
      "class": "look",
      "args": [
        {
          "name": "txn_id"
        }
      ]
    },
    {
      "id": "insights.show",
      "class": "look",
      "args": [
        {
          "name": "month"
        },
        {
          "name": "category",
          "optional": true
        }
      ]
    },
    {
      "id": "confirm.ask",
      "class": "reversible",
      "args": [
        {
          "name": "action_id"
        },
        {
          "name": "kind",
          "enum": [
            "card_block",
            "card_unblock",
            "card_control",
            "card_limit",
            "bill_pay",
            "transfer",
            "fd_book",
            "emi_convert",
            "offer_accept"
          ]
        },
        {
          "name": "card",
          "enum": [
            "debit",
            "credit"
          ],
          "optional": true
        },
        {
          "name": "control",
          "enum": [
            "international",
            "online",
            "contactless",
            "atm",
            "atm_daily",
            "pos_daily",
            "online_daily"
          ],
          "optional": true
        },
        {
          "name": "value",
          "optional": true
        },
        {
          "name": "amount",
          "type": "number",
          "optional": true
        },
        {
          "name": "target",
          "optional": true
        },
        {
          "name": "from_account",
          "enum": [
            "sb",
            "ca"
          ],
          "optional": true
        },
        {
          "name": "tenure_months",
          "type": "integer",
          "optional": true
        },
        {
          "name": "payout",
          "enum": [
            "cumulative",
            "monthly",
            "quarterly"
          ],
          "optional": true
        }
      ]
    },
    {
      "id": "confirm.answer",
      "class": "confirmed",
      "args": [
        {
          "name": "action_id"
        },
        {
          "name": "yes",
          "type": "boolean"
        }
      ]
    },
    {
      "id": "form.fill",
      "class": "reversible",
      "args": [
        {
          "name": "form",
          "enum": [
            "open_account",
            "card_apply",
            "loan_apply"
          ]
        },
        {
          "name": "field"
        },
        {
          "name": "value"
        }
      ]
    },
    {
      "id": "form.step",
      "class": "navigate",
      "args": [
        {
          "name": "form",
          "enum": [
            "open_account",
            "card_apply",
            "loan_apply"
          ]
        },
        {
          "name": "step",
          "type": "integer"
        }
      ]
    },
    {
      "id": "form.submit",
      "class": "confirmed",
      "args": [
        {
          "name": "form",
          "enum": [
            "open_account",
            "card_apply",
            "loan_apply"
          ]
        }
      ]
    },
    {
      "id": "cards.compare",
      "class": "look",
      "args": [
        {
          "name": "card_ids",
          "type": "array"
        },
        {
          "name": "dining",
          "type": "integer",
          "optional": true
        },
        {
          "name": "online",
          "type": "integer",
          "optional": true
        },
        {
          "name": "groceries",
          "type": "integer",
          "optional": true
        },
        {
          "name": "travel",
          "type": "integer",
          "optional": true
        },
        {
          "name": "fuel",
          "type": "integer",
          "optional": true
        },
        {
          "name": "utilities",
          "type": "integer",
          "optional": true
        },
        {
          "name": "other",
          "type": "integer",
          "optional": true
        }
      ]
    },
    {
      "id": "emi.plan",
      "class": "reversible",
      "args": [
        {
          "name": "txn_id",
          "optional": true
        },
        {
          "name": "amount",
          "type": "number",
          "optional": true
        },
        {
          "name": "tenure_months",
          "type": "integer"
        }
      ]
    },
    {
      "id": "loan.calc",
      "class": "reversible",
      "args": [
        {
          "name": "loan_type",
          "enum": [
            "home",
            "personal",
            "gold",
            "car"
          ]
        },
        {
          "name": "amount",
          "type": "number"
        },
        {
          "name": "tenure_months",
          "type": "integer"
        },
        {
          "name": "rate",
          "type": "number",
          "optional": true
        }
      ]
    },
    {
      "id": "loan.eligibility",
      "class": "reversible",
      "args": [
        {
          "name": "loan_type",
          "enum": [
            "home",
            "personal",
            "gold",
            "car"
          ]
        },
        {
          "name": "monthly_income",
          "type": "number",
          "optional": true
        },
        {
          "name": "existing_emis",
          "type": "number",
          "optional": true
        },
        {
          "name": "tenure_months",
          "type": "integer",
          "optional": true
        },
        {
          "name": "gold_grams",
          "type": "number",
          "optional": true
        }
      ]
    }
  ]
});

export const SPEC_SHA256 = "85f59443fd9ee99ebe6d59103c23a9a7b4f5ae382f465081580423df37127d3b";
