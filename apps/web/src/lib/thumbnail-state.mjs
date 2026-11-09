export function initialThumbnailState(hasSource) {
  return hasSource ? "loading" : "failed";
}

export function thumbnailStateAfterEvent(event) {
  return event === "load" ? "loaded" : "failed";
}

export function shouldShowThumbnailFallback(state) {
  return state === "failed";
}
