import { useEffect, useRef } from "react";
import { buildField, DEFAULT_FIELD, INK, LUMINOUS } from "./particleField";
import { useThemeStore } from "../../store/themeStore";

/**
 * The nebula.
 *
 * ## Where it renders, and at what strength
 *
 * The design brief asked for the particle field to be removed, and it was —
 * from everywhere. It came back by request, first on the entrance pages only,
 * and now throughout the product. The original objection still stands, though,
 * so it is answered with strength rather than with absence: a landing page has
 * ninety seconds to be memorable and nothing to compete with, so it runs the
 * field at 1; a dashboard has numbers someone is trying to read, so it runs at
 * the theme `--mm-field` cap and the field becomes texture in peripheral vision
 * instead of a picture. `Room` — one light, one grain, no motion — still sits
 * underneath everywhere.
 *
 * The one screen with no field at all is the live interview, and that falls out
 * of the routing rather than from a pathname test here: it renders outside
 * `AppLayout`, so there is nothing to drift out of sync.
 *
 * ## Cost
 *
 * three.js is ~866 KB, which is why it was removed in the first place. It is
 * imported dynamically here, so it is a separate chunk fetched *after* first
 * paint and only on the two routes that use it; the landing page renders its
 * text without waiting for it, and the app never downloads it at all.
 *
 * Bows out entirely for reduced motion and for a missing WebGL context. In both
 * cases the page keeps `Room` underneath, so the fallback is a designed
 * background rather than a blank rectangle.
 */
