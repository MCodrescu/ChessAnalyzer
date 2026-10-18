import { formatEvaluation } from './review-state.js';
import { evaluationSeries, gameAccuracy } from './summary-state.js';

const $ = (id) => document.getElementById(id);
const left = 30;
const right = 590;
const middle = 65;

/** Render game-wide estimates and keep the actual-game graph in sync with review. */
export class ReviewSummary {
  constructor(onSelect) {
    this.points = [];
    const choose = (index) => onSelect(index === 0 ? 0 : index - 1, index === 0 ? 'before' : 'played');
    $('graph-position').addEventListener('input', (event) => choose(Number(event.target.value)));
    $('evaluation-graph').addEventListener('click', (event) => {
      if (!this.points.length) return;
      const bounds = event.currentTarget.getBoundingClientRect();
      const x = (event.clientX - bounds.left) / bounds.width * 600;
      const fraction = Math.max(0, Math.min(1, (x - left) / (right - left)));
      choose(Math.round(fraction * (this.points.length - 1)));
    });
  }

  render(analysis) {
    const accuracy = gameAccuracy(analysis.moves);
    for (const color of ['white', 'black']) {
      const { accuracy: score, count } = accuracy[color];
      $(`${color}-accuracy`).textContent = score === null ? '—' : `${score.toFixed(1)}%`;
      $(`${color}-accuracy`).title = `${count} scored ${color} moves. Lichess accuracy algorithm with local Stockfish evaluations; requires scored moves for both colors.`;
      $(`${color}-accuracy-name`).textContent = analysis.headers[color === 'white' ? 'White' : 'Black'] || color;
    }
    this.points = evaluationSeries(analysis.moves);
    let path = '';
    let gap = true;
    this.points.forEach((point, index) => {
      if (point.score === null) { gap = true; return; }
      path += `${gap ? 'M' : 'L'}${this.x(index).toFixed(2)},${this.y(point).toFixed(2)} `;
      gap = false;
    });
    $('graph-line').setAttribute('d', path);
    $('graph-empty').hidden = this.points.length > 0;
    $('graph-position').disabled = !this.points.length;
    $('graph-position').max = String(Math.max(0, this.points.length - 1));
    $('evaluation-graph').setAttribute('aria-label', this.points.length
      ? `Game evaluation after ${analysis.moves.length} half-moves. White advantage above zero; Black below. Use the position slider to explore.`
      : 'Game evaluation graph. No analyzed moves.');
    this.select(0, 'before');
  }

  x(index) { return left + index / Math.max(1, this.points.length - 1) * (right - left); }
  y(point) { return middle - point.score / 10 * 49; }

  select(index, preview) {
    const position = index + (preview === 'played' ? 1 : 0);
    const point = this.points[position];
    $('graph-position').value = String(position);
    const label = point ? `${point.label} · ${point.score === null ? '—' : formatEvaluation(point.evaluation)}` : 'No analyzed moves';
    $('graph-position').setAttribute('aria-valuetext', label);
    $('graph-readout').textContent = label;
    $('graph-note').textContent = preview === 'best'
      ? 'Best-line preview is not plotted. Marker shows the position before this move.'
      : 'Actual game · ±10 pawns · Click graph or slider.';
    $('graph-cursor').style.display = point ? '' : 'none';
    $('graph-dot').style.display = point && point.score !== null ? '' : 'none';
    if (!point) return;
    const x = this.x(position);
    $('graph-cursor').setAttribute('x1', x);
    $('graph-cursor').setAttribute('x2', x);
    if (point.score !== null) {
      $('graph-dot').setAttribute('cx', x);
      $('graph-dot').setAttribute('cy', this.y(point));
    }
  }
}