export const MAX_IMAGE_EDGE = 1800;
export const MAX_PDF_BYTES = 4 * 1024 * 1024;

export function validateUpload(file) {
  const accepted = ["application/pdf", "image/jpeg", "image/png", "image/webp", "image/gif"];
  if (!accepted.includes(file.type)) return "Choose a PDF, JPEG, PNG, WebP, or GIF file.";
  if (file.type === "application/pdf" && file.size > MAX_PDF_BYTES) {
    return "This PDF may be too large. Try a smaller file or a few pages at a time.";
  }
  return null;
}

/** Resize images locally before upload. PDFs pass through unchanged. */
export async function prepareUpload(file) {
  if (!file.type.startsWith("image/")) return file;
  const source = URL.createObjectURL(file);
  try {
    const image = await loadImage(source);
    const scale = Math.min(1, MAX_IMAGE_EDGE / Math.max(image.width, image.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(image.width * scale);
    canvas.height = Math.round(image.height * scale);
    canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve, reject) =>
      canvas.toBlob((value) => value ? resolve(value) : reject(new Error("Could not resize image.")), "image/jpeg", 0.82)
    );
    return new File([blob], file.name.replace(/\.[^.]+$/, ".jpg"), { type: "image/jpeg" });
  } finally {
    URL.revokeObjectURL(source);
  }
}

function loadImage(source) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Could not read that image."));
    image.src = source;
  });
}
