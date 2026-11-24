# Generated from insurance/frontend/src/stage/scene.json by `voqalize stage gen`. Do not edit — regenerate with:
#   voqalize stage gen insurance/frontend/src/stage/scene.json --py insurance/backend/stage_gen.py --ts insurance/frontend/src/stage/scene.gen.ts
"""The moves of chhatri_insurance, from its Stage Spec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from voqalize.sdk.stage import Move, MoveClass, MoveSet, StageSpec, load_spec

#: The spec itself, carried here so the brain never reads the JSON at run
#: time (and a deploy that ships this file ships the spec with it).
SPEC: StageSpec = load_spec(
    '{"events":[{"doc":"A quote field or add-on changed.","id":"quote.changed","note":"{by} changed {field} on the {product} quote","op":"set","slice":"quote"},{"doc":"A policy document was opened.","id":"policy.viewed","note":"{by} opened policy {policy_id}","op":"set","slice":"policy_view"},{"doc":"A claim field changed, or the type or section did.","id":"claim.changed","note":"{by} changed {field} on the claim form","slice":"claim_form"},{"doc":"A document was uploaded (mock).","id":"claim.document_uploaded","note":"{by} uploaded {field}","slice":"claim_form"},{"ask":"thank them, give the claim reference and say what happens next from the claims guide, in two short sentences","doc":"The customer pressed Submit claim.","id":"claim.submitted","note":"{by} submitted the claim {reference}","react":"speak","slice":"claim_form"},{"doc":"The EN / हिंदी toggle moved.","id":"site.language_chosen","note":"{by} switched the language toggle to {language}","op":"set","slice":"site"}],"id":"chhatri_insurance","languages":["en","hi"],"moves":[{"args":[{"doc":"home, quote, quote/<product>, insurance/<product>, my-policies, my-policies/<policy_id>, claim. Products: car, bike, health, term, home, travel.","name":"page"}],"claims":["taking you to","opening the","le chalti hoon"],"class":"navigate","doc":"Go to one page of the site, ringing the nav item or the card that leads there first.","id":"site.go","objects":["page","quote","policy","policies","claim","home"]},{"args":[{"doc":"A language code from persona.json.","name":"language"}],"claims":["switching to"],"class":"reversible","doc":"Move the EN / हिंदी toggle by the call button to the language the call is now in. The brain has already moved both speech legs.","id":"site.language","objects":["language","hindi","english"]},{"args":[{"enum":["car","bike","health","term","home","travel"],"name":"product"}],"claims":["opening the quote","starting a quote"],"class":"navigate","doc":"Put that product\'s quote builder on screen: stays on /insurance/<product> or /quote/<product> when that product\'s builder is already showing, else goes to /quote/<product>. Rings the product tab.","id":"quote.open","objects":["quote","form"]},{"args":[{"doc":"A quote field id of the product on screen (data/products.json).","name":"field"},{"doc":"The value as the form stores it: an option value (suv, pune, 1000000) or a number (1400000).","name":"value"}],"claims":["filling in","putting in"],"class":"reversible","doc":"Ring the quote field, set it, and let the premium recompute. Refused with the options when the value is not one of them, or when no quote builder is on screen.","id":"quote.fill","objects":["quote","field","form"]},{"args":[{"doc":"An add-on id of the product on screen.","name":"addon"},{"name":"on","type":"boolean"}],"claims":["adding the","removing the"],"class":"reversible","doc":"Ring the add-on\'s toggle and switch it on or off; its line appears or leaves the breakdown. Refused, with why, when the add-on is unavailable for these answers.","id":"quote.addon","objects":["add-on","addon","cover"]},{"claims":["here\'s the breakdown"],"class":"look","doc":"Scroll to and ring the premium breakdown panel.","id":"quote.show","objects":["premium","breakdown"]},{"args":[{"doc":"A policy id of the signed-in customer (data/customer.json).","name":"policy_id"},{"doc":"A section id of that document, to scroll to.","name":"section","optional":true}],"claims":["opening your","pulling up your"],"class":"navigate","doc":"Open the customer\'s policy document at /my-policies/<policy_id> (and scroll to a section).","id":"policy.open","objects":["policy","document","wording"]},{"args":[{"name":"policy_id"},{"doc":"A clause id in that document, e.g. 3.4.","name":"clause_id"},{"enum":["covered","not_covered","covered_with_limits","depends"],"name":"verdict"}],"claims":["marking the clause","highlighting the clause"],"class":"look","doc":"Open the document if it is not open, scroll to the clause, ring it, highlight it and pin a verdict chip on it (Covered, Not covered, Covered with limits, Depends). Earlier marks are cleared.","id":"policy.mark","objects":["clause","policy","wording"]},{"args":[{"enum":["motor","health"],"name":"claim_type"},{"name":"policy_id","optional":true}],"claims":["starting the claim","opening the claim form"],"class":"reversible","doc":"Go to /claim, choose the claim type (and the policy), and open the form at its first section. Keeps what is already filled when the type is the same.","id":"claim.start","objects":["claim","form"]},{"args":[{"doc":"A claim form field id (data/claim_form.json).","name":"field"},{"doc":"Option value, date YYYY-MM-DD, time HH:MM, number, or text.","name":"value"}],"claims":["filling in","putting down"],"class":"reversible","doc":"Open the field\'s section, ring the field and set it. Refused with the options for a value the field does not take, or for a field hidden by the answers so far.","id":"claim.fill","objects":["claim","form","field"]},{"args":[{"doc":"A section id: policy, incident, driver, other_party, police, garage, patient, treatment, bank, documents, review.","name":"section"}],"claims":["showing the"],"class":"look","doc":"Open a section of the claim form, scroll to it and ring it (documents: rings the uploads still missing).","id":"claim.section","objects":["section","documents","claim"]},{"claims":["taking you to the review"],"class":"reversible","doc":"Check every section like the Review button and open the review step. Refused naming the fields still missing. Never submits: the customer ticks the declaration and presses Submit claim.","id":"claim.review","objects":["review","claim"]}],"slices":[{"doc":"the quote builder on screen: product, answers, add-ons on, and the total","fields":[{"name":"product","optional":true},{"doc":"The field or add-on that just changed.","name":"field","optional":true},{"fields":[{"name":"field"},{"name":"value"}],"name":"answers","type":"array"},{"doc":"Ids of the add-ons switched on.","name":"addons","type":"array"},{"doc":"Field ids still empty.","name":"missing","type":"array"},{"doc":"Total payable, rupees, once complete.","name":"total","optional":true,"type":"integer"}],"id":"quote"},{"doc":"the policy document on screen","fields":[{"name":"policy_id","optional":true},{"name":"section","optional":true}],"id":"policy_view"},{"doc":"the claim form: type, section in front, which fields hold something (names only) and which documents are uploaded","fields":[{"name":"claim_type","optional":true},{"name":"policy_id","optional":true},{"name":"section","optional":true},{"doc":"The field or document that just changed.","name":"field","optional":true},{"name":"filled","type":"array"},{"name":"missing","type":"array"},{"doc":"Ids of the documents uploaded.","name":"documents","type":"array"},{"name":"reference","optional":true}],"id":"claim_form"},{"doc":"the language the visitor chose on the toggle","fields":[{"name":"language","optional":true}],"id":"site"}],"stage":1}'
)
#: The spec's hash: a page reading another spec reports a different one.
SPEC_SHA256 = "53a37187127da92aa6770e7ae44a3488b427b5807e40ba774bba3ee9364fd7a6"


class GoArgs(BaseModel):
    """The arguments of ``site.go``."""

    page: str
    """home, quote, quote/<product>, insurance/<product>, my-policies, my-policies/<policy_id>, claim. Products: car, bike, health, term, home, travel."""


class LanguageArgs(BaseModel):
    """The arguments of ``site.language``."""

    language: str
    """A language code from persona.json."""


class QuoteOpenArgs(BaseModel):
    """The arguments of ``quote.open``."""

    product: Literal["car", "bike", "health", "term", "home", "travel"]


class QuoteFillArgs(BaseModel):
    """The arguments of ``quote.fill``."""

    field: str
    """A quote field id of the product on screen (data/products.json)."""
    value: str
    """The value as the form stores it: an option value (suv, pune, 1000000) or a number (1400000)."""


class AddonArgs(BaseModel):
    """The arguments of ``quote.addon``."""

    addon: str
    """An add-on id of the product on screen."""
    on: bool


class ShowArgs(BaseModel):
    """``quote.show`` takes none."""


class PolicyOpenArgs(BaseModel):
    """The arguments of ``policy.open``."""

    policy_id: str
    """A policy id of the signed-in customer (data/customer.json)."""
    section: str | None = None
    """A section id of that document, to scroll to."""


class MarkArgs(BaseModel):
    """The arguments of ``policy.mark``."""

    policy_id: str
    clause_id: str
    """A clause id in that document, e.g. 3.4."""
    verdict: Literal["covered", "not_covered", "covered_with_limits", "depends"]


class StartArgs(BaseModel):
    """The arguments of ``claim.start``."""

    claim_type: Literal["motor", "health"]
    policy_id: str | None = None


class ClaimFillArgs(BaseModel):
    """The arguments of ``claim.fill``."""

    field: str
    """A claim form field id (data/claim_form.json)."""
    value: str
    """Option value, date YYYY-MM-DD, time HH:MM, number, or text."""


class SectionArgs(BaseModel):
    """The arguments of ``claim.section``."""

    section: str
    """A section id: policy, incident, driver, other_party, police, garage, patient, treatment, bank, documents, review."""


class ReviewArgs(BaseModel):
    """``claim.review`` takes none."""


GO = Move(
    id="site.go",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("page",),
    claims=(
        "taking you to",
        "opening the",
        "le chalti hoon",
    ),
    objects=(
        "page",
        "quote",
        "policy",
        "policies",
        "claim",
        "home",
    ),
)
"""Go to one page of the site, ringing the nav item or the card that leads there first."""

LANGUAGE = Move(
    id="site.language",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=("language",),
    claims=("switching to",),
    objects=(
        "language",
        "hindi",
        "english",
    ),
)
"""Move the EN / हिंदी toggle by the call button to the language the call is now in. The brain has already moved both speech legs."""

QUOTE_OPEN = Move(
    id="quote.open",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=("product",),
    claims=(
        "opening the quote",
        "starting a quote",
    ),
    objects=(
        "quote",
        "form",
    ),
)
"""Put that product's quote builder on screen: stays on /insurance/<product> or /quote/<product> when that product's builder is already showing, else goes to /quote/<product>. Rings the product tab."""

QUOTE_FILL = Move(
    id="quote.fill",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "field",
        "value",
    ),
    claims=(
        "filling in",
        "putting in",
    ),
    objects=(
        "quote",
        "field",
        "form",
    ),
)
"""Ring the quote field, set it, and let the premium recompute. Refused with the options when the value is not one of them, or when no quote builder is on screen."""

ADDON = Move(
    id="quote.addon",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "addon",
        "on",
    ),
    claims=(
        "adding the",
        "removing the",
    ),
    objects=(
        "add-on",
        "addon",
        "cover",
    ),
)
"""Ring the add-on's toggle and switch it on or off; its line appears or leaves the breakdown. Refused, with why, when the add-on is unavailable for these answers."""

