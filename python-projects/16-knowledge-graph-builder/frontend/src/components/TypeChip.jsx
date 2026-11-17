import { typeColor, typeLabel } from "../lib/graph";

export default function TypeChip({ type }) {
  return (
    <span className="chip" style={{ "--c": typeColor(type) }}>
      <span className="swatch" aria-hidden="true" />
      {typeLabel(type)}
    </span>
  );
}
