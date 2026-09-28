export type Action = "fix_stale" | "remove" | "refactor_instead" | "rewrite" | "keep";
export type RuleVersion = "legacy-round3" | "current";

export interface CodeFacts {
  readonly docComment: boolean;
  readonly dates: ReadonlyArray<string>;
  readonly ticketRefs: ReadonlyArray<string>;
  readonly unownedTodo: boolean;
}

export interface CommentCase {
  readonly round: string;
  readonly caseId: string;
  readonly ruleVersion: RuleVersion;
  readonly facts: CodeFacts;
  readonly probabilities: Readonly<Record<string, number>>;
}

export interface PolicyInput {
  readonly caseId: string;
  readonly ruleVersion: RuleVersion;
  readonly facts: CodeFacts;
}

export interface ReplayRow {
  readonly round: string;
  readonly caseId: string;
  readonly action: Action;
  readonly escalated: boolean;
  readonly reasons: ReadonlyArray<string>;
}
