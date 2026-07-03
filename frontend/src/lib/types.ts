// TypeScript mirror of the backend contract (backend/app/models.py + schemas.py).
// Keep in sync: if a Pydantic model changes, change the matching type here.

export type Element = "physical" | "fire" | "water" | "nature" | "lightning";

export type ComponentType =
  | "damage"
  | "heal"
  | "dot"
  | "hot"
  | "stat"
  | "defense"
  | "barrier"
  | "control"
  | "summon"
  | "item";

export type ComponentTarget = "self" | "opponent";

export type StatKind = "power" | "speed" | "damage_taken";

export type DefenseSubtype = "shield" | "dodge" | "reflect";

export type EffectKind = "dot" | "hot" | "stat" | "defense" | "control";

export type Template =
  | "projectile"
  | "beam"
  | "melee"
  | "aoe_burst"
  | "shield_raise"
  | "dodge"
  | "reflect"
  | "buff_aura"
  | "debuff_cloud"
  | "heal_glow";

export type Outcome =
  | "hit_knockback"
  | "blocked"
  | "partial"
  | "dodged"
  | "reflected"
  | "healed"
  | "applied"
  | "ticked"
  | "shattered"
  | "fizzled";

export type Shape = "circle" | "rect" | "triangle" | "line" | "zigzag" | "ring" | "star";

export type Size = "small" | "medium" | "large";

export interface Primitive {
  shape: Shape;
  size: Size;
  color: string;
  offset: [number, number];
}

export interface Visual {
  primitives: Primitive[];
}

export interface EffectComponent {
  type: ComponentType;
  target: ComponentTarget;
  element: Element;
  power: number | null;
  magnitude: number | null;
  duration: number | null;
  stat: StatKind | null;
  subtype: DefenseSubtype | null;
  source_id: string | null;
  target_id: string | null;
  // summon only
  name?: string | null;
  hp?: number | null;
  tags?: string[] | null;
  item?: string | null;
}

export interface Action {
  components: EffectComponent[];
  element: Element;
  speed: number;
  template: Template;
  visual: Visual;
  flavor_text: string;
}

export type Side = "p1" | "p2";

export interface ActiveEffect {
  kind: EffectKind;
  turns_remaining: number;
  source: Side;
  label: string;
  per_turn: number;
  element: Element;
  stat: StatKind | null;
  magnitude: number;
  subtype: DefenseSubtype | null;
  power: number;
  speed: number;
}

export interface Barrier {
  pool: number;
  element: Element;
  source: Side;
  label: string;
}

export type UnitKind = "stickman" | "entity";

export interface Weapon {
  name: string;
  element: Element;
  power: number;
}

export interface Unit {
  id: string;
  name: string;
  kind: UnitKind;
  hp: number;
  max_hp: number;
  effects: ActiveEffect[];
  barriers: Barrier[];
  stun_immunity: number;
  weapon: Weapon | null;
  tags: string[];
  items: string[];
}

export interface SideState {
  name: string;
  mana: number;
  cooldowns: Record<string, number>;
  stickman: Unit;
  entities: Unit[];
}

export interface GameState {
  round: number;
  active: Side;
  p1: SideState;
  p2: SideState;
}

export interface StateDelta {
  p1_hp: number;
  p2_hp: number;
  p1_mana: number;
  p2_mana: number;
}

export interface EffectSummary {
  kind: string;
  stat?: StatKind | null;
  magnitude?: number | null;
  duration?: number | null;
  per_turn?: number | null;
  absorbed?: number | null;
  barrier_absorbed?: number | null;
  barrier_remaining?: number | null;
  label?: string;
}

export interface ResolutionEvent {
  actor: Side;
  target: Side;
  kind: string; // component type, or "dot_tick" / "hot_tick"
  element: Element;
  outcome: Outcome;
  amount: number;
  effect: EffectSummary | null;
  template: Template | null;
  narration: string;
  state_delta: StateDelta;
  // The specific units involved (P3.1b) — playback says "Orc hits Archer".
  actor_id?: string | null;
  target_id?: string | null;
  actor_name?: string | null;
  target_name?: string | null;
}

export interface ResolveResult {
  events: ResolutionEvent[];
  state: GameState;
  match_over: boolean;
  winner: Side | "draw" | null;
}

export interface MatchConfig {
  hp_max: number;
  mana_max: number;
  mana_regen_per_turn: number;
  rewrites_per_turn: number;
  max_turns: number;
}

// ---- API request/response shapes -------------------------------------------

export interface JudgeRequest {
  prompt: string;
  // The full battlefield — the judge is stateful (resolves unit references).
  state: GameState;
  match_id: string;
  rewrites_remaining?: number;
}

export interface JudgeResponse {
  action: Action | null;
  mana_cost: number | null;
  affordable: boolean | null;
  on_cooldown: boolean | null;
  error: string | null;
  message: string | null;
  rewrites_remaining: number;
}

export interface ResolveRequest {
  match_id: string;
  state: GameState;
  action: Action | null; // null = the active player is stunned and skips
}

export interface NewMatchResponse {
  match_id: string;
  state: GameState;
  config: MatchConfig;
}

// ---- Frontend-only: a running combat history (no backend mirror) -----------

export interface LedgerEntry {
  round: number;
  actor: Side;
  events: ResolutionEvent[];
}
