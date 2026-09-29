import test, { mock } from "node:test";
import assert from "node:assert/strict";
import { pollWhileVisible } from "./visiblePoll.js";

function fakeDoc() {
  const listeners = new Set();
  return {
    hidden: false,
    addEventListener: (t, f) => listeners.add(f),
    removeEventListener: (t, f) => listeners.delete(f),
    fire() { for (const f of listeners) f(); },
    listeners,
  };
}

test("polls while visible, skips while hidden, catches up once on return", () => {
  mock.timers.enable({ apis: ["setInterval"] });
  try {
    const doc = fakeDoc();
    let n = 0;
    const stop = pollWhileVisible(() => n++, 1000, doc);
    mock.timers.tick(2000);
    assert.equal(n, 2);
    doc.hidden = true; doc.fire();
    mock.timers.tick(5000);
    assert.equal(n, 2);
    doc.hidden = false; doc.fire();
    assert.equal(n, 3);                 // one catch-up, not five
    doc.fire();
    assert.equal(n, 3);
    stop();
    mock.timers.tick(5000);
    assert.equal(n, 3);
    assert.equal(doc.listeners.size, 0);
  } finally {
    mock.timers.reset();
  }
});

test("showing the tab again without a missed tick does not poll early", () => {
  mock.timers.enable({ apis: ["setInterval"] });
  try {
    const doc = fakeDoc();
    let n = 0;
    const stop = pollWhileVisible(() => n++, 1000, doc);
    doc.hidden = true; doc.fire();
    doc.hidden = false; doc.fire();
    assert.equal(n, 0);
    stop();
  } finally {
    mock.timers.reset();
  }
});
