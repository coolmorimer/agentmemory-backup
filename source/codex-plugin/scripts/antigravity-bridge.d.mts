//#region src/hooks/antigravity-bridge.d.ts
type Json = Record<string, unknown>;
declare function normalizePayload(event: string, raw: Json): Json;
declare function targetsFor(event: string, raw: Json): string[];
declare function responseFor(event: string): string;
//#endregion
export { normalizePayload, responseFor, targetsFor };
//# sourceMappingURL=antigravity-bridge.d.mts.map