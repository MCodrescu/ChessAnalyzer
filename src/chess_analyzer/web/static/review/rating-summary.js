/** Keep asynchronous ratings attached to the game that requested them. */
export class RatingSummary {
  constructor() {
    this.version = 0;
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
    this.request(document.body.dataset.ratingUrl, {
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
      const data = await response.json();
      if (version !== this.version) return;
      if (!response.ok) {
        this.unavailable(data.error || 'Performance rating unavailable.', response.status === 429 || response.status >= 500);
        return;
      }
      if (data.status === 'complete') {
        if (!data.result || !['white', 'black'].every((color) => Number.isFinite(data.result[color]))) {
          throw new Error('Invalid rating response.');
        }
        for (const color of ['white', 'black']) {
          const rating = document.getElementById(`${color}-rating`);
          rating.textContent = String(Math.round(data.result[color]));
          rating.title = `Model: ${data.result.model_version || data.result.model_id}`;
        }
        this.status.textContent = 'Experimental single-game estimate on the Chess.com rating scale.';
        return;
      }
      if (data.status === 'failed') {
        this.unavailable(data.error || 'Performance rating failed.', true);
        return;
      }
      if (!['queued', 'running'].includes(data.status) || typeof data.id !== 'string') {
        throw new Error('Invalid job response.');
      }
      if (Date.now() >= this.deadline) {
        this.unavailable('Performance rating timed out. Please try again.', true);
        return;
      }
      this.status.textContent = data.status === 'queued' ? 'Performance rating queued.' : 'Calculating performance rating...';
      this.timer = setTimeout(() => this.request(
        `${document.body.dataset.ratingUrl}${encodeURIComponent(data.id)}/`, {}, version,
      ), 2000);
    } catch (error) {
      if (signal.aborted || version !== this.version) return;
      this.unavailable('Unable to retrieve the performance rating.', true);
    }
  }

  unavailable(message, retryable) {
    this.status.textContent = message;
    this.retry.hidden = !retryable;
  }
}