/** Keep asynchronous ratings attached to the game that requested them. */
export class RatingSummary {
  version = 0;

  constructor() {
    this.controller = undefined;
    this.status = document.getElementById('rating-status');
    this.retry = document.getElementById('retry-rating');
  }

  async loadReview(url, pgn, onProgress = () => {}) {
    this.version++;
    this.controller?.abort();
    this.controller = new AbortController();
    const version = this.version;
    const deadline = Date.now() + 60 * 60 * 1000;
    let data = await this.request(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
      },
      body: JSON.stringify({ pgn }),
    }, version);
    while (['queued', 'running'].includes(data.status)) {
      if (Date.now() >= deadline) throw new Error('Game analysis timed out. Please try again.');
      if (typeof data.id !== 'string') throw new Error('The server returned an invalid analysis job.');
      onProgress(data.status === 'queued'
        ? 'Game analysis queued. Review and performance rating will use the same Stockfish analysis.'
        : 'Stockfish is reviewing the game for accuracy and performance rating. This can take several minutes.');
      await new Promise((resolve) => setTimeout(resolve, 2000));
      data = await this.request(`${document.body.dataset.ratingUrl}${encodeURIComponent(data.id)}/`, {}, version);
    }
    if (data.status === 'failed') throw new Error(data.error || 'Game analysis failed.');
    if (data.status === 'complete') {
      if (!data.review) throw new Error('The server returned no game review. Please analyze the game again.');
      return { ...data.review, rating: data.result, rating_error: data.error };
    }
    if (!Array.isArray(data.moves)) throw new Error('The server returned an invalid game review.');
    return data;
  }

  render(review) {
    this.retry.hidden = true;
    for (const color of ['white', 'black']) {
      const rating = document.getElementById(`${color}-rating`);
      rating.textContent = '\u2014';
      rating.removeAttribute('title');
    }
    if (review.rating) this.complete(review.rating);
    else this.status.textContent = review.rating_error || 'Performance ratings are not configured.';
  }

  async request(url, options, version) {
    if (version !== this.version) throw new DOMException('Analysis superseded.', 'AbortError');
    const signal = this.controller.signal;
    const response = await fetch(url, { ...options, credentials: 'same-origin', signal });
    const data = await this.readResponse(response);
    if (version !== this.version) throw new DOMException('Analysis superseded.', 'AbortError');
    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      throw new Error(`Analysis server returned an invalid response (HTTP ${response.status}).`);
    }
    if (!response.ok) throw new Error(data.error || `Game analysis failed (HTTP ${response.status}).`);
    return data;
  }

  async readResponse(response) {
    try {
      return await response.json();
    } catch (error) {
      if (!(error instanceof SyntaxError)) throw error;
      let detail = 'Check the application logs and rating service configuration.';
      if (response.status === 403) {
        detail = 'Reload the page and try again. If this continues, check the server CSRF and proxy settings.';
      }
      if (response.status === 404) {
        detail = 'The rating endpoint was not found. Check the deployed application version and routing.';
      }
      throw new Error(`Analysis server returned an unreadable response (HTTP ${response.status}). ${detail}`);
    }
  }

  complete(result) {
    if (!result || !['white', 'black'].every((color) => Number.isFinite(result[color]))) {
      this.status.textContent = 'The rating service returned an invalid estimate.';
      return;
    }
    for (const color of ['white', 'black']) {
      const rating = document.getElementById(`${color}-rating`);
      rating.textContent = String(Math.round(result[color]));
      rating.title = `Model: ${result.model_version || result.model_id}`;
    }
    this.status.textContent = 'Experimental single-game estimate on the Chess.com rating scale.';
  }

}