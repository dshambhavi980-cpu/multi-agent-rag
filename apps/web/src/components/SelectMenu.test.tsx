import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SelectMenu } from "./SelectMenu";

const options = [
  { value: "auto", label: "Auto", description: "Choose the best route." },
  { value: "agentic", label: "Agentic", description: "Use the agent workflow." },
] as const;

test("selects an option and closes the menu", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(
    <SelectMenu
      label="Run mode"
      value="auto"
      options={[...options]}
      onChange={onChange}
    />,
  );

  await user.click(screen.getByRole("button", { name: "Run mode" }));
  expect(screen.getByRole("listbox", { name: "Run mode" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: /Auto/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  await user.click(screen.getByRole("option", { name: /Agentic/ }));
  expect(onChange).toHaveBeenCalledWith("agentic");
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
});

test("closes on Escape and an outside pointer event", async () => {
  const user = userEvent.setup();
  render(
    <div>
      <SelectMenu
        label="Run mode"
        value="auto"
        options={[...options]}
        onChange={vi.fn()}
      />
      <button type="button">Outside</button>
    </div>,
  );

  await user.click(screen.getByRole("button", { name: "Run mode" }));
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Run mode" }));
  await user.click(screen.getByRole("button", { name: "Outside" }));
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
});

test("supports disabled and fallback states", () => {
  const { rerender } = render(
    <SelectMenu
      label="Workspace"
      value="auto"
      options={[...options]}
      onChange={vi.fn()}
      disabled
      compact
    />,
  );
  expect(screen.getByRole("button", { name: "Workspace" })).toBeDisabled();

  rerender(
    <SelectMenu
      label="Workspace"
      value="missing"
      options={[]}
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByRole("button", { name: "Workspace" })).toHaveTextContent(
    "Select",
  );
});
