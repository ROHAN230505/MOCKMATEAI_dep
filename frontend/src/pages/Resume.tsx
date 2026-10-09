import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Badge } from "../components/ui/Badge";
import { Banner } from "../components/ui/Banner";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { ApiError } from "../lib/apiClient";
import { ExtractionError, extractResumeText } from "../lib/resumeExtract";
import { analyseResume, getResumeHistory } from "../services/practiceApi";
import type { ResumeAnalysis } from "../types/practice";

/**
 * Resume analyzer (Phase 8).
 *
 * The file never leaves this component. It is read, parsed to text and dropped;
 * only the text is submitted, and only what the analyser derives from it is
 * stored. That is stated on the screen too, because a candidate uploading a
 * document with their home address on it deserves to know where it goes.
 *
 * The score is presented with its components always visible rather than as a
 * headline number with a breakdown hidden behind a toggle. It is not a
 * prediction of any real ATS — those are proprietary and disagree — so the only
 * thing that makes it worth showing is that every part of it is checkable.
 */

function ScoreBar({ score }: { score: number }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-pill bg-surface-raised">
      <div
        className="h-full rounded-pill transition-[width] duration-500 ease-out"
        style={{
          width: `${Math.max(2, Math.min(100, score))}%`,
          background: "linear-gradient(90deg, var(--grad-a), var(--grad-b))",
        }}
      />
    </div>
  );
}