SHOW = Move(
    id="quote.show",
    verb=None,
    cls=MoveClass.LOOK,
    claims=("here's the breakdown",),
    objects=(
        "premium",
        "breakdown",
    ),
)
"""Scroll to and ring the premium breakdown panel."""

POLICY_OPEN = Move(
    id="policy.open",
    verb=None,
    cls=MoveClass.NAVIGATE,
    args=(
        "policy_id",
        "section",
    ),
    claims=(
        "opening your",
        "pulling up your",
    ),
    objects=(
        "policy",
        "document",
        "wording",
    ),
)
"""Open the customer's policy document at /my-policies/<policy_id> (and scroll to a section)."""

MARK = Move(
    id="policy.mark",
    verb=None,
    cls=MoveClass.LOOK,
    args=(
        "policy_id",
        "clause_id",
        "verdict",
    ),
    claims=(
        "marking the clause",
        "highlighting the clause",
    ),
    objects=(
        "clause",
        "policy",
        "wording",
    ),
)
"""Open the document if it is not open, scroll to the clause, ring it, highlight it and pin a verdict chip on it (Covered, Not covered, Covered with limits, Depends). Earlier marks are cleared."""

START = Move(
    id="claim.start",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "claim_type",
        "policy_id",
    ),
    claims=(
        "starting the claim",
        "opening the claim form",
    ),
    objects=(
        "claim",
        "form",
    ),
)
"""Go to /claim, choose the claim type (and the policy), and open the form at its first section. Keeps what is already filled when the type is the same."""

