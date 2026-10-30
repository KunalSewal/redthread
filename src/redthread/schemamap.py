"""Someone else's schema (challenge 13): map a bank's graph schema onto the concepts an investigation needs.

A bank's graph comes in its own vocabulary: ISO 20022 message elements, BIAN service domains, a core
banking system's application records. Before RedThread can investigate on it, it needs to know which
vertex is a person, which is an account, which of three money-movement records is the transaction,
which way an edge points, and which attribute holds the amount.

The split is the same as everywhere else in RedThread:

- **Code parses.** ``parse_gsql`` reads the schema file into vertices, attributes and edges (with
  direction and reverse names). Comments are stripped first, so nothing the file's author wrote about
  the answer reaches the mapper.
- **The model proposes.** It reads the parsed schema and the target model below, and proposes a mapping
  with a reason for every choice (redthread.schemamap_llm).
- **Code checks.** ``validate`` rejects any vertex, edge or attribute that does not exist, any edge path
  that does not actually connect the mapped types in the direction given, and any attribute that is
  not on (or reachable from) the vertex it is mapped from. An invalid proposal is reported, never
  patched.

The target model is ours: the concepts an investigation needs and what each one means. Its names
follow the vocabulary the organisers' test schemas map onto.
"""

import re
from dataclasses import dataclass, field

# ------------------------------------------------------------------------------------------------ parse


@dataclass
class Vertex:
    name: str
    primary_id: str
    attributes: dict[str, str]  # attribute name -> type, the primary id included


@dataclass
class Edge:
    name: str
    pairs: list[tuple[str, str]]  # (from vertex, to vertex)
    directed: bool
    reverse: str | None
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class Schema:
    graph: str
    vertices: dict[str, Vertex]
    edges: dict[str, Edge]

    def hop(self, edge_name: str) -> list[tuple[str, str]]:
        """(from, to) pairs for an edge name, a reverse edge name, or an undirected edge either way."""
        if edge_name in self.edges:
            e = self.edges[edge_name]
            return e.pairs + ([(b, a) for a, b in e.pairs] if not e.directed else [])
        for e in self.edges.values():
            if e.reverse == edge_name:
                return [(b, a) for a, b in e.pairs]
        return []


def strip_comments(text: str) -> str:
    """Remove '#' and '//' comments: the schema's author can describe the answer in them."""
    out = []
    for line in text.splitlines():
        line = re.sub(r"(^|\s)(#|//).*$", "", line)
        if line.strip():
            out.append(line)
    return "\n".join(out)


_VERTEX = re.compile(r"ADD\s+VERTEX\s+(\w+)\s*\((.*?)\)\s*(WITH[^;]*)?;", re.S | re.I)
_EDGE = re.compile(r"ADD\s+(DIRECTED|UNDIRECTED)\s+EDGE\s+(\w+)\s*\((.*?)\)\s*(WITH[^;]*)?;", re.S | re.I)


def _attributes(body: str) -> dict[str, str]:
    attrs = {}
    for part in re.split(r",(?![^()]*\))", body):
        tokens = part.split()
        if len(tokens) >= 2 and tokens[0].upper() not in ("FROM", "TO"):
            name, typ = (tokens[1], tokens[2]) if tokens[0].upper() == "PRIMARY_ID" else (tokens[0], tokens[1])
            attrs[name] = typ.upper()
    return attrs


def parse_gsql(text: str) -> Schema:
    text = strip_comments(text)
    graph = (re.search(r"CREATE\s+GRAPH\s+(\w+)", text, re.I) or re.search(r"FOR\s+GRAPH\s+(\w+)", text, re.I))
    vertices = {}
    for name, body, _ in _VERTEX.findall(text):
        pk = re.search(r"PRIMARY_ID\s+(\w+)", body, re.I)
        vertices[name] = Vertex(name, pk.group(1) if pk else "", _attributes(body))
    edges = {}
    for kind, name, body, with_ in _EDGE.findall(text):
        pairs = re.findall(r"FROM\s+(\w+)\s*,\s*TO\s+(\w+)", body, re.I)
        attr_body = re.sub(r"\|?\s*FROM\s+\w+\s*,\s*TO\s+\w+\s*,?", "", body, flags=re.I)
        reverse = re.search(r'REVERSE_EDGE\s*=\s*"(\w+)"', with_ or "", re.I)
        edges[name] = Edge(name, pairs, kind.upper() == "DIRECTED", reverse.group(1) if reverse else None,
                           _attributes(attr_body))
    return Schema(graph.group(1) if graph else "", vertices, edges)