function AnalysisView({ analysis }: { analysis: ResumeAnalysis }) {
  if (analysis.atsScore === null) {
    return (
      <Card className="flex flex-col gap-3">
        <Banner tone="error" title="Nothing could be read from that file">
          {analysis.suggestions[0]}
        </Banner>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-[0.6875rem] font-semibold tracking-[0.16em] text-text-subtle uppercase">
              ATS readiness
            </p>
            <p className="tnum mt-1 text-4xl font-semibold text-text">{analysis.atsScore}</p>
          </div>
          <p className="max-w-md text-xs leading-relaxed text-text-subtle">
            {/* The honest framing, on the screen rather than only in a docstring.
                No product can predict a specific ATS; what it can do is measure
                the things all of them depend on. */}
            Not a prediction of any particular applicant tracking system — those are proprietary and
            disagree with each other. This measures the things they all depend on, and every part of
            it is shown below.
          </p>
        </div>
        <ScoreBar score={analysis.atsScore} />
      </Card>

      <Card>
        <CardHeader eyebrow="Breakdown" title="What produced that number" />
        <ul className="mt-4 flex flex-col gap-4">
          {analysis.components.map((component) => (
            <li key={component.name} className="flex flex-col gap-1.5">
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm font-medium text-text">{component.label}</span>
                <span className="flex items-baseline gap-2.5">
                  <span className="text-xs text-text-subtle">
                    {Math.round(component.weight * 100)}% of the score
                  </span>
                  <span className="tnum text-sm font-semibold text-text">
                    {Math.round(component.score)}
                  </span>
                </span>
              </div>
              <ScoreBar score={component.score} />
              <p className="text-xs leading-relaxed text-text-muted">{component.detail}</p>
            </li>
          ))}
          {analysis.unmeasured.includes("keywords") && (
            <li className="flex flex-col gap-1.5">
              <span className="text-sm font-medium text-text-subtle">Job description match</span>
              {/* A dashed empty track, exactly as the interview report renders an
                  unmeasured category. Not a 0% bar. */}
              <div className="h-1.5 w-full rounded-pill border border-dashed border-border" />
              <p className="text-xs leading-relaxed text-text-subtle">
                Not measured — paste a job description above and this becomes a quarter of the score.
                It is left out rather than counted as zero.
              </p>
            </li>
          )}
        </ul>
      </Card>

      {analysis.keywordGaps !== null && (
        <Card>
          <CardHeader
            eyebrow="Keywords"
            title={`${analysis.matchedKeywords?.length ?? 0} matched, ${analysis.keywordGaps.length} missing`}
          />
          <div className="mt-4 flex flex-col gap-3">
            {analysis.keywordGaps.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {analysis.keywordGaps.map((word) => (
                  <Badge key={word} tone="warning">
                    {word}
                  </Badge>
                ))}
              </div>
            )}
            {(analysis.matchedKeywords?.length ?? 0) > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {analysis.matchedKeywords!.map((word) => (
                  <Badge key={word} tone="success">
                    {word}
                  </Badge>
                ))}
              </div>
            )}
            <p className="text-xs leading-relaxed text-text-subtle">
              Add only the missing terms you genuinely have experience with, in the bullet where you
              actually did the work.
            </p>
          </div>
        </Card>
      )}

      <Card>
        <CardHeader eyebrow="Next steps" title="What to change" />
        <ul className="mt-4 flex flex-col gap-2.5">
          {analysis.suggestions.map((suggestion, index) => (
            <li key={index} className="flex gap-2.5 text-sm leading-relaxed text-text-muted">
              <span aria-hidden="true" className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
              {suggestion}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

export function Resume() {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);

  const [fileName, setFileName] = useState<string | null>(null);
  const [resumeText, setResumeText] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [extractError, setExtractError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [analysis, setAnalysis] = useState<ResumeAnalysis | null>(null);

  const history = useQuery({ queryKey: ["resumeHistory"], queryFn: getResumeHistory });

  const analyse = useMutation({
    mutationFn: () =>
      analyseResume({
        resumeText,
        jobDescriptionText: jobDescription.trim() || undefined,
        fileName: fileName ?? undefined,
      }),
    onSuccess: (data) => {
      setAnalysis(data);
      queryClient.invalidateQueries({ queryKey: ["resumeHistory"] });
      queryClient.invalidateQueries({ queryKey: ["dashboardSummary"] });
    },
  });

  async function handleFile(file: File | undefined) {
    if (!file) return;
    setExtractError(null);
    setNotice(null);
    setAnalysis(null);
    setExtracting(true);
    try {
      const result = await extractResumeText(file);
      setResumeText(result.text);
      setFileName(file.name);
      if (result.looksScanned) {
        setNotice(
          "Very little text came out of that file. If it's a scan or an image, an ATS can't read it either — export a text-based PDF.",
        );
      }
    } catch (error) {
      setResumeText("");
      setFileName(null);
      setExtractError(
        error instanceof ExtractionError ? error.message : "That file couldn't be read.",
      );
    } finally {
      setExtracting(false);
    }
  }

  const wordCount = resumeText.trim() ? resumeText.trim().split(/\s+/).length : 0;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        eyebrow="Practice"
        title="Resume analyzer"
        description="Check how a resume reads to an applicant tracking system, and against a specific job."
      />

      <Card className="flex flex-col gap-5">
        <div className="flex flex-col gap-2">
          <span className="text-[0.8125rem] font-medium text-text">Your resume</span>
          <div className="flex flex-wrap items-center gap-3">
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.txt,.md,application/pdf,text/plain"
              className="hidden"
              onChange={(event) => handleFile(event.target.files?.[0])}
            />
            <Button
              variant="secondary"
              loading={extracting}
              onClick={() => fileInput.current?.click()}
            >
              Choose a PDF
            </Button>
            {fileName && (
              <span className="text-xs text-text-muted">
                {fileName} · {wordCount} words read
              </span>
            )}
          </div>
          <p className="text-xs leading-relaxed text-text-subtle">
            The file is read in your browser and never uploaded. Only the extracted text is sent, and
            only the scores derived from it are stored — not the text, not the file, not the filename.
          </p>
        </div>

        {extractError && <Banner tone="error">{extractError}</Banner>}
        {notice && <Banner tone="warning">{notice}</Banner>}

        <div className="flex flex-col gap-2">
          <label htmlFor="jd" className="text-[0.8125rem] font-medium text-text">
            Job description <span className="text-text-subtle">— optional</span>
          </label>
          <textarea
            id="jd"
            value={jobDescription}
            onChange={(event) => setJobDescription(event.target.value)}
            rows={5}
            placeholder="Paste the advert to see which of its terms your resume already uses."
            className="w-full resize-y rounded-control border border-border bg-surface px-3.5 py-3 text-sm leading-relaxed text-text placeholder:text-text-subtle focus:border-border-strong focus:ring-2 focus:ring-accent/30 focus:outline-none"
          />
          <p className="text-xs text-text-subtle">
            Without one, keyword matching is left unmeasured rather than counted as zero.
          </p>
        </div>

        {analyse.isError && (
          <Banner tone="error">
            {analyse.error instanceof ApiError ? analyse.error.message : "Couldn't analyse that resume."}
          </Banner>
        )}

        <Button
          className="self-start"
          loading={analyse.isPending}
          disabled={wordCount === 0}
          onClick={() => analyse.mutate()}
        >
          Analyse
        </Button>
      </Card>

      {analysis && <AnalysisView analysis={analysis} />}

      {(history.data?.length ?? 0) > 0 && (
        <Card>
          <CardHeader eyebrow="History" title="Past analyses" />
          <ul className="mt-4 flex flex-col gap-2.5">
            {history.data!.slice(0, 8).map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-4 text-sm">
                <span className="text-text-muted">
                  {item.analyzedAt ? new Date(item.analyzedAt).toLocaleString() : "—"}
                  {item.hadJobDescription && (
                    <span className="ml-2 text-xs text-text-subtle">matched to a job</span>
                  )}
                </span>
                <span className="tnum text-text">{item.atsScore ?? "—"}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
