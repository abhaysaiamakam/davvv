export type ThumbnailLoadState = "loading" | "loaded" | "failed";
export type ThumbnailLoadEvent = "load" | "error";
export function initialThumbnailState(hasSource: boolean): ThumbnailLoadState;
export function thumbnailStateAfterEvent(event: ThumbnailLoadEvent): ThumbnailLoadState;
export function shouldShowThumbnailFallback(state: ThumbnailLoadState): boolean;
