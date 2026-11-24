# Generated from demos/property/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen demos/property/frontend/src/stage/scene.json --py demos/property/backend/stage_gen.py --ts demos/property/frontend/src/stage/scene.gen.ts
"""The moves of kosha_homes, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"events":[{"id":"screen.viewed","note":"{by} opened {path}","op":"set","react":"silent","slice":"screen"},{"id":"search.changed","note":"{by} changed the search: {summary}; {count} homes match","op":"set","slice":"search"},{"id":"shortlist.changed","note":"{by} changed the shortlist: {count} homes","op":"set","slice":"shortlist"},{"id":"visit.slot_picked","note":"{by} picked the visit slot {slot} for {listing_id}","slice":"visit"},{"ask":"they typed their mobile number on the visit form: thank them in a few words and go on with the booking","id":"visit.phone_typed","note":"{by} typed a mobile number on the visit form for {listing_id} (typed: {typed}); the number itself stays on the page","react":"speak","slice":"visit"},{"ask":"they booked the site visit themselves: confirm it in one line and say one thing to bring","id":"visit.booked","note":"{by} booked a site visit for {listing_id} at {slot}, reference {reference}","op":"set","react":"speak","slice":"visit"}],"id":"kosha_homes","languages":["en","hi"],"moves":[{"args":[{"doc":"A page of the site: /, /listings, /listing/<id>, /project/<project_id>, /compare, /shortlist, /visits.","name":"path"}],"claims":["opening the","taking you to"],"class":"navigate","doc":"Go to a page of the site, ringing the link or header that leads there first.","id":"site.go","objects":["page","listing","project","listings","shortlist","visits","पेज"]},{"args":[{"enum":["bengaluru","pune","hyderabad"],"name":"city","optional":true},{"enum":["buy","rent"],"name":"deal","optional":true},{"doc":"Bedroom counts as strings, [\\"2\\", \\"3\\"]: a move\'s array carries strings only.","name":"bhk","optional":true,"type":"array"},{"doc":"Rupees: a price to buy, a monthly rent to rent.","name":"budget_min","optional":true,"type":"integer"},{"doc":"Rupees: a price to buy, a monthly rent to rent.","name":"budget_max","optional":true,"type":"integer"},{"enum":["ready","under_construction"],"name":"possession","optional":true},{"name":"localities","optional":true,"type":"array"},{"doc":"An office\'s id from the city\'s places, for the commute filter.","name":"office","optional":true},{"doc":"Most kilometres from the office.","name":"max_km","optional":true,"type":"number"},{"doc":"A school within this many kilometres.","name":"school_km","optional":true,"type":"number"},{"doc":"A metro station within this many kilometres.","name":"metro_km","optional":true,"type":"number"},{"name":"amenities","optional":true,"type":"array"}],"claims":["filtering the","narrowing the","ticking"],"class":"reversible","doc":"Set the listings page\'s whole search: on /listings each sidebar control that changes is ringed and set in turn, then the results and the map follow. Navigates to /listings first when elsewhere.","id":"listings.filter","objects":["filters","filter","listings","homes","results","map","फ़िल्टर","घर"]},{"args":[{"doc":"A listing id on screen, BLR-104.","name":"listing_id"}],"class":"look","doc":"Ring one listing\'s card and its map pin, scrolling it into view. Changes nothing.","id":"listings.show","say":"{show: BLR-104} at the start of the sentence that talks about one home on the list: its card and its map pin are ringed.","verb":"show"},{"args":[{"doc":"Two or three listing ids.","name":"ids","type":"array"}],"claims":["comparing them","putting them side by side"],"class":"navigate","doc":"Open the compare page with these homes side by side; each row\'s better value is marked and the rows are ringed in turn.","id":"compare.show","objects":["comparison","compare","side by side","तुलना"]},{"args":[{"name":"listing_id"},{"name":"down_pct","optional":true,"type":"number"},{"name":"tenure_years","optional":true,"type":"integer"},{"doc":"A lender id from homes.json.","name":"lender","optional":true}],"claims":["working out the emi","opening the emi"],"class":"reversible","doc":"Open the EMI calculator for a listing (on its page, or as a panel on the listings page) and set down payment, tenure and lender, each ringed.","id":"emi.show","objects":["emi","loan","calculator","ईएमआई"]},{"args":[{"name":"listing_id"},{"default":true,"name":"on","type":"boolean"}],"claims":["adding it to your shortlist","shortlisting"],"class":"reversible","doc":"Ring the listing\'s heart and add it to (or take it off) the shortlist.","id":"shortlist.set","objects":["shortlist","शॉर्टलिस्ट"]},{"args":[{"name":"listing_id"},{"doc":"YYYY-MM-DD, IST.","name":"day"},{"enum":["morning","afternoon","evening","any"],"name":"part","optional":true}],"claims":["opening the visit","checking the slots"],"class":"look","doc":"On the listing page\'s site-visit panel: ring and open that day, and mark the free slots in that part of the day as suiting the buyer.","id":"visit.slots","objects":["slots","slot","visit","calendar","स्लॉट"]},{"args":[{"name":"listing_id"},{"doc":"YYYY-MM-DDTHH:MM, IST, one of the free slots.","name":"slot"},{"doc":"The buyer\'s name as they said it.","name":"name"},{"default":1,"name":"visitors","type":"integer"}],"class":"reversible","doc":"On the listing\'s visit panel: select the slot and fill the name and visitors, each ringed; while the Mobile box is empty it is ringed and focused for the visitor to type their number (never filled by the agent). Books nothing.","id":"visit.fill"},{"args":[{"name":"listing_id"},{"doc":"YYYY-MM-DDTHH:MM, IST, one of the free slots.","name":"slot"},{"doc":"The buyer\'s name as they said it.","name":"name"},{"default":1,"name":"visitors","type":"integer"}],"claims":["booking the visit","booking it"],"class":"confirmed","doc":"Select the slot, fill name and visitors, press Book visit; the visit card appears. Refused when the slot is not free or the visitor has not typed their mobile number.","id":"visit.book","objects":["booking","visit","बुकिंग"]}],"slices":[{"doc":"the page in front of the visitor","fields":[{"name":"path"},{"name":"page"},{"name":"listing_id","optional":true},{"name":"title","optional":true}],"id":"screen"},{"doc":"the listings page\'s search","fields":[{"name":"summary"},{"name":"count","type":"integer"},{"name":"city","optional":true},{"name":"deal","optional":true},{"items":{"type":"integer"},"name":"bhk","optional":true,"type":"array"},{"name":"budget_min","optional":true,"type":"integer"},{"name":"budget_max","optional":true,"type":"integer"},{"name":"possession","optional":true},{"name":"localities","optional":true,"type":"array"},{"name":"office","optional":true},{"name":"max_km","optional":true,"type":"number"},{"name":"school_km","optional":true,"type":"number"},{"name":"metro_km","optional":true,"type":"number"},{"name":"amenities","optional":true,"type":"array"},{"name":"ids","optional":true,"type":"array"}],"id":"search"},{"doc":"the homes the visitor shortlisted","fields":[{"name":"count","type":"integer"},{"name":"ids","type":"array"}],"id":"shortlist"},{"doc":"the site-visit panel and bookings","fields":[{"name":"listing_id"},{"name":"slot","optional":true},{"name":"reference","optional":true},{"name":"typed","optional":true,"type":"boolean"}],"id":"visit"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "0cb6a031857eb735084c07602b706dc8fd1bfd43ec2135ce3b7f92ecba4f4b73"


class GoArgs(BaseModel):
    """The arguments of ``site.go``."""

    path: str
    """A page of the site: /, /listings, /listing/<id>, /project/<project_id>, /compare, /shortlist, /visits."""


class FilterArgs(BaseModel):
    """The arguments of ``listings.filter``."""

    city: Literal["bengaluru", "pune", "hyderabad"] | None = None
    deal: Literal["buy", "rent"] | None = None
    bhk: list[str] | None = None
    """Bedroom counts as strings, ["2", "3"]: a move's array carries strings only."""
    budget_min: int | None = None
    """Rupees: a price to buy, a monthly rent to rent."""
    budget_max: int | None = None
    """Rupees: a price to buy, a monthly rent to rent."""
    possession: Literal["ready", "under_construction"] | None = None
    localities: list[str] | None = None
    office: str | None = None
    """An office's id from the city's places, for the commute filter."""
    max_km: float | None = None
    """Most kilometres from the office."""
    school_km: float | None = None
    """A school within this many kilometres."""
    metro_km: float | None = None
    """A metro station within this many kilometres."""
    amenities: list[str] | None = None


