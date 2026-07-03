// TypeScript mirror of the backend contract (backend/app/models.py + schemas.py).
// Keep in sync: if a Pydantic model changes, change the matching type here.

export type Category = "attack" | "defense" | "buff" | "debuff" | "heal";

export type Subtype =
  | "projectile"
  | "beam"
  | "melee"
  | "aoe"
  | "shield"
  | "dodge"
  | "reflect"
  | "buff"
  | "debuff"
  | "heal";

export type Element = "physical" | "fire" | "water" | "nature" | "lightning";

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

export type Stat = "power" | "speed";

export type Outcome =
  | "hit_knockback"
  | "blocked"
  | "partial"
  | "dodged"
  | "reflected"
  | "healed"
  | "buffed"
  | "debuffed"
  | "defended"
  | "fizzled";

export type Shape =
  | "circle"
  | "rect"
  | "triangle"
  | "line"
  | "zigzag"
  | "ring"
  | "star";

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

export interface JudgedAction {
  category: Category;
  subtype: Subtype;
  element: Element;
  power: number;
  speed: number;
  stat: Stat | null;
  template: Template | null;
  visual: Visual;
  flavor_text: string;
}

export interface ActiveEffect {
  power_shift: number;
  speed_shift: number;
  turns_remaining: number;
}

export interface PlayerState {
  name: string;
  hp: number;
  mana: number;
  cooldowns: Partial<Record<Category, number>>;
  active_buff: ActiveEffect | null;
  active_debuff: ActiveEffect | null;
}

export interface GameState {
  turn: number;
  p1: PlayerState;
  p2: PlayerState;
}

export interface StateDelta {
  p1_hp: number;
  p2_hp: number;
  p1_mana: number;
  p2_mana: number;
}

export type Side = "p1" | "p2";

export interface ResolutionEvent {
  actor: Side;
  template: Template;
  outcome: Outcome;
  damage: number;
  narration: string;
  state_delta: StateDelta;
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

export interface PlayerSnapshot {
  mana: number;
  cooldowns: Partial<Record<Category, number>>;
}

export interface JudgeRequest {
  prompt: string;
  player: PlayerSnapshot;
  match_id: string;
  rewrites_remaining?: number;
}

export interface JudgeResponse {
  action: JudgedAction | null;
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
  p1_action: JudgedAction;
  p2_action: JudgedAction;
}

export interface NewMatchResponse {
  match_id: string;
  state: GameState;
  config: MatchConfig;
}
