// Generated from demos/fashio/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
//   voqalize stage gen demos/fashio/frontend/src/stage/scene.json --py demos/fashio/backend/stage_gen.py --ts demos/fashio/frontend/src/stage/scene.gen.ts
import { defineScene } from "@voqalize/stage";

/** The moves of fashio, from its Stage Spec. */
export const scene = defineScene({
  "stage": 1,
  "id": "fashio",
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
      "id": "shop.filter",
      "class": "reversible",
      "args": [
        {
          "name": "dept",
          "enum": [
            "men",
            "women",
            "kids",
            "boys",
            "girls",
            "ethnic",
            "footwear",
            "accessories",
            "all"
          ],
          "optional": true
        },
        {
          "name": "types",
          "type": "array",
          "optional": true
        },
        {
          "name": "brands",
          "type": "array",
          "optional": true
        },
        {
          "name": "colours",
          "type": "array",
          "optional": true
        },
        {
          "name": "sizes",
          "type": "array",
          "optional": true
        },
        {
          "name": "price_min",
          "type": "integer",
          "optional": true
        },
        {
          "name": "price_max",
          "type": "integer",
          "optional": true
        },
        {
          "name": "discount_min",
          "type": "integer",
          "optional": true
        },
        {
          "name": "usage",
          "type": "array",
          "optional": true
        },
        {
          "name": "seasons",
          "type": "array",
          "optional": true
        },
        {
          "name": "query",
          "optional": true
        },
        {
          "name": "sort",
          "enum": [
            "popular",
            "price_asc",
            "price_desc",
            "discount",
            "new"
          ],
          "optional": true
        }
      ]
    },
    {
      "id": "shop.show",
      "verb": "show",
      "class": "look",
      "args": [
        {
          "name": "product_id"
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
      "id": "product.size",
      "class": "reversible",
      "args": [
        {
          "name": "product_id"
        },
        {
          "name": "size"
        }
      ]
    },
    {
      "id": "size_chart.open",
      "class": "look",
      "args": [
        {
          "name": "product_id"
        },
        {
          "name": "size",
          "optional": true
        }
      ]
    },
    {
      "id": "fit.fill",
      "class": "reversible",
      "args": [
        {
          "name": "product_id"
        },
        {
          "name": "height_cm",
          "type": "integer",
          "optional": true
        },
        {
          "name": "usual_size",
          "optional": true
        },
        {
          "name": "fit",
          "enum": [
            "snug",
            "regular",
            "relaxed"
          ],
          "optional": true
        }
      ]
    },
    {
      "id": "fit.recommend",
      "class": "reversible",
      "args": [
        {
          "name": "product_id"
        },
        {
          "name": "size"
        },
        {
          "name": "reason"
        },
        {
          "name": "wanted",
          "optional": true
        }
      ]
    },
    {
      "id": "wishlist.set",
      "class": "reversible",
      "args": [
        {
          "name": "product_id"
        },
        {
          "name": "on",
          "type": "boolean",
          "default": true
        }
      ]
    },
    {
      "id": "bag.add",
      "class": "confirmed",
      "args": [
        {
          "name": "product_id"
        },
        {
          "name": "size"
        },
        {
          "name": "qty",
          "type": "integer",
          "default": 1
        }
      ]
    },
    {
      "id": "bag.gift",
      "class": "reversible",
      "args": [
        {
          "name": "product_id"
        },
        {
          "name": "size"
        },
        {
          "name": "on",
          "type": "boolean",
          "default": true
        },
        {
          "name": "note",
          "optional": true
        }
      ]
    },
    {
      "id": "checkout.focus",
      "class": "look",
      "args": [
        {
          "name": "field",
          "enum": [
            "contact",
            "address",
            "payment",
            "place"
          ]
        }
      ]
    },
    {
      "id": "gifts.brief",
      "class": "reversible",
      "args": [
        {
          "name": "recipient",
          "optional": true
        },
        {
          "name": "occasion",
          "optional": true
        },
        {
          "name": "budget_max",
          "type": "integer",
          "optional": true
        },
        {
          "name": "size",
          "optional": true
        },
        {
          "name": "colours",
          "type": "array",
          "optional": true
        },
        {
          "name": "patterns",
          "type": "array",
          "optional": true
        },
        {
          "name": "material",
          "optional": true
        }
      ]
    },
    {
      "id": "gifts.show",
      "class": "reversible",
      "args": [
        {
          "name": "ids",
          "type": "array"
        },
        {
          "name": "reasons",
          "type": "array"
        }
      ]
    },
    {
      "id": "orders.open",
      "class": "navigate",
      "args": [
        {
          "name": "order_id"
        }
      ]
    },
    {
      "id": "orders.cancel_open",
      "class": "look",
      "args": [
        {
          "name": "order_id"
        }
      ]
    },
    {
      "id": "returns.fill",
      "class": "reversible",
      "args": [
        {
          "name": "order_id"
        },
        {
          "name": "product_id",
          "optional": true
        },
        {
          "name": "reason",
          "enum": [
            "size_small",
            "size_large",
            "not_as_pictured",
            "quality",
            "changed_mind",
            "damaged",
            "wrong_item"
          ],
          "optional": true
        },
        {
          "name": "unused",
          "type": "boolean",
          "optional": true
        },
        {
          "name": "tags",
          "type": "boolean",
          "optional": true
        }
      ]
    },
    {
      "id": "kiosk.search",
      "class": "reversible",
      "args": [
        {
          "name": "query",
          "optional": true
        },
        {
          "name": "genders",
          "type": "array",
          "optional": true
        },
        {
          "name": "types",
          "type": "array",
          "optional": true
        },
        {
          "name": "colours",
          "type": "array",
          "optional": true
        },
        {
          "name": "sizes",
          "type": "array",
          "optional": true
        },
        {
          "name": "price_max",
          "type": "integer",
          "optional": true
        },
        {
          "name": "usage",
          "type": "array",
          "optional": true
        }
      ]
    },
    {
      "id": "kiosk.show",
      "class": "look",
      "args": [
        {
          "name": "product_id"
        }
      ]
    },
    {
      "id": "kiosk.qr",
      "class": "look",
      "args": [
        {
          "name": "product_id",
          "optional": true
        }
      ]
    },
    {
      "id": "kiosk.shortlist",
      "class": "reversible",
      "args": [
        {
          "name": "product_id"
        },
        {
          "name": "on",
          "type": "boolean",
          "default": true
        }
      ]
    },
    {
      "id": "kiosk.assist",
      "class": "reversible"
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
          "name": "product_id",
          "optional": true
        },
        {
          "name": "order_id",
          "optional": true
        },
        {
          "name": "title",
          "optional": true
        }
      ]
    },
    {
      "id": "shop",
      "fields": [
        {
          "name": "summary"
        },
        {
          "name": "count",
          "type": "integer"
        },
        {
          "name": "dept",
          "optional": true
        },
        {
          "name": "types",
          "type": "array",
          "optional": true
        },
        {
          "name": "brands",
          "type": "array",
          "optional": true
        },
        {
          "name": "colours",
          "type": "array",
          "optional": true
        },
        {
          "name": "sizes",
          "type": "array",
          "optional": true
        },
        {
          "name": "price_min",
          "type": "integer",
          "optional": true
        },
        {
          "name": "price_max",
          "type": "integer",
          "optional": true
        },
        {
          "name": "discount_min",
          "type": "integer",
          "optional": true
        },
        {
          "name": "usage",
          "type": "array",
          "optional": true
        },
        {
          "name": "seasons",
          "type": "array",
          "optional": true
        },
        {
          "name": "query",
          "optional": true
        },
        {
          "name": "sort",
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
      "id": "product",
      "fields": [
        {
          "name": "product_id"
        },
        {
          "name": "size",
          "optional": true
        },
        {
          "name": "height_cm",
          "type": "integer",
          "optional": true
        },
        {
          "name": "usual_size",
          "optional": true
        },
        {
          "name": "fit",
          "optional": true
        }
      ]
    },
    {
      "id": "bag",
      "fields": [
        {
          "name": "count",
          "type": "integer"
        },
        {
          "name": "total",
          "type": "integer"
        },
        {
          "name": "lines",
          "type": "array"
        }
      ]
    },
    {
      "id": "wishlist",
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
      "id": "checkout",
      "fields": [
        {
          "name": "contact",
          "type": "boolean"
        },
        {
          "name": "address",
          "type": "boolean"
        },
        {
          "name": "payment",
          "type": "boolean"
        },
        {
          "name": "order_id",
          "optional": true
        },
        {
          "name": "total",
          "type": "integer",
          "optional": true
        }
      ]
    },
    {
      "id": "order",
      "fields": [
        {
          "name": "order_id"
        },
        {
          "name": "status",
          "optional": true
        }
      ]
    },
    {
      "id": "return",
      "fields": [
        {
          "name": "order_id"
        },
        {
          "name": "product_id",
          "optional": true
        },
        {
          "name": "reason",
          "optional": true
        },
        {
          "name": "unused",
          "type": "boolean",
          "optional": true
        },
        {
          "name": "tags",
          "type": "boolean",
          "optional": true
        },
        {
          "name": "reference",
          "optional": true
        }
      ]
    },
    {
      "id": "gifts",
      "fields": [
        {
          "name": "recipient",
          "optional": true
        },
        {
          "name": "occasion",
          "optional": true
        },
        {
          "name": "budget_max",
          "type": "integer",
          "optional": true
        },
        {
          "name": "size",
          "optional": true
        },
        {
          "name": "colours",
          "type": "array",
          "optional": true
        },
        {
          "name": "patterns",
          "type": "array",
          "optional": true
        },
        {
          "name": "material",
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
      "id": "kiosk",
      "fields": [
        {
          "name": "summary",
          "optional": true
        },
        {
          "name": "count",
          "type": "integer",
          "optional": true
        },
        {
          "name": "ids",
          "type": "array",
          "optional": true
        },
        {
          "name": "product_id",
          "optional": true
        },
        {
          "name": "shortlist",
          "type": "array",
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
      "id": "shop.changed",
      "slice": "shop",
      "op": "set"
    },
    {
      "id": "product.size_picked",
      "slice": "product"
    },
    {
      "id": "fit.changed",
      "slice": "product"
    },
    {
      "id": "bag.changed",
      "slice": "bag",
      "op": "set"
    },
    {
      "id": "wishlist.changed",
      "slice": "wishlist",
      "op": "set"
    },
    {
      "id": "checkout.changed",
      "slice": "checkout"
    },
    {
      "id": "order.placed",
      "slice": "checkout"
    },
    {
      "id": "order.selected",
      "slice": "order",
      "op": "set"
    },
    {
      "id": "order.cancelled",
      "slice": "order",
      "op": "set"
    },
    {
      "id": "return.changed",
      "slice": "return"
    },
    {
      "id": "return.submitted",
      "slice": "return"
    },
    {
      "id": "gifts.changed",
      "slice": "gifts",
      "op": "set"
    },
    {
      "id": "kiosk.changed",
      "slice": "kiosk"
    }
  ]
});

export const SPEC_SHA256 = "938847e045b8a2cb5118c13ef9adae63a58e44af319779e79070b5db1af98374";