class ListingsShowArgs(BaseModel):
    """The arguments of ``listings.show``."""

    listing_id: str
    """A listing id on screen, BLR-104."""


class CompareShowArgs(BaseModel):
    """The arguments of ``compare.show``."""

    ids: list[str]
    """Two or three listing ids."""


class EmiShowArgs(BaseModel):
    """The arguments of ``emi.show``."""

    listing_id: str
    down_pct: float | None = None
    tenure_years: int | None = None
    lender: str | None = None
    """A lender id from homes.json."""


class SetArgs(BaseModel):
    """The arguments of ``shortlist.set``."""

    listing_id: str
    on: bool = True


class SlotsArgs(BaseModel):
    """The arguments of ``visit.slots``."""

    listing_id: str
    day: str
    """YYYY-MM-DD, IST."""
    part: Literal["morning", "afternoon", "evening", "any"] | None = None


class FillArgs(BaseModel):
    """The arguments of ``visit.fill``."""

    listing_id: str
    slot: str
    """YYYY-MM-DDTHH:MM, IST, one of the free slots."""
    name: str
    """The buyer's name as they said it."""
    visitors: int = 1


class BookArgs(BaseModel):
    """The arguments of ``visit.book``."""

    listing_id: str
    slot: str
    """YYYY-MM-DDTHH:MM, IST, one of the free slots."""
    name: str
    """The buyer's name as they said it."""
    visitors: int = 1


