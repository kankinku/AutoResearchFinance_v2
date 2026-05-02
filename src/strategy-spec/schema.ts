import { z } from "zod";

export const afStrategySpecSchema = z.object({
  version: z.literal("af-spec/v1"),
  name: z.string().min(1).default("AF Spec v1"),
  event: z.object({
    source: z
      .enum([
        "af_exhaustion",
        "event_floor",
        "reclaim",
        "compression_release",
      ])
      .default("af_exhaustion"),
    L1: z.number().int().positive().default(9),
    L2: z.number().int().positive().default(12),
    L3: z.number().int().positive().default(14),
    confirmBars: z.number().int().nonnegative().default(2),
    eventFloorBars: z.number().int().positive().nullable().default(null),
    eventWindowBars: z.number().int().positive().nullable().default(null),
  }),
  regime: z.object({
    trendMode: z.enum(["Strict", "Balanced", "Loose"]).default("Balanced"),
    useSupertrendFilter: z.boolean().default(false),
    riskOffRsi: z.number().default(45),
    maxExtPct: z.number().default(6),
  }),
  entry: z.object({
    primaryTrigger: z.string().min(1).default("bull_event"),
    cooldownBars: z.number().int().nonnegative().default(0),
    allowBearRebound: z.boolean().default(true),
    applyFilterToB1: z.boolean().default(false),
  }),
  slot: z.object({
    slotPct: z.number().positive().default(15),
    maxSlots: z.number().int().positive().default(18),
    useReplacement: z.boolean().default(true),
    replaceMinRank: z.number().int().nonnegative().default(3),
    replaceIfPnlBelow: z.number().default(-5),
  }),
  exit: z.object({
    weakRangeExit: z.boolean().default(true),
    maxHoldBars: z.number().int().positive().nullable().default(null),
    closeAllOnBearConfRiskOff: z.boolean().default(true),
    resetOnL3: z.boolean().default(false),
  }),
});

export type AfStrategySpec = z.infer<typeof afStrategySpecSchema>;

export function parseAfStrategySpec(value: unknown): AfStrategySpec {
  return afStrategySpecSchema.parse(value);
}
