// Generated from agroplanet/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
//   voqalize stage gen agroplanet/scene.json --py agroplanet/backend/stage_gen.py --ts agroplanet/extension/src/scene.gen.ts
import { defineScene } from "@voqalize/stage";

/** The moves of agroplanet, from its Stage Spec. */
export const scene = defineScene({
  "stage": 1,
  "id": "agroplanet",
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
      "id": "menu.open",
      "verb": "menu",
      "class": "look",
      "args": [
        {
          "name": "category"
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
            "details",
            "specs",
            "photos",
            "zoom",
            "price"
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
            "details",
            "specs",
            "photos",
            "zoom",
            "price"
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
          "name": "category_code",
          "optional": true
        },
        {
          "name": "brand",
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
      "id": "start_quote",
      "class": "confirmed"
    },
    {
      "id": "fill_quote",
      "class": "confirmed",
      "args": [
        {
          "name": "name",
          "optional": true
        },
        {
          "name": "phone",
          "optional": true
        },
        {
          "name": "email",
          "optional": true
        },
        {
          "name": "region",
          "optional": true
        },
        {
          "name": "commune",
          "optional": true
        },
        {
          "name": "street",
          "optional": true
        },
        {
          "name": "number",
          "optional": true
        },
        {
          "name": "unit",
          "optional": true
        },
        {
          "name": "notes",
          "optional": true
        }
      ]
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
          "name": "sku",
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
          "name": "maker_code",
          "optional": true
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
        },
        {
          "name": "discount",
          "type": "integer",
          "optional": true
        },
        {
          "name": "price_hidden",
          "type": "boolean",
          "optional": true
        },
        {
          "name": "stock",
          "optional": true
        },
        {
          "name": "stock_level",
          "type": "integer",
          "optional": true
        },
        {
          "name": "description",
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
      "id": "quote",
      "fields": [
        {
          "name": "step",
          "enum": [
            "form",
            "done",
            "other"
          ]
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
          "name": "items",
          "type": "integer",
          "optional": true
        },
        {
          "name": "total",
          "type": "number",
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
      "id": "quote.changed",
      "slice": "quote",
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

export const SPEC_SHA256 = "760a59d821467a4af12851fa71cf66e0472e55ce1830002c5942e3a3dc26b37e";
