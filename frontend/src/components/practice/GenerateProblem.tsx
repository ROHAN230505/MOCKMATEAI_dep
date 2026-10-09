import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Banner } from "../ui/Banner";
import { Button } from "../ui/Button";
import { generateDsaProblem } from "../../services/practiceApi";
import { ApiError } from "../../lib/apiClient";
import type { Difficulty } from "../../types/practice";

const TOPICS: { value: string; label: string }[] = [
  { value: "arrays", label: "Arrays" },
  { value: "strings", label: "Strings" },
  { value: "linked_lists", label: "Linked lists" },
  { value: "trees", label: "Trees" },
  { value: "graphs", label: "Graphs" },
  { value: "dynamic_programming", label: "Dynamic programming" },
  { value: "recursion_backtracking", label: "Recursion & backtracking" },
  { value: "sorting_searching", label: "Sorting & searching" },
  { value: "greedy", label: "Greedy" },
];

const DIFFICULTIES: Difficulty[] = ["easy", "medium", "hard"];

/**
 * Write a problem that has never existed before.
 *
 * ## Why this is a button rather than the default
 *
 * The curated bank's test cases are verified by *executing* a reference
 * solution. A generated problem's are verified by independently recomputing
 * every expected output and requiring exact agreement — which catches the
 * arithmetic slips that make up most bad test cases, but is not the same
 * guarantee. Keeping generation deliberate means a candidate who wants the
 * stronger guarantee simply picks from the list, and nobody is opted in to the
 * weaker one without knowing.
 *
 * ## Why the wait is stated up front
 *
 * It is two provider round trips, so several seconds, and there is nothing
 * honest to show as progress: revealing the problem before verification
 * finishes would mean sometimes taking it away again. Saying "a few seconds"
 * before the click is better than a spinner that looks stuck after three.
 */
export function GenerateProblem({ onGenerated }: { onGenerated: (problemId: string) => void }) {
  const [topic, setTopic] = useState(TOPICS[0].value);
  const [difficulty, setDifficulty] = useState<Difficulty>("easy");

  const generate = useMutation({
    mutationFn: () => generateDsaProblem({ topic, difficulty }),
    onSuccess: (problem) => onGenerated(problem.id),
  });

  const failed = generate.error instanceof ApiError ? generate.error : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className="text-micro text-text-subtle">Topic</span>
          <select
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            disabled={generate.isPending}
            className="rounded-control border border-border bg-surface px-2.5 py-1.5 text-small text-text"
          >
            {TOPICS.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-micro text-text-subtle">Difficulty</span>
          <select
            value={difficulty}
            onChange={(event) => setDifficulty(event.target.value as Difficulty)}
            disabled={generate.isPending}
            className="rounded-control border border-border bg-surface px-2.5 py-1.5 text-small text-text capitalize"
          >
            {DIFFICULTIES.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>

        <Button onClick={() => generate.mutate()} loading={generate.isPending} size="md">
          {generate.isPending ? "Writing and checking…" : "Generate a new problem"}
        </Button>
      </div>

      <p className="text-xs leading-relaxed text-text-subtle">
        Takes a few seconds: the problem is written, then every expected answer is worked out a
        second time independently. It is only shown if both agree.
      </p>

      {failed && (
        <Banner tone={failed.code === "generation_unavailable" ? "warning" : "error"}>
          {failed.message}
        </Banner>
      )}
    </div>
  );
}