export function Nebula({
  className = "",
  /** `absolute` when the caller places this inside a panel rather than behind the page. */
  anchor = "fixed",
  /**
   * A hard ceiling on the canvas opacity, and the reason the legibility case is
   * provable rather than hoped for.
   *
   * The field accumulates, so its densest region clips to the palette extreme
   * no matter how low the per-particle alpha is — which means the shader cannot
   * bound the brightest (or, in light mode, darkest) pixel a panel might sit
   * on. A CSS opacity on the host can: whatever the GL does, the composited
   * result is at most this far from the page ground.
   *
   * Left undefined it reads `--mm-field` from the theme, so the cap is per-theme
   * with no prop plumbing and nothing to run on a theme flip. Pass 1 where the
   * field is the subject rather than the backdrop.
   */
  intensity,
}: {
  className?: string;
  anchor?: "fixed" | "absolute";
  intensity?: number;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  // Palette and blending both depend on the theme, and neither can be swapped
  // on a live material without rebuilding the buffers — so this is an effect
  // dependency rather than a ref. A theme flip is a rare, user-initiated event;
  // paying a context rebuild for it is the right trade.
  const theme = useThemeStore((state) => state.resolved);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const light = theme === "light";
    const host = hostRef.current;
    if (!host) return;

    let disposed = false;
    let cleanup: (() => void) | undefined;

    void (async () => {
      const THREE = await import("three");
      if (disposed || !hostRef.current) return;

      let renderer: import("three").WebGLRenderer;
      try {
        renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false, powerPreference: "low-power" });
      } catch {
        return; // No WebGL. `Room` is already behind this.
      }

      // Capped at 1.5 rather than the device value: at 8-11k additive points a
      // 3x retina buffer costs several times the fill for no visible gain.
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
      renderer.setSize(host.clientWidth, host.clientHeight, false);
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";
      renderer.domElement.style.display = "block";
      host.appendChild(renderer.domElement);

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(52, host.clientWidth / host.clientHeight, 0.1, 200);
      camera.position.set(0, 13.5, 33);
      camera.lookAt(0, 0, 0);

      const field = buildField({ ...DEFAULT_FIELD, palette: light ? INK : LUMINOUS });
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.BufferAttribute(field.positions, 3));
      geometry.setAttribute("color", new THREE.BufferAttribute(field.colors, 3));
      geometry.setAttribute("aScale", new THREE.BufferAttribute(field.scales, 1));

      // A round, soft point, drawn in the shader. A texture would be another
      // request and another asset to lose; `gl_PointCoord` is free.
      // Additive on a dark ground, normal on a light one.
      //
      // Additive is what makes a galaxy: overlapping points sum, so the hub
      // blooms. On paper that same summing is fatal — every channel clips at
      // 1.0, so the densest, most striking part of the picture converges on
      // white and white on warm stone is 1.14:1. NormalBlending converges on
      // the source colour instead of running past it, which is what lets the
      // ink palette stay ink all the way into the hub.
      //
      // `material.premultipliedAlpha` is left at its default of false, so three
      // sets blendFuncSeparate(SRC_ALPHA, ONE_MINUS_SRC_ALPHA, ONE,
      // ONE_MINUS_SRC_ALPHA): rgb converges on the tint, alpha on 1, and the
      // buffer ends up correctly premultiplied — which is what the renderer own
      // `premultipliedAlpha: true` composite then expects.
      const material = new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        blending: light ? THREE.NormalBlending : THREE.AdditiveBlending,
        uniforms: { uSize: { value: 2.9 * renderer.getPixelRatio() }, uOpacity: { value: 0.0 } },
        vertexShader: `
          attribute float aScale;
          uniform float uSize;
          varying vec3 vColor;
          void main() {
            vColor = color;
            vec4 mv = modelViewMatrix * vec4(position, 1.0);
            gl_PointSize = uSize * aScale * (30.0 / -mv.z);
            gl_Position = projectionMatrix * mv;
          }
        `,
        fragmentShader: `
          uniform float uOpacity;
          varying vec3 vColor;
          void main() {
            float d = length(gl_PointCoord - vec2(0.5));
            if (d > 0.5) discard;
            // Squared falloff: a linear edge on an additive point reads as a
            // hard disc once thousands of them overlap.
            float a = pow(1.0 - d * 2.0, 2.0);
            gl_FragColor = vec4(vColor, a * uOpacity);
          }
        `,
      });
      material.vertexColors = true;

      const points = new THREE.Points(geometry, material);
      points.rotation.x = 0.32;
      scene.add(points);

      let raf = 0;
      let running = true;
      const started = performance.now();

      // --- mouse parallax --------------------------------------------------
      // The canvas is `pointer-events: none` by design, so it can never receive
      // a pointer event itself; the listener goes on the window and reads
      // normalised coordinates from there.
      //
      // Tracked into plain numbers and applied by interpolation inside the
      // existing frame loop — not applied on the event. A pointermove can fire
      // several times between two frames, and moving the camera per event does
      // work the display will never show.
      let aimX = 0;
      let aimY = 0;
      let tiltX = 0;
      let tiltY = 0;
      const onPointer = (event: PointerEvent) => {
        aimX = (event.clientX / window.innerWidth) * 2 - 1;
        aimY = (event.clientY / window.innerHeight) * 2 - 1;
      };
      window.addEventListener("pointermove", onPointer, { passive: true });

      // Aspect is interpolated too, so a dragged window resize glides instead
      // of stepping. `setSize` still happens immediately — the drawing buffer
      // has to match the element or the image stretches.
      let aspect = camera.aspect;

      const resize = () => {
        if (!hostRef.current) return;
        const { clientWidth: w, clientHeight: h } = hostRef.current;
        if (w === 0 || h === 0) return;
        renderer.setSize(w, h, false);
        aspect = w / h;
      };
      const observer = new ResizeObserver(resize);
      observer.observe(host);

      const frame = () => {
        if (!running) return;
        const elapsed = (performance.now() - started) / 1000;

        // One slow rotation. Anything faster turns a backdrop into something the
        // eye tracks instead of something it sits behind.
        points.rotation.y = elapsed * 0.026;

        // Parallax: the camera moves, the galaxy does not. Moving the object
        // would swing it against a fixed viewpoint, which reads as the thing
        // being dragged; moving the viewpoint reads as looking around it.
        // Deliberately shallow — a few degrees at the extremes.
        tiltX += (aimX - tiltX) * 0.045;
        tiltY += (aimY - tiltY) * 0.045;
        camera.position.x = tiltX * 3.4;
        camera.position.y = 13.5 - tiltY * 2.1;
        camera.position.z = 33 - Math.abs(tiltX) * 0.8;
        camera.lookAt(0, 0, 0);

        if (Math.abs(camera.aspect - aspect) > 0.0005) {
          camera.aspect += (aspect - camera.aspect) * 0.18;
          camera.updateProjectionMatrix();
        }

        // Faded in rather than appearing: the chunk lands after first paint, and
        // a field that pops into existence advertises having been late.
        material.uniforms.uOpacity.value = Math.min(elapsed / 1.6, 1) * 0.9;
        renderer.render(scene, camera);
        raf = requestAnimationFrame(frame);
      };
      raf = requestAnimationFrame(frame);

      // A backgrounded tab should not hold the GPU awake.
      const onVisibility = () => {
        const visible = document.visibilityState === "visible";
        if (visible && !running) {
          running = true;
          raf = requestAnimationFrame(frame);
        } else if (!visible) {
          running = false;
          cancelAnimationFrame(raf);
        }
      };
      document.addEventListener("visibilitychange", onVisibility);

      cleanup = () => {
        running = false;
        cancelAnimationFrame(raf);
        document.removeEventListener("visibilitychange", onVisibility);
        window.removeEventListener("pointermove", onPointer);
        observer.disconnect();
        geometry.dispose();
        material.dispose();
        renderer.dispose();
        renderer.domElement.remove();
      };
    })();

    return () => {
      disposed = true;
      cleanup?.();
    };
  }, [theme]);

  return (
    <div
      ref={hostRef}
      aria-hidden="true"
      // Undefined falls through to the theme token, so light and dark each get
      // their own measured ceiling without this component knowing either one.
      style={{ opacity: intensity ?? "var(--mm-field, 1)" }}
      className={`pointer-events-none ${anchor} inset-0 -z-10 overflow-hidden ${className}`}
    />
  );
}
