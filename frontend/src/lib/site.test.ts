import { describe, it, expect } from "vitest";
import { APP_NAME } from "@/lib/site";

describe("site config", () => {
  it("exposes the app name", () => {
    expect(APP_NAME).toBe("Stickmancer");
  });
});
