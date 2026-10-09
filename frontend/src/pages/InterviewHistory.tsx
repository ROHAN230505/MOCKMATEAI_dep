import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { EmptyState, ErrorState, Skeleton } from "../components/ui/States";
import { getInterviewHistory } from "../services/interviewApi";

const STATUS_LABEL: Record<string, string> = {
  in_progress: "In progress",
  completed: "Completed",
  abandoned: "Abandoned",
};

const STATUS_TONE: Record<string, "accent" | "success" | "neutral"> = {
  in_progress: "accent",
  completed: "success",
  abandoned: "neutral",
};

export function InterviewHistory() {
  const { data, isLoading, isError } = useQuery({ queryKey: ["interview-history"], queryFn: getInterviewHistory });

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <PageHeader
        eyebrow="Records"
        title="Interview History"
        description="Every session you've run, with its report."
        actions={
          <Link to="/interview/setup">
            <Button variant="primary" size="sm">
              New Interview
            </Button>
          </Link>
        }
      />

      {isLoading && (
        <div className="flex flex-col gap-3">
          {[0, 1, 2].map((index) => (
            <Card key={index} className="flex items-center justify-between gap-4">
              <div className="flex w-full flex-col gap-2.5">
                <Skeleton className="h-3.5 w-44" />
                <Skeleton className="h-3 w-56" />
              </div>
              <Skeleton className="h-6 w-24 shrink-0 rounded-pill" />
            </Card>
          ))}
        </div>
      )}

      {isError && <ErrorState message="Couldn't load your interview history." />}

      {data && data.length === 0 && (
        <EmptyState
          icon={
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 2M3.05 11a9 9 0 1 1 .5 4M3 4v5h5" />
            </svg>
          }
          title="You haven't done a mock interview yet"
          description="Your first one takes about ten minutes, and the report is ready right after."
          action={
            <Link to="/interview/setup">
              <Button variant="primary">Start your first one</Button>
            </Link>
          }
        />
      )}

      {data && data.length > 0 && (
        <div className="flex flex-col gap-3">
          {data.map((session, index) => (
            <motion.div
              key={session.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: index * 0.04, ease: [0.22, 1, 0.36, 1] }}
            >
              <Link to={`/interview/feedback/${session.id}`} className="block">
                <Card interactive className="group flex items-center justify-between gap-4 py-5">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-text">{session.roleTarget}</p>
                    <p className="mt-1.5 text-xs text-text-muted">
                      <span className="capitalize">{session.interviewType}</span> · {session.durationMinutes} min ·{" "}
                      {session.startedAt ? new Date(session.startedAt).toLocaleDateString() : "—"}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <Badge tone={STATUS_TONE[session.status] ?? "neutral"} dot>
                      {STATUS_LABEL[session.status] ?? session.status}
                    </Badge>
                    <span
                      aria-hidden="true"
                      className="text-text-subtle transition-transform duration-300 group-hover:translate-x-0.5 group-hover:text-text-muted"
                    >
                      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
                        <path strokeLinecap="round" strokeLinejoin="round" d="m9 6 6 6-6 6" />
                      </svg>
                    </span>
                  </div>
                </Card>
              </Link>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
