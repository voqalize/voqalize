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
  ],
  "slices": [
    {
      "id": "page",
      "fields": [
        {
          "name": "site",
          "enum": [
            "site",
            "reservations"
          ],
          "optional": true
        },
        {
          "name": "url",
          "optional": true
        },
        {
          "name": "path"
        },
        {
          "name": "title",
          "optional": true
        },
        {
          "name": "headings",
          "type": "array",
          "optional": true
        },
        {
          "name": "faqs",
          "type": "array",
          "optional": true
        },
        {
          "name": "tabs",
          "type": "array",
          "optional": true
        },
        {
          "name": "links",
          "type": "array",
          "optional": true
        }
      ]
    },
    {
      "id": "stay",
      "fields": [
        {
          "name": "step",
          "enum": [
            "dates",
            "rooms"
          ]
        },
        {
          "name": "hotel_code",
          "optional": true
        },
        {
          "name": "hotel",
          "optional": true
        },
        {
          "name": "month",
          "optional": true
        },
        {
          "name": "open_days",
          "type": "array",
          "optional": true
        },
        {
          "name": "date",
          "optional": true
        },
        {
          "name": "nights",
          "type": "array",
          "fields": [
            {
              "name": "nights",
              "type": "integer"
            },
            {
              "name": "label"
            }
          ],
          "optional": true
        },
        {
          "name": "chosen_nights",
          "type": "integer",
          "optional": true
        },
        {
          "name": "rooms",
          "type": "array",
          "fields": [
            {
              "name": "name"
            },
            {
              "name": "text"
            }
          ],
          "optional": true
        }
      ]
    },
    {
      "id": "enquiry",
      "fields": [
        {
          "name": "expedition",
          "optional": true
        },
        {
          "name": "expedition_code",
          "optional": true
        },
        {
          "name": "filled",
          "type": "array",
          "optional": true
        },
        {
          "name": "missing",
          "type": "array",
          "optional": true
        },
        {
          "name": "captcha",
          "type": "boolean",
          "optional": true
        }
      ]
    }
  ],
  "events": [
    {
      "id": "page.changed",
      "slice": "page",
      "op": "set"
    },
    {
      "id": "stay.changed",
      "slice": "stay",
      "op": "set"
    },
    {
      "id": "enquiry.changed",
      "slice": "enquiry",
      "op": "set"
    }
  ]
});

export const SPEC_SHA256 = "a830ff3608259b71f70fb7ad4fbefd99ae79b80989302c941fa09c3f1c839cbd";