def describe(schema: Schema) -> str:
    """The schema as the mapper sees it: names, types and directions only."""
    lines = [f"GRAPH {schema.graph}", "VERTICES"]
    for v in schema.vertices.values():
        attrs = ", ".join(f"{a} {t}" for a, t in v.attributes.items())
        lines.append(f"  {v.name} (primary id {v.primary_id}): {attrs}")
    lines.append("EDGES (direction FROM -> TO; a reverse name walks it TO -> FROM)")
    for e in schema.edges.values():
        pairs = " | ".join(f"{a} -> {b}" for a, b in e.pairs)
        extra = f"; reverse {e.reverse}" if e.reverse else ""
        attrs = f"; attributes {', '.join(e.attributes)}" if e.attributes else ""
        lines.append(f"  {e.name} ({'directed' if e.directed else 'undirected'}): {pairs}{extra}{attrs}")
    return "\n".join(lines)


# -------------------------------------------------------------------------------------- target model

CONCEPTS = {
    "Person": "a customer of this bank (an individual or organisation that holds accounts here)",
    "Account": "an account this bank keeps for a customer; money moves in and out of it",
    "Transaction": "one movement of money that actually happened (not a request, not a ledger posting, "
                   "not a return of an earlier payment)",
    "Beneficiary": "the external party a payment goes to (a payee that is not this bank's customer)",
    "Device": "the phone or computer a customer used to log in or pay (not a payment card)",
    "IPAddress": "the network address a customer connected from",
    "LoginEvent": "one sign-on or authentication by a customer to a digital channel",
    "Card": "a payment card issued on an account",
    "Merchant": "a business where a card was used",
    "InvestigationCase": "a fraud or financial-crime case opened by the bank (not a score, not a flag)",
}

RELATIONS = {  # name: (from concept, to concept, meaning)
    "OWNS": ("Person", "Account", "the person owns or jointly holds the account"),
    "INITIATED": ("Account", "Transaction", "the account the money left (the payer's account)"),
    "PAYS_TO_ACCOUNT": ("Transaction", "Account", "an account at this bank that received the money"),
    "PAYS": ("Transaction", "Beneficiary", "the external payee the money went to"),
    "FROM_DEVICE": ("Transaction", "Device", "the device the payment was made from"),
    "FROM_IP": ("Transaction", "IPAddress", "the network address the payment was made from"),
    "AT": ("Transaction", "Merchant", "where a card payment was made"),
    "VIA": ("Transaction", "Card", "the card a payment was made with"),
    "HOLDS": ("Account", "Card", "a card issued on the account"),
    "LOGGED_IN": ("LoginEvent", "Account", "the account whose holder logged in"),
    "LOGIN_FROM_DEVICE": ("LoginEvent", "Device", "the device used for the sign-on"),
    "LOGIN_FROM_IP": ("LoginEvent", "IPAddress", "the address of the sign-on"),
    "INVESTIGATED_IN": ("Account", "InvestigationCase", "a case concerning the account"),
}

ATTRIBUTES = {  # name: (concept, meaning)
    "Transaction.amount": ("Transaction", "the amount that actually moved (settled), not a requested or pre-FX one"),
    "Transaction.timestamp": ("Transaction", "when the money moved, with time of day if the schema has it"),
    "Transaction.channel": ("Transaction", "how it was made: transfer type, card, cash, instant, ..."),
    "Account.open_date": ("Account", "when the account was opened"),
    "Account.status": ("Account", "the account's state: active, blocked, closed"),
    "Account.kyc_score": ("Account", "a know-your-customer risk score on the account, if there is one"),
    "Person.anonymized_ssn_hash": ("Person", "a hash of the person's national identity number"),
    "Person.kyc_verified_at": ("Person", "when the person's identity was last verified"),
    "Beneficiary.bank_identifier": ("Beneficiary", "the payee's bank: BIC, sort code or similar"),
    "Beneficiary.name_hash": ("Beneficiary", "a hash of the payee's name"),
    "InvestigationCase.status": ("InvestigationCase", "whether the case is open or closed"),
    "account_under_investigation": ("Account", "how to tell an account is currently under investigation"),
}


