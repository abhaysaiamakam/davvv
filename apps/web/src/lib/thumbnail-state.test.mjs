import assert from "node:assert/strict";
import test from "node:test";
import { initialThumbnailState, shouldShowThumbnailFallback, thumbnailStateAfterEvent } from "./thumbnail-state.mjs";

test("successful thumbnail loads hide the fallback", () => {
  assert.equal(initialThumbnailState(true), "loading");
  const state = thumbnailStateAfterEvent("load");
  assert.equal(state, "loaded");
  assert.equal(shouldShowThumbnailFallback(state), false);
});

test("failed thumbnail loads show the fallback", () => {
  const state = thumbnailStateAfterEvent("error");
  assert.equal(state, "failed");
  assert.equal(shouldShowThumbnailFallback(state), true);
});
