import { act, renderHook } from "@testing-library/react";

import { useOnlineStatus } from "./useOnlineStatus";

test("tracks browser connectivity events", async () => {
  const online = vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
  const { result } = renderHook(() => useOnlineStatus());
  expect(result.current).toBe(true);

  await act(() => window.dispatchEvent(new Event("offline")));
  expect(result.current).toBe(false);
  await act(() => window.dispatchEvent(new Event("online")));
  expect(result.current).toBe(true);
  online.mockRestore();
});
