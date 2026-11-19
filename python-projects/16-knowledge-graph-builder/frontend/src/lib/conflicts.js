// Words for conflicts between facts and for the verdict of a claim check (the server decides which; this only says it plainly).

export const KIND_TEXT = {
  different_object: "Two different answers for a relation that has one at a time",
  different_value: "Two different values",
  different_holder: "Two holders of a role that has one at a time",
  reversed: "The same relation stated both ways round",
};

export function kindText(kind) {
  return KIND_TEXT[kind] || "Facts that may not both be true";
}

const VERDICTS = {
  supported: { label: "Supported", tone: "ok" },
  supported_other_dates: { label: "Supported, but other dates", tone: "work" },
  contradicted: { label: "Contradicted", tone: "bad" },
  not_found: { label: "Not in the documents", tone: "muted" },
  unclear: { label: "Unclear", tone: "wait" },
};

export function verdictInfo(verdict) {
  return VERDICTS[verdict] || VERDICTS.unclear;
}

const ROLES = { supports: "supports", contradicts: "contradicts", related: "related" };

export function roleLabel(role) {
  return ROLES[role] || role;
}

export function roleTone(role) {
  return role === "supports" ? "ok" : role === "contradicts" ? "bad" : "muted";
}

/** What a person can do with one open conflict, in the order they are shown */
export function actionsFor(conflict) {
  const acts = [
    { id: "keep_a", label: "Trust the first" },
    { id: "keep_b", label: "Trust the second" },
    { id: "both", label: "Both are true" },
  ];
  if (conflict.can_end_earlier) acts.push({ id: "succession", label: "The earlier one ended when the later began" });
  return acts;
}

/** "since 2020" / "2012 – 2019" / "no date" for a fact's period */
export function periodText(from, to) {
  if (from && to) return `${from} – ${to}`;
  if (from) return `since ${from}, no end stated`;
  if (to) return `until ${to}`;
  return "no date";
}
