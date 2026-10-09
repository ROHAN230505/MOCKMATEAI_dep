import { Link } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { BrandLockup } from "../components/brand/Brand";
import { ThemeToggle } from "../components/ThemeToggle";
import { Room } from "../components/room/Room";
import { Nebula } from "../components/room/Nebula";

export function NotFound() {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 text-center">
      <Room />
      <Nebula />

      <div className="absolute top-4 right-4 z-10 sm:top-6 sm:right-6">
        <ThemeToggle />
      </div>
      <div className="absolute top-5 left-5 z-10 sm:top-7 sm:left-7">
        <BrandLockup to="/" size="xs" />
      </div>

      <div className="relative z-10 flex flex-col items-center gap-5">
        <p className="tnum display text-8xl sm:text-9xl">
          <span className="text-gradient-accent">404</span>
        </p>
        <h1 className="display text-2xl text-text sm:text-3xl">This page doesn't exist</h1>
        <p className="max-w-sm text-sm leading-relaxed text-text-muted">
          The link may be broken, or the page may have moved. Everything you've built is still where you left
          it.
        </p>
        <div className="mt-2 flex flex-col gap-3 sm:flex-row">
          <Link to="/dashboard">
            <Button variant="primary">Go to dashboard</Button>
          </Link>
          <Link to="/">
            <Button variant="ghost">Back home</Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
