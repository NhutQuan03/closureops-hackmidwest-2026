import { useState } from "react";
import { cn } from "../lib/utils";
import { useMotionPreference } from "../hooks/MotionPreference";

export type MascotState =
  | "idle"
  | "monitoring"
  | "analyzing"
  | "watch"
  | "caution"
  | "high_risk"
  | "review_required"
  | "awaiting_approval"
  | "resolved";
export interface MascotAsset {
  animated?: string;
  static: string;
}
export interface AssistantMascotProps {
  state: MascotState;
  size?: "small" | "large";
  assets?: Partial<Record<MascotState, MascotAsset>>;
}
const idleAsset: MascotAsset = { static: "/mascot/snoopy-idle.png" };
// These user-provided PNGs are static. Reusing artwork does not add an event,
// animation, or severity; the label always describes the verified state.
export const mascotAssets: Record<MascotState, MascotAsset> = {
  idle: idleAsset,
  monitoring: idleAsset,
  analyzing: idleAsset,
  watch: idleAsset,
  caution: idleAsset,
  high_risk: { static: "/mascot/snoopy-high-risk.png" },
  review_required: idleAsset,
  awaiting_approval: idleAsset,
  resolved: idleAsset,
};
export const mascotStateLabels: Record<MascotState, string> = {
  idle: "Standing by",
  monitoring: "Reading saved evaluation",
  analyzing: "Analysis in progress",
  watch: "Watch",
  caution: "Caution",
  high_risk: "High risk · simulated closure recommendation",
  review_required: "Manual review required",
  awaiting_approval: "Human approval required",
  resolved: "Recorded manager action",
};

export function AssistantMascot({
  state,
  size = "large",
  assets = mascotAssets,
}: AssistantMascotProps) {
  const [failedAsset, setFailedAsset] = useState<string | null>(null);
  const { reducedMotion } = useMotionPreference();
  const asset = assets[state];
  const usable = asset && failedAsset !== asset.static;
  return (
    <div
      className={cn("assistant-mascot", `mascot-${size}`, `mascot-${state}`)}
      data-state={state}
      role="img"
      aria-label={`Snoopy, ClosureOps demo companion: ${mascotStateLabels[state]}`}
    >
      {usable ? (
        <picture key={asset.static}>
          <source
            media="(prefers-reduced-motion: reduce)"
            srcSet={asset.static}
          />
          <img
            src={reducedMotion ? asset.static : asset.animated || asset.static}
            alt=""
            onError={() => setFailedAsset(asset.static)}
          />
        </picture>
      ) : (
        <span className="mascot-asset-unavailable">
          Artwork unavailable · {mascotStateLabels[state]}
        </span>
      )}
    </div>
  );
}
