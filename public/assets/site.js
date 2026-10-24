// The docs page's only script: theme toggle, "Try it" requests, and highlighting the endpoint in view.
// Everything works without it except trying requests in place (the Open links still work).

const MAX_LINES = 400;

function setupThemeToggle() {
  const button = document.querySelector('[data-theme-toggle]');
  if (!button) return;
  const label = () =>
    button.setAttribute(
      'aria-label',
      document.documentElement.classList.contains('dark') ? 'Switch to light theme' : 'Switch to dark theme',
    );
  label();
  button.addEventListener('click', () => {
    const dark = document.documentElement.classList.toggle('dark');
    try {
      localStorage.setItem('theme', dark ? 'dark' : 'light');
    } catch {
      // Storage can be unavailable (private mode); the choice then lasts for this page view.
    }
    label();
  });
}

/** The URL a "Try it" block points at, with its path parameter filled in. */
function tryUrl(/** @type {HTMLElement} */ block) {
  const input = /** @type {HTMLInputElement | null} */ (block.querySelector('.try-input'));
  const path = (block.dataset.path ?? '').replace(/\{[^}]+\}/, encodeURIComponent(input?.value.trim() ?? ''));
  return new URL(path.replace(/^\//, ''), document.baseURI).href;
}

/** Pretty JSON, or the text as it is; long bodies are cut so the page stays responsive. */
function formatBody(/** @type {string} */ text, /** @type {string} */ contentType) {
  let body = text;
  if (contentType.includes('json') || /^[[{"]/.test(text)) {
    try {
      body = JSON.stringify(JSON.parse(text), null, 2);
    } catch {
      // Not JSON after all; show it as it is.
    }
  }
  // Find where line MAX_LINES ends without splitting a body that can be 100,000 lines long.
  let end = -1;
  for (let i = 0; i < MAX_LINES; i++) {
    end = body.indexOf('\n', end + 1);
    if (end === -1) return body;
  }
  return `${body.slice(0, end)}\n… Cut at ${MAX_LINES} lines. Use Open to see everything.`;
}

function setupTryIt() {
  for (const block of /** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll('.try'))) {
    const send = /** @type {HTMLButtonElement} */ (block.querySelector('.try-send'));
    const open = /** @type {HTMLAnchorElement} */ (block.querySelector('.try-open'));
    const result = /** @type {HTMLElement} */ (block.querySelector('.try-result'));
    const meta = /** @type {HTMLElement} */ (block.querySelector('.try-meta'));
    const code = /** @type {HTMLElement} */ (block.querySelector('code'));
    const input = block.querySelector('.try-input');

    const syncOpen = () => (open.href = tryUrl(block));
    syncOpen();
    input?.addEventListener('input', syncOpen);
    input?.addEventListener('keydown', (e) => {
      if (/** @type {KeyboardEvent} */ (e).key === 'Enter') send.click();
    });

    send.addEventListener('click', async () => {
      const url = tryUrl(block);
      send.disabled = true;
      result.hidden = false;
      meta.classList.remove('try-error');
      meta.textContent = `GET ${url}`;
      code.textContent = '';
      const started = performance.now();
      try {
        const res = await fetch(url);
        const text = await res.text();
        const ms = Math.round(performance.now() - started);
        const size = new Blob([text]).size;
        meta.textContent = `${res.status} ${res.statusText || (res.ok ? 'OK' : '')} · ${(size / 1024).toFixed(1)} kB · ${ms} ms`;
        if (!res.ok) meta.classList.add('try-error');
        code.textContent = res.ok ? formatBody(text, res.headers.get('content-type') ?? '') : '';
      } catch (e) {
        meta.classList.add('try-error');
        meta.textContent = `Request failed: ${e instanceof Error ? e.message : String(e)}`;
      } finally {
        send.disabled = false;
      }
    });
  }
}

/** Marks the sidebar link of the endpoint currently in view. */
function setupScrollSpy() {
  const links = new Map([...document.querySelectorAll('.ref-nav a')].map((a) => [a.getAttribute('href')?.slice(1), a]));
  if (!links.size || !('IntersectionObserver' in window)) return;
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        for (const a of links.values()) a.removeAttribute('aria-current');
        links.get(entry.target.id)?.setAttribute('aria-current', 'true');
      }
    },
    { rootMargin: '-20% 0px -70% 0px' },
  );
  for (const id of links.keys()) {
    const el = id && document.getElementById(id);
    if (el) observer.observe(el);
  }
}

setupThemeToggle();
setupTryIt();
setupScrollSpy();
