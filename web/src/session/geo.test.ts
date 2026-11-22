import { describe, expect, it } from "vitest";
import type { NetNode } from "../cascade/types";
import { haversineKm, nearestBus } from "./geo";

const node = (id: string, lon: number, lat: number, kv: number, in_service = true): NetNode =>
  ({ id, name: id, lon, lat, kv, zone: "centro_sur", map_nodes: [], in_service });

describe("nearestBus", () => {
  const nodes = [node("B000", -70.60, -33.45, 110), node("B001", -70.70, -33.50, 220), node("B002", -70.65, -33.45, 500, false), node("B003", -71.60, -33.00, 500)];

  it("skips buses under minKv and out of service", () => {
    expect(nearestBus(nodes, -70.60, -33.45)?.node.id).toBe("B001");
    expect(nearestBus(nodes, -70.60, -33.45, 500)?.node.id).toBe("B003");
    expect(nearestBus(nodes, -70.60, -33.45, 0)?.node.id).toBe("B000");
    expect(nearestBus(nodes, -70.60, -33.45, 600)).toBeNull();
  });

  it("measures great-circle distance in km", () => {
    expect(haversineKm(-70.6, -33.45, -70.6, -34.45)).toBeCloseTo(111.2, 0);
  });
});
