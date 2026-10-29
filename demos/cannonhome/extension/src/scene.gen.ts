// Generated from cannonhome/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
//   voqalize stage gen cannonhome/scene.json --py cannonhome/backend/stage_gen.py --ts cannonhome/extension/src/scene.gen.ts
import { defineScene } from "@voqalize/stage";

/** The moves of cannonhome, from its Stage Spec. */
export const scene = defineScene({
  "stage": 1,
  "id": "cannonhome",
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
      "id": "filter_listing",
      "class": "reversible",
      "args": [
        {
          "name": "category_path"
        },
        {
          "name": "size",
          "type": "array",
          "optional": true
        },
        {
          "name": "color",
          "type": "array",
          "optional": true
        },
        {
          "name": "threads",
          "type": "array",
          "optional": true
        },
        {
          "name": "material",
          "type": "array",
          "optional": true
        },
        {
          "name": "sort",
          "enum": [
            "price_asc",
            "price_desc",
            "relevance",
            "newest"
          ],
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
            "descripcion",
            "especificaciones",
            "calificaciones",
            "fotos"
          ],
          "optional": true
        }
      ]
    },
    {
      "id": "product_tab",
      "class": "look",
      "args": [
        {
          "name": "tab",
          "enum": [
            "descripcion",
            "especificaciones",
            "calificaciones",
            "fotos"
          ]
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
      "id": "start_checkout",
      "class": "confirmed"
    },
    {
      "id": "fill_checkout",
      "class": "confirmed",
      "args": [
        {
          "name": "email",
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
          "name": "phone",
          "optional": true
        },
        {
          "name": "region",
          "optional": true
        },
        {
          "name": "comuna",
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
          "name": "apartment",
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
          "name": "in_stock",
          "type": "boolean",
          "optional": true
        },
        {
          "name": "qty",
          "type": "integer",
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
          "name": "rating",
          "type": "number",
          "optional": true
        },
        {
          "name": "reviews",
          "type": "integer",
          "optional": true
        },
        {
          "name": "source",
          "enum": [
            "page",
            "graphql"
          ]
        }
      ]
    },
    {
      "id": "search",
      "fields": [
        {
          "name": "query"
        },
        {
          "name": "items",
          "type": "array",
          "fields": [
            {
              "name": "name"
            },
            {
              "name": "path"
            },
            {
              "name": "price",
              "type": "number",
              "optional": true
            }
          ]
        },
        {
          "name": "categories",
          "type": "array"
        }
      ]
    },
    {
      "id": "checkout",
      "fields": [
        {
          "name": "filled",
          "type": "array"
        },
        {
          "name": "missing",
          "type": "array"
        },
        {
          "name": "invalid",
          "type": "array",
          "fields": [
            {
              "name": "field"
            },
            {
              "name": "message"
            }
          ]
        },
        {
          "name": "region",
          "optional": true
        },
        {
          "name": "comuna",
          "optional": true
        },
        {
          "name": "email_has_account",
          "type": "boolean",
          "optional": true
        },
        {
          "name": "delivery_options",
          "type": "array"
        },
        {
          "name": "delivery",
          "optional": true
        },
        {
          "name": "payment_open",
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
      "id": "search.suggested",
      "slice": "search",
      "op": "set"
    },
    {
      "id": "checkout.changed",
      "slice": "checkout",
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

export const SPEC_SHA256 = "6b46f675bf33dd95874ea7565fdc89837ac9e47784f727245b2f9dd6d2fed4fd";
