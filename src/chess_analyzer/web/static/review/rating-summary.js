/** Keep asynchronous ratings attached to the game that requested them. */
export class RatingSummary {
  version = 0;

  constructor() {
    this.timer = undefined;
    this.controller = undefined;
    this.pgn = undefined;
    this.status = document.getElementById('rating-status');
    this.retry = document.getElementById('retry-rating');
    this.retry.addEventListener('click', () => this.start(this.pgn));
  }

  start(pgn) {
    this.version++;
    clearTimeout(this.timer);
    this.controller?.abort();
    this.controller = new AbortController();
    this.pgn = pgn;
    this.deadline = Date.now() + 60 * 60 * 1000;
    this.retry.hidden = true;
    for (const color of ['white', 'black']) {
      const rating = document.getElementById(`${color}-rating`);
      rating.textContent = '\u2014';
      rating.removeAttribute('title');
    }
    this.status.textContent = 'Requesting performance rating...';
    void this.request(document.body.dataset.ratingUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
      },
      body: JSON.stringify({ pgn }),
    }, this.version);
  }

  async request(url, options, version) {
    const signal = this.controller.signal;
    try {
      const response = await fetch(url, { ...options, credentials: 'same-origin', signal });
      const data = await this.readResponse(response, version);
      if (version !== this.version || data === undefined) return;
      if (!data || typeof data !== 'object' || Array.isArray(data)) {
        this.unavailable(`Rating server returned an invalid response (HTTP ${response.status}).`, true);
        return;
      }
      if (!response.ok) {
        this.unavailable(data.error || 'Performance rating unavailable.', response.status === 429 || response.status >= 500);
        return;
      }
      if (data.status === 'complete') {
        this.complete(data.result);
        return;
      }
      if (data.status === 'failed') {
        this.unavailable(data.error || 'Performance rating failed.', true);
        return;
      }
      if (!['queued', 'running'].includes(data.status) || typeof data.id !== 'string') {
        this.unavailable('The rating service returned an invalid job response.', true);
        return;
      }
      if (Date.now() >= this.deadline) {
        this.unavailable('Performance rating timed out. Please try again.', true);
        return;
      }
      this.status.textContent = data.status === 'queued' ? 'Performance rating queued.' : 'Calculating performance rating...';
      this.timer = setTimeout(() => this.request(
        `${document.body.dataset.ratingUrl}${encodeURIComponent(data.id)}/`, {}, version,
      ), 2000);
    } catch {
      if (signal.aborted || version !== this.version) return;
      this.unavailable('Unable to connect to the rating service. Check your connection and try again.', true);
    }
  }

  async readResponse(response, version) {
    try {
      return await response.json();
    } catch (error) {
      if (!(error instanceof SyntaxError)) throw error;
      if (version !== this.version) return undefined;
      let detail = 'Check the application logs and rating service configuration.';
      if (response.status === 403) {
        detail = 'Reload the page and try again. If this continues, check the server CSRF and proxy settings.';
      }
      if (response.status === 404) {
        detail = 'The rating endpoint was not found. Check the deployed application version and routing.';
      }
      this.unavailable(`Rating server returned an unreadable response (HTTP ${response.status}). ${detail}`,
        response.status === 429 || response.status >= 500);
      return undefined;
    }
  }

  complete(result) {
    if (!result || !['white', 'black'].every((color) => Number.isFinite(result[color]))) {
      this.unavailable('The rating service returned an invalid estimate.', true);
      return;
    }
    for (const color of ['white', 'black']) {
      const rating = document.getElementById(`${color}-rating`);
      rating.textContent = String(Math.round(result[color]));
      rating.title = `Model: ${result.model_version || result.model_id}`;
    }
    this.status.textContent = 'Experimental single-game estimate on the Chess.com rating scale.';
  }

  unavailable(message, retryable) {
    this.status.textContent = message;
    this.retry.hidden = !retryable;
  }
}