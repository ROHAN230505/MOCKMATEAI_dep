/**
 * Resume text extraction, in the browser (Phase 8).
 *
 * ## Why here and not on the server
 *
 * A resume is the most PII-dense document a candidate owns: legal name, home
 * address, phone number, email, and their whole employment history. Every other
 * media pipeline in this product already keeps the raw artifact on the
 * candidate's own machine — audio in Phase 2, video in Phase 5B, their code in
 * Phase 7 — and the resume is the last document that should break that pattern.
 *
 * So the file is read, parsed and discarded here. What crosses the network is
 * extracted text, and what is stored is only what the analyser derived from it.
 * The file itself is never uploaded and `file_storage_url` records that plainly.
 *
 * ## Worker, and why it is pinned locally
 *
 * pdf.js runs its parser in a Web Worker, and its default worker URL points at a
 * CDN. Same objection as MediaPipe and Pyodide: an interview product cannot
 * depend on a third-party host, and a candidate's resume is the last thing that
 * should be parsed by code fetched from one at page load. The worker is served
 * from our own origin, from the pinned package.
 */

/** Vite resolves this at build time and emits the worker as a local asset. */
const WORKER_URL = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).href;

/** A resume beyond this is not a resume, and parsing it would block the tab. */
export const MAX_FILE_BYTES = 10 * 1024 * 1024;
export const MAX_PAGES = 15;

export interface ExtractionResult {
  text: string;
  pageCount: number;
  /** True when the PDF yielded almost nothing — usually a scan or an image. */
  looksScanned: boolean;
}

export class ExtractionError extends Error {}

/**
 * Text from a PDF, page by page.
 *
 * Items are joined with spaces and pages with blank lines rather than
 * reconstructing layout: the analyser looks for section headings at line starts
 * and for contact details near the top, both of which survive this. Trying to
 * rebuild columns would risk inventing structure the document does not have.
 */
export async function extractPdfText(file: File): Promise<ExtractionResult> {
  if (file.size > MAX_FILE_BYTES) {
    throw new ExtractionError("That file is larger than 10MB. Export a smaller PDF and try again.");
  }

  const pdfjs = await import("pdfjs-dist");
  pdfjs.GlobalWorkerOptions.workerSrc = WORKER_URL;

  let document;
  try {
    document = await pdfjs.getDocument({ data: await file.arrayBuffer() }).promise;
  } catch {
    throw new ExtractionError(
      "That file couldn't be opened as a PDF. If it's a Word document, export it as PDF first.",
    );
  }

  const pageCount = Math.min(document.numPages, MAX_PAGES);
  const pages: string[] = [];

  for (let pageNumber = 1; pageNumber <= pageCount; pageNumber += 1) {
    const page = await document.getPage(pageNumber);
    const content = await page.getTextContent();
    const line = content.items
      .map((item) => ("str" in item ? item.str : ""))
      .join(" ")
      .replace(/[ \t]+/g, " ")
      .trim();
    pages.push(line);
  }

  const text = pages.join("\n\n").trim();

  return {
    text,
    pageCount: document.numPages,
    // A text-based resume yields hundreds of words per page. A scan yields
    // almost none, and the candidate needs to be told that rather than handed a
    // score of nothing.
    looksScanned: text.split(/\s+/).filter(Boolean).length < 40 * pageCount,
  };
}

/** Plain-text resumes need no parser, and some candidates keep one. */
export async function extractPlainText(file: File): Promise<ExtractionResult> {
  if (file.size > MAX_FILE_BYTES) {
    throw new ExtractionError("That file is larger than 10MB.");
  }
  const text = (await file.text()).trim();
  return { text, pageCount: 1, looksScanned: text.length === 0 };
}

export async function extractResumeText(file: File): Promise<ExtractionResult> {
  const name = file.name.toLowerCase();
  if (name.endsWith(".pdf") || file.type === "application/pdf") return extractPdfText(file);
  if (name.endsWith(".txt") || name.endsWith(".md") || file.type.startsWith("text/")) {
    return extractPlainText(file);
  }
  throw new ExtractionError(
    // Said explicitly rather than failing silently on a .docx, which is the
    // format candidates most often reach for.
    "Only PDF and plain text are supported. Export a Word document as PDF — that's also what an ATS reads best.",
  );
}