def target_model() -> str:
    lines = ["CONCEPTS"] + [f"  {k}: {v}" for k, v in CONCEPTS.items()]
    lines += ["RELATIONS (from concept -> to concept)"]
    lines += [f"  {k}: {a} -> {b}: {m}" for k, (a, b, m) in RELATIONS.items()]
    lines += ["ATTRIBUTES"] + [f"  {k}: {m}" for k, (_, m) in ATTRIBUTES.items()]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------- check

CONFIDENCE = ("exact", "approximate", "unmapped")


def validate(mapping: dict, schema: Schema) -> list[str]:
    """Every problem with a proposed mapping, against the schema as parsed. Empty means it holds."""
    problems = []
    concept_types: dict[str, set[str]] = {}
    for c in mapping.get("concepts", []):
        if c["confidence"] == "unmapped":
            if c.get("vertices"):
                problems.append(f"{c['concept']}: unmapped but names vertices {c['vertices']}")
            continue
        missing = [v for v in c.get("vertices", []) if v not in schema.vertices]
        if missing:
            problems.append(f"{c['concept']}: no such vertex {missing}")
        if not c.get("vertices"):
            problems.append(f"{c['concept']}: mapped but names no vertex")
        concept_types[c["concept"]] = set(c.get("vertices", [])) - set(missing)
    for r in mapping.get("relations", []):
        if r["confidence"] == "unmapped":
            continue
        frm, to, _ = RELATIONS.get(r["relation"], (None, None, None))
        if frm is None:
            problems.append(f"{r['relation']}: not a relation of the target model")
            continue
        if not r.get("paths") or not all(p.get("edges") for p in r["paths"]):
            problems.append(f"{r['relation']}: mapped but gives no edge path")
            continue
        for path in r["paths"]:
            reach = set(concept_types.get(frm, set()))
            for hop in path["edges"]:
                pairs = schema.hop(hop)
                if not pairs:
                    problems.append(f"{r['relation']}: no such edge {hop!r}")
                    reach = set()
                    break
                reach = {b for a, b in pairs if a in reach}
                if not reach:
                    problems.append(f"{r['relation']}: edge {hop!r} does not continue the path in that direction")
                    break
            else:
                if concept_types.get(to) and not (reach & concept_types[to]):
                    problems.append(f"{r['relation']}: path {path['edges']} ends at {sorted(reach)}, not at {to} "
                                    f"({sorted(concept_types[to])})")
    for a in mapping.get("attributes", []):
        if a["confidence"] == "unmapped":
            continue
        if not a.get("sources"):
            problems.append(f"{a['attribute']}: mapped but names no source")
        for src in a.get("sources", []):
            if "." not in src:
                problems.append(f"{a['attribute']}: source {src!r} is not Vertex.attribute")
                continue
            vertex, attr = src.split(".", 1)
            if vertex not in schema.vertices or attr not in schema.vertices[vertex].attributes:
                if not any(attr in e.attributes for e in schema.edges.values() if e.name == vertex):
                    problems.append(f"{a['attribute']}: no attribute {src}")
    return problems


# ------------------------------------------------------------------------------------------- propose

