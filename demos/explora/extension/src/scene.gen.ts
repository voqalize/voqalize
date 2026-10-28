// Generated from explora/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
//   voqalize stage gen explora/scene.json --py explora/backend/stage_gen.py --ts explora/extension/src/scene.gen.ts
import { defineScene } from "@voqalize/stage";

/** The moves of explora, from its Stage Spec. */
export const scene = defineScene({
  "stage": 1,
  "id": "explora",
  "moves": [
    {
      "id": "core.show",
      "verb": "show",
      "class": "look",
      "args": [
        {
          "name": "target"
        }
      ]
    },
    {
      "id": "core.faq",
      "verb": "faq",
      "class": "look",
      "args": [
        {
          "name": "question"
        }
      ]
    },
    {
      "id": "explora.navigate",
      "class": "navigate",
      "args": [
        {
          "name": "path"
        },
        {
          "name": "after_words",
          "type": "integer",
          "optional": true
        }
      ]
    },
    {
      "id": "explora.twin",
      "class": "navigate",
      "args": [
        {
          "name": "language",
          "enum": [
            "en",
            "es"
          ]
        }
      ]
    },
    {
      "id": "explora.check_availability",
      "class": "reversible",
      "args": [
        {
          "name": "hotel_code"
        },
        {
          "name": "date",
          "optional": true
        },
        {
          "name": "month",
          "optional": true
        },
        {
          "name": "nights",
          "type": "integer",
          "optional": true
        },
        {
          "name": "rooms",
          "type": "boolean",
          "optional": true
        },
        {
          "name": "language",
          "enum": [
            "EN",
            "ES"
          ],
          "optional": true
        }
      ]
    },
    {
      "id": "explora.choose_room",
      "class": "reversible",
      "args": [
        {
          "name": "room"
        },
        {
          "name": "travellers",
          "type": "integer",
          "optional": true
        },
        {
          "name": "bed",
          "optional": true
        },
        {
          "name": "count",
          "type": "integer",
          "optional": true
        }
      ]
    },
    {
      "id": "explora.fill_enquiry",
      "class": "reversible",
      "args": [
        {
          "name": "expedition_code"
        },
        {
          "name": "title",
          "optional": true
        },
        {
          "name": "first_name",
          "optional": true
        },
        {
          "name": "last_name",
          "optional": true
        },
        {
          "name": "email",
          "optional": true
        },
        {
          "name": "phone",
          "optional": true
        },
        {
          "name": "country",
          "optional": true
        },
        {
          "name": "message",
          "optional": true
        },
        {
          "name": "language",
          "enum": [
            "EN",
            "ES"
          ],
          "optional": true
        }
      ]
    },
    {
      "id": "explora.send_enquiry",
      "class": "confirmed"
    },
    {
      "id": "explora.focus_tab",
      "class": "look",
      "args": [
        {
          "name": "tab_id"
        }
      ]
    }
  ]
});

export const SPEC_SHA256 = "9001cb7b62eac15b24dbc1a537b93ac3f817f975d69634b8b35d1afe8f7029db";