CLAIM_FILL = Move(
    id="claim.fill",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    args=(
        "field",
        "value",
    ),
    claims=(
        "filling in",
        "putting down",
    ),
    objects=(
        "claim",
        "form",
        "field",
    ),
)
"""Open the field's section, ring the field and set it. Refused with the options for a value the field does not take, or for a field hidden by the answers so far."""

SECTION = Move(
    id="claim.section",
    verb=None,
    cls=MoveClass.LOOK,
    args=("section",),
    claims=("showing the",),
    objects=(
        "section",
        "documents",
        "claim",
    ),
)
"""Open a section of the claim form, scroll to it and ring it (documents: rings the uploads still missing)."""

REVIEW = Move(
    id="claim.review",
    verb=None,
    cls=MoveClass.REVERSIBLE,
    claims=("taking you to the review",),
    objects=(
        "review",
        "claim",
    ),
)
"""Check every section like the Review button and open the review step. Refused naming the fields still missing. Never submits: the customer ticks the declaration and presses Submit claim."""

MOVES = MoveSet(
    (
        GO,
        LANGUAGE,
        QUOTE_OPEN,
        QUOTE_FILL,
        ADDON,
        SHOW,
        POLICY_OPEN,
        MARK,
        START,
        CLAIM_FILL,
        SECTION,
        REVIEW,
    )
)

#: The line each cue is taught with, in the spec's order.
PROMPT_LINES: tuple[str, ...] = ()

#: The slices of the page's state a read may name.
SliceId = Literal["quote", "policy_view", "claim_form", "site"]


class ReadRequest(BaseModel):
    """What the read tool takes: the slice to read, from the brain's mirror."""

    slice: SliceId = Field(
        description="Which part of their screen to read. quote: the quote builder on screen: product, answers, add-ons on, and the total; policy_view: the policy document on screen; claim_form: the claim form: type, section in front, which fields hold something (names only) and which documents are uploaded; site: the language the visitor chose on the toggle."
    )