GO = Move(
    id="site.go",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("path",),
    claims=(
        "opening the",
        "taking you to",
    ),
    objects=(
        "page",
        "listing",
        "project",
        "listings",
        "shortlist",
        "visits",
        "पेज",
    ),
)
"""Go to a page of the site, ringing the link or header that leads there first."""

FILTER = Move(
    id="listings.filter",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "city",
        "deal",
        "bhk",
        "budget_min",
        "budget_max",
        "possession",
        "localities",
        "office",
        "max_km",
        "school_km",
        "metro_km",
        "amenities",
    ),
    claims=(
        "filtering the",
        "narrowing the",
        "ticking",
    ),
    objects=(
        "filters",
        "filter",
        "listings",
        "homes",
        "results",
        "map",
        "फ़िल्टर",
        "घर",
    ),
)
"""Set the listings page's whole search: on /listings each sidebar control that changes is ringed and set in turn, then the results and the map follow. Navigates to /listings first when elsewhere."""

LISTINGS_SHOW = Move(
    id="listings.show",
    verb="show",
    cls=MoveClass.LOOK,
    args=("listing_id",),
    say="{show: BLR-104} at the start of the sentence that talks about one home on the list: its card and its map pin are ringed.",
)
"""Ring one listing's card and its map pin, scrolling it into view. Changes nothing."""

COMPARE_SHOW = Move(
    id="compare.show",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("ids",),
    claims=(
        "comparing them",
        "putting them side by side",
    ),
    objects=(
        "comparison",
        "compare",
        "side by side",
        "तुलना",
    ),
)
"""Open the compare page with these homes side by side; each row's better value is marked and the rows are ringed in turn."""

EMI_SHOW = Move(
    id="emi.show",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "listing_id",
        "down_pct",
        "tenure_years",
        "lender",
    ),
    claims=(
        "working out the emi",
        "opening the emi",
    ),
    objects=(
        "emi",
        "loan",
        "calculator",
        "ईएमआई",
    ),
)
"""Open the EMI calculator for a listing (on its page, or as a panel on the listings page) and set down payment, tenure and lender, each ringed."""

SET = Move(
    id="shortlist.set",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "listing_id",
        "on",
    ),
    claims=(
        "adding it to your shortlist",
        "shortlisting",
    ),
    objects=(
        "shortlist",
        "शॉर्टलिस्ट",
    ),
)
"""Ring the listing's heart and add it to (or take it off) the shortlist."""

SLOTS = Move(
    id="visit.slots",
    verb=None,
    cls=MoveClass.LOOK,
    args=(
        "listing_id",
        "day",
        "part",
    ),
    claims=(
        "opening the visit",
        "checking the slots",
    ),
    objects=(
        "slots",
        "slot",
        "visit",
        "calendar",
        "स्लॉट",
    ),
)
"""On the listing page's site-visit panel: ring and open that day, and mark the free slots in that part of the day as suiting the buyer."""

FILL = Move(
    id="visit.fill",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "listing_id",
        "slot",
        "name",
        "visitors",
    ),
)
"""On the listing's visit panel: select the slot and fill the name and visitors, each ringed; while the Mobile box is empty it is ringed and focused for the visitor to type their number (never filled by the agent). Books nothing."""

BOOK = Move(
    id="visit.book",
    verb=None,
    cls=MoveClass.CONFIRMED,
    args=(
        "listing_id",
        "slot",
        "name",
        "visitors",
    ),
    claims=(
        "booking the visit",
        "booking it",
    ),
    objects=(
        "booking",
        "visit",
        "बुकिंग",
    ),
)
"""Select the slot, fill name and visitors, press Book visit; the visit card appears. Refused when the slot is not free or the visitor has not typed their mobile number."""

MOVES = MoveSet(
    (
        GO,
        FILTER,
        LISTINGS_SHOW,
        COMPARE_SHOW,
        EMI_SHOW,
        SET,
        SLOTS,
        FILL,
        BOOK,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = (
    "{show: BLR-104} at the start of the sentence that talks about one home on the list: its card and its map pin are ringed.",
)

#: The slices of the page's state a read may name.
SliceId = Literal["screen", "search", "shortlist", "visit"]


class ReadRequest(BaseModel):
    """What the read tool takes: the slice to read, from the brain's mirror."""

    slice: SliceId = Field(
        description="Which part of their screen to read. screen: the page in front of the visitor; search: the listings page's search; shortlist: the homes the visitor shortlisted; visit: the site-visit panel and bookings."
    )
