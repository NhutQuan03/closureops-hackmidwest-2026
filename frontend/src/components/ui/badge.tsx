import type { ComponentProps } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const variants = cva(
  "badge inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[10px] font-semibold tracking-wide",
  {
    variants: {
      tone: {
        purple: "border-primary/25 bg-primary/10 text-purple-300",
        amber: "border-warning/25 bg-warning/10 text-warning",
        red: "border-danger/25 bg-danger/10 text-danger",
        blue: "border-info/25 bg-info/10 text-info",
        green: "border-success/25 bg-success/10 text-success",
        neutral: "border-border bg-secondary text-muted-foreground",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);
export function Badge({
  className,
  tone,
  ...props
}: ComponentProps<"span"> & VariantProps<typeof variants>) {
  return (
    <span
      data-slot="badge"
      className={cn(variants({ tone }), className)}
      {...props}
    />
  );
}
