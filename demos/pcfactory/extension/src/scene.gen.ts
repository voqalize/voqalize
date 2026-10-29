// Generated from pcfactory/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
//   voqalize stage gen pcfactory/scene.json --py pcfactory/backend/stage_gen.py --ts pcfactory/extension/src/scene.gen.ts
import { defineScene } from "@voqalize/stage";

/** The moves of pcfactory, from its Stage Spec. */
export const scene = defineScene({
  "stage": 1,
  "id": "pcfactory",
  "moves": [
    {
      "id": "page.open",
      "verb": "page",
      "class": "navigate",
      "args": [
        {
          "name": "path"
        }
      ]
    },
    {
      "id": "page.show",
      "verb": "show",
      "class": "look",
      "args": [
        {
          "name": "target"
        },
        {
          "name": "path",
          "optional": true
        }
      ]
    },
    {
      "id": "page.faq",
      "verb": "faq",
      "class": "look",
      "args": [
        {
          "name": "question"
        },
        {
          "name": "path",
          "optional": true
        }
      ]
    },
    {
      "id": "product.tab",
      "verb": "tab",
      "class": "look",
      "args": [
        {
          "name": "tab",
          "enum": [
            "about",
            "specs",
            "warranty",
            "stock",
            "photos",
            "zoom",
            "pickup",
            "price_note"
          ]
        }
      ]
    },
    {
      "id": "filter_listing",
      "class": "reversible",
      "args": [
        {
          "name": "category_path"
        },
        {
          "name": "filters",
          "type": "array",
          "optional": true
        },
        {
          "name": "min_price",
          "type": "integer",
          "optional": true
        },
        {
          "name": "max_price",
          "type": "integer",
          "optional": true
        },
        {
          "name": "sort",
          "enum": [
            "price_asc",
            "price_desc",
            "relevance"
          ],
          "optional": true
        },
        {
          "name": "remove",
          "type": "array",
          "optional": true
        },
        {
          "name": "clear",
          "type": "boolean",
          "optional": true
        },
        {
          "name": "page",
          "type": "integer",
          "optional": true
        },
        {
          "name": "size",
          "type": "integer",
          "optional": true
        }
      ]
    },
    {
      "id": "open_product",
      "class": "navigate",
      "args": [
        {
          "name": "path"
        },
        {
          "name": "tab",
          "enum": [
            "about",
            "specs",
            "warranty",
            "stock",
            "photos"
          ],
          "optional": true
        }
      ]
    },
    {
      "id": "find_products",
      "class": "look",
      "args": [
        {
          "name": "query",
          "optional": true
        },
        {
          "name": "category_id",
          "type": "integer",
          "optional": true
        },
        {
          "name": "brand",
          "optional": true
        },
        {
          "name": "min_price",
          "type": "integer",
          "optional": true
        },
        {
          "name": "max_price",
          "type": "integer",
          "optional": true
        },
        {
          "name": "sort",
          "enum": [
            "price_asc",
            "price_desc",
            "relevance"
          ],
          "optional": true
        }
      ]
    },
    {
      "id": "check_prices",
      "class": "look",
      "args": [
        {
          "name": "paths",
          "type": "array"
        }
      ]
    },
    {
      "id": "check_stock",
      "class": "look",
      "args": [
        {
          "name": "path"
        },
        {
          "name": "store",
          "optional": true
        }
      ]
    },
    {
      "id": "stores.show",
      "verb": "store",
      "class": "look",
      "args": [
        {
          "name": "name"
        }
      ]
    },
    {
      "id": "compare.add",
      "class": "reversible",
      "args": [
        {
          "name": "paths",
          "type": "array"
        },
        {
          "name": "open",
          "type": "boolean",
          "default": true
        }
      ]
    },
    {
      "id": "compare.show",
      "verb": "compare",
      "class": "look",
      "args": [
        {
          "name": "row"
        }
      ]
    },
    {
      "id": "compare.remove",
      "class": "reversible",
      "args": [
        {
          "name": "path",
          "optional": true
        },
        {
          "name": "all",
          "type": "boolean",
          "optional": true
        }
      ]
    },
    {
      "id": "menu.open",
      "verb": "menu",
      "class": "look",
      "args": [
        {
          "name": "category",
          "optional": true
        }
      ]
    },
    {
      "id": "apply_coupon",
      "class": "confirmed",
      "args": [
        {
          "name": "code"
        }
      ]
    },
    {
      "id": "start_checkout",
      "class": "confirmed"
    },
    {
      "id": "commerce.filter",
      "verb": "filter",
      "class": "reversible",
      "args": [
        {
          "name": "facet"
        },
        {
          "name": "value",
          "optional": true
        },
        {
          "name": "path",
          "optional": true
        }
      ]
    },
    {
      "id": "commerce.sort",
      "verb": "sort",
      "class": "reversible",
      "args": [
        {
          "name": "order",
          "enum": [
            "price_asc",
            "price_desc",
            "relevance",
            "newest"
          ]
        },
        {
          "name": "path",
          "optional": true
        }
      ]
    },
    {
      "id": "commerce.search",
      "class": "reversible",
      "args": [
        {
          "name": "query"
        },
        {
          "name": "open_index",
          "type": "integer",
          "optional": true
        }
      ]
    },
    {
      "id": "commerce.cart_add",
      "class": "confirmed",
      "args": [
        {
          "name": "path"
        },
        {
          "name": "qty",
          "type": "integer",
          "default": 1
        }
      ]
    },
    {
      "id": "commerce.cart_update",
      "class": "confirmed",
      "args": [
        {
          "name": "path"
        },
        {
          "name": "qty",
          "type": "integer"
        }
      ]
    },
    {
      "id": "commerce.cart_show",
      "class": "look",
      "args": [
        {
          "name": "open",
          "type": "boolean",
          "default": true
        }
      ]
    }
  ],
  "slices": [
    {
      "id": "product",
      "fields": [
        {
          "name": "path"
        },
        {
          "name": "id",
          "type": "integer",
          "optional": true
        },
        {
          "name": "name"
        },
        {
          "name": "brand",
          "optional": true
        },
        {
          "name": "price",
          "type": "number",
          "optional": true
        },
        {
          "name": "card_price",
          "type": "number",
          "optional": true
        },
        {
          "name": "regular_price",
          "type": "number",
          "optional": true
        },
        {
          "name": "online_stock",
          "optional": true
        },
        {
          "name": "stores_with_stock",
          "type": "integer",
          "optional": true
        },
        {
          "name": "warranty",
          "optional": true
        },
        {
          "name": "promo_until",
          "optional": true
        },
        {
          "name": "specs",
          "type": "array",
          "fields": [
            {
              "name": "label"
            },
            {
              "name": "value"
            }
          ]
        },
        {
          "name": "source",
          "enum": [
            "page",
            "api"
          ]
        }
      ]
    },
    {
      "id": "checkout",
      "fields": [
        {
          "name": "step",
          "enum": [
            "login",
            "delivery",
            "payment",
            "other"
          ]
        },
        {
          "name": "options",
          "type": "array",
          "optional": true
        },
        {
          "name": "chosen",
          "optional": true
        }
      ]
    },
    {
      "id": "compare",
      "fields": [
        {
          "name": "path"
        },
        {
          "name": "category",
          "optional": true
        },
        {
          "name": "items",
          "type": "array",
          "fields": [
            {
              "name": "path"
            },
            {
              "name": "name"
            },
            {
              "name": "brand",
              "optional": true
            },
            {
              "name": "price",
              "type": "number",
              "optional": true
            },
            {
              "name": "card_price",
              "type": "number",
              "optional": true
            },
            {
              "name": "regular_price",
              "type": "number",
              "optional": true
            }
          ]
        },
        {
          "name": "rows",
          "type": "array",
          "fields": [
            {
              "name": "group"
            },
            {
              "name": "label"
            },
            {
              "name": "values",
              "type": "array"
            }
          ]
        },
        {
          "name": "differs",
          "type": "array"
        },
        {
          "name": "highlighted",
          "type": "boolean",
          "optional": true
        }
      ]
    },
    {
      "id": "listing",
      "fields": [
        {
          "name": "path"
        },
        {
          "name": "title"
        },
        {
          "name": "count",
          "type": "integer",
          "optional": true
        },
        {
          "name": "filters",
          "type": "array",
          "fields": [
            {
              "name": "facet"
            },
            {
              "name": "on",
              "type": "array"
            },
            {
              "name": "options",
              "type": "array"
            }
          ]
        },
        {
          "name": "sort",
          "optional": true
        },
        {
          "name": "items",
          "type": "array",
          "fields": [
            {
              "name": "path"
            },
            {
              "name": "name"
            },
            {
              "name": "price",
              "type": "number",
              "optional": true
            },
            {
              "name": "regular_price",
              "type": "number",
              "optional": true
            }
          ]
        }
      ]
    },
    {
      "id": "cart",
      "fields": [
        {
          "name": "count",
          "type": "integer"
        },
        {
          "name": "subtotal",
          "type": "number",
          "optional": true
        },
        {
          "name": "items",
          "type": "array",
          "fields": [
            {
              "name": "path"
            },
            {
              "name": "name"
            },
            {
              "name": "qty",
              "type": "integer"
            },
            {
              "name": "price",
              "type": "number",
              "optional": true
            }
          ]
        },
        {
          "name": "free_shipping_left",
          "type": "number",
          "optional": true
        }
      ]
    }
  ],
  "events": [
    {
      "id": "product.shown",
      "slice": "product",
      "op": "set"
    },
    {
      "id": "product.checked",
      "slice": "product",
      "op": "set"
    },
    {
      "id": "checkout.changed",
      "slice": "checkout",
      "op": "set"
    },
    {
      "id": "compare.shown",
      "slice": "compare",
      "op": "set"
    },
    {
      "id": "listing.shown",
      "slice": "listing",
      "op": "set"
    },
    {
      "id": "listing.filtered",
      "slice": "listing",
      "op": "set"
    },
    {
      "id": "listing.sorted",
      "slice": "listing",
      "op": "set"
    },
    {
      "id": "cart.changed",
      "slice": "cart",
      "op": "set"
    }
  ]
});

export const SPEC_SHA256 = "68425cb8c5bd2dd23a1b8a6f22bd127c996e60de44de7824cd28e4746416b5a7";
