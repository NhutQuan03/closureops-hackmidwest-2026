import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  AssistantMascot,
  mascotAssets,
  mascotStateLabels,
  type MascotState,
} from "../../src/components/AssistantMascot";

describe("user-provided static mascot artwork", () => {
  it.each(Object.keys(mascotAssets) as MascotState[])(
    "labels %s without inventing an animation",
    (state) => {
      const markup = renderToStaticMarkup(
        createElement(AssistantMascot, { state }),
      );
      expect(markup).toContain(
        state === "high_risk"
          ? "/mascot/snoopy-high-risk.png"
          : "/mascot/snoopy-idle.png",
      );
      expect(markup).toContain(mascotStateLabels[state]);
      expect(markup).toContain("prefers-reduced-motion: reduce");
      expect(markup).not.toContain("<svg");
      expect(mascotAssets[state].animated).toBeUndefined();
    },
  );
  it("retains state information if replacement artwork is missing", () => {
    const markup = renderToStaticMarkup(
      createElement(AssistantMascot, { state: "review_required", assets: {} }),
    );
    expect(markup).toContain("Artwork unavailable");
    expect(markup).toContain("Manual review required");
  });
});
