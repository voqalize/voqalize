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
      "id": "listing.filter",
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
      "id": "listing.sort",
      "verb": "sort",
      "class": "reversible",
      "args": [
        {
          "name": "order"
        },
        {
          "name": "path",
          "optional": true
        }
      ]
    },
    {
      "id": "search_products",
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
      "id": "show_cart",
      "class": "look",
      "args": [
        {
          "name": "open",
          "type": "boolean",
          "default": true
        }
      ]
    },
    {
      "id": "add_to_cart",
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
      "id": "update_cart_item",
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
    }
  ]
});

export const SPEC_SHA256 = "997a4a5ac83c4619c97d573bb3104050e1a1b112e5c298850f27b29edb99defe";