PROPOSE_SYSTEM = """You map a bank's graph schema onto a fixed target model for fraud investigation.
You see only the schema's names, types and edge directions. Judge from meaning, not spelling:
- Money movement: map Transaction to the record of money that actually moved. A request or order to
  pay, a ledger or statement posting, and a return of an earlier payment are not the transaction. If two
  record types both move money for real (for example transfers and cash at a branch), list both.
- A party type shared by customers and outsiders maps with a filter on the attribute that tells them
  apart. A payment card is a Card, even if the schema calls it a device; Device is what a person logs in
  or pays from.
- A score, an alert flag or a block code is not an InvestigationCase; say how an account under
  investigation can be recognised instead (account_under_investigation).
- Relations are edge paths, using edge names exactly. An edge is walked FROM -> TO; to walk it the other
  way use its reverse name. Paths may take several hops.
- Prefer the direct debtor/creditor relations over ultimate or intermediary ones.
- When a concept maps to several vertex types, give a relation path and an attribute source for each of
  them; give every way a relation holds (an owner and a joint holder both own an account).
- A concept with no vertex type of its own may be carried by an attribute of another record (a
  terminal id or an address on a login record): map it approximately to that record and name the
  attribute in the filter.
- confidence: exact when the schema has the thing itself; approximate when it needs a filter, a
  multi-hop path, a role, a code or string conversion, or is a near substitute; unmapped when nothing fits.
  Never invent a vertex, edge or attribute.
Give a short reason for every choice, naming the schema elements that justify it."""


def _models():
    from typing import Literal

    from pydantic import BaseModel, Field

    Conf = Literal["exact", "approximate", "unmapped"]

    class ConceptMap(BaseModel):
        concept: Literal[tuple(CONCEPTS)]  # type: ignore[valid-type]
        vertices: list[str] = Field(description="vertex types that hold this concept; empty if unmapped")
        filter: str = Field(description="condition selecting the right records, or ''")
        confidence: Conf
        reason: str

    class PathMap(BaseModel):
        edges: list[str] = Field(description="edge names walked from the source concept to the target, in order")
        filter: str = Field(description="condition on this path, or ''")

    class RelationMap(BaseModel):
        relation: Literal[tuple(RELATIONS)]  # type: ignore[valid-type]
        paths: list[PathMap] = Field(description="every way the relation holds; empty if unmapped")
        confidence: Conf
        reason: str

    class AttributeMap(BaseModel):
        attribute: Literal[tuple(ATTRIBUTES)]  # type: ignore[valid-type]
        sources: list[str] = Field(description="Vertex.attribute (or Edge.attribute) for each vertex type the "
                                             "concept maps to; empty if unmapped")
        transform: str = Field(description="conversion needed (string date format, code meaning), or ''")
        confidence: Conf
        reason: str

    class Proposal(BaseModel):
        concepts: list[ConceptMap]
        relations: list[RelationMap]
        attributes: list[AttributeMap]

    return Proposal


async def propose(schema: Schema, llm=None) -> dict:
    """Ask the model for a mapping, check it, and give it one chance to fix what the check rejected."""
    from google.genai import types

    from redthread.agent.llm import Llm
    from redthread.agent.schemas import json_schema

    llm = llm or Llm()
    proposal_model = _models()
    ask = (f"TARGET MODEL\n{target_model()}\n\nBANK SCHEMA\n{describe(schema)}\n\n"
           "Map every concept, relation and attribute of the target model (use unmapped where nothing fits).")
    rounds = []
    for _ in range(2):
        resp = await llm.generate([types.Content(role="user", parts=[types.Part.from_text(text=ask)])],
                                  system=PROPOSE_SYSTEM, response_schema=json_schema(proposal_model),
                                  temperature=0.0)
        mapping = proposal_model.model_validate_json(resp.text or "").model_dump()
        problems = validate(mapping, schema)
        rounds.append({"mapping": mapping, "problems": problems})
        if not problems:
            break
        ask += ("\n\nYOUR PREVIOUS MAPPING\n" + proposal_model(**mapping).model_dump_json()
                + "\n\nA CHECK AGAINST THE SCHEMA REJECTED THESE; correct only them and return the whole "
                  "mapping:\n- " + "\n- ".join(problems))
    return {"graph": schema.graph, "mapping": rounds[-1]["mapping"], "problems": rounds[-1]["problems"],
            "rounds": len(rounds), "first_round_problems": rounds[0]["problems"], "tokens": llm.tokens}
