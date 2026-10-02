import { Orb } from "@yogesharc/thinking-orbs";

export function Thinking() {
  return (
    <span className="flex items-center gap-2 text-sm text-zinc-300">
      <Orb state="reasoning" />
      Thinking
    </span>
  );
}

export default Thinking;
