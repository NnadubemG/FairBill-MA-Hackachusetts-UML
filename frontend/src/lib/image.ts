import type { ExtractRequest } from '@contracts';

export const MAX_LONG_EDGE = 1800;
// Base64 adds roughly 33%; keep the raw PDF below the server's 6 MB JSON cap.
export const PDF_WARN_BYTES = 4 * 1024 * 1024;

type DocumentMediaType = NonNullable<ExtractRequest['document_media_type']>;

export interface PreparedDocument {
  document_base64: string;
  document_media_type: DocumentMediaType;
}

/** Prepare an accepted image/PDF for the shared ExtractRequest contract. */
export async function prepareDocument(file: File): Promise<PreparedDocument> {
  if (file.type === 'application/pdf') {
    return splitDataUrl(await readAsDataUrl(file), 'application/pdf');
  }
  if (!file.type.startsWith('image/')) {
    throw new Error('Choose a PDF or image file.');
  }

  const resized = await resizeImage(file);
  return splitDataUrl(resized, 'image/jpeg');
}

/** Resize an image to a max long edge and return a JPEG data URL. */
export async function resizeImage(file: File): Promise<string> {
  const dataUrl = await readAsDataUrl(file);
  const img = await loadImage(dataUrl);
  const longEdge = Math.max(img.width, img.height);
  const scale = longEdge > MAX_LONG_EDGE ? MAX_LONG_EDGE / longEdge : 1;

  const canvas = document.createElement('canvas');
  canvas.width = Math.round(img.width * scale);
  canvas.height = Math.round(img.height * scale);
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Could not prepare that image.');
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.82);
}

export function pdfSizeWarning(file: File): string | null {
  if (file.type === 'application/pdf' && file.size > PDF_WARN_BYTES) {
    const mb = (file.size / (1024 * 1024)).toFixed(1);
    return `This PDF is about ${mb} MB, which may be too large to process. Try a smaller file or a few pages at a time.`;
  }
  return null;
}

function splitDataUrl(dataUrl: string, mediaType: DocumentMediaType): PreparedDocument {
  const comma = dataUrl.indexOf(',');
  if (comma < 0) throw new Error('Could not prepare that file.');
  return {
    document_base64: dataUrl.slice(comma + 1),
    document_media_type: mediaType,
  };
}

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('Could not read that image.'));
    img.src = src;
  });
}
