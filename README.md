# ChessAnalyzer

Turn your finished games into something you can learn from. ChessAnalyzer lets
you review your Chess.com games with Stockfish, compare your decisions with the
engine's suggestions, and play out the alternatives on an interactive board.

Whether you missed a winning tactic, let an advantage slip, or want to understand
why a move worked, you can return to the position and investigate it yourself.

## Start With a Game

1. Select **Load game** and enter your Chess.com username.
2. Select **Find games**, then choose a game from your archives. You can browse
   different months and see each game's players, ratings, time control, and result.
3. Select **Analyze game** to open the review.

You can also select **Use example game** to try the review right away. Public
games are available by username, without signing in to Chess.com.

## Find the Turning Points

The evaluation graph shows how the balance changed throughout the game. A sharp
swing is a useful place to look for a missed opportunity or a costly decision.
Click the graph to jump straight to that moment.

Positive evaluations favor White; negative evaluations favor Black, whichever
side of the board you are viewing. For example, **+1.5** means Stockfish judges
White's position to be better by roughly a pawn and a half. It is an assessment
of the position, not a guarantee of the result.

The move list and navigation controls let you replay the whole game, including
the final position and recorded result. Your games open from your side of the
board, and **Flip** lets you see the other player's perspective.

## Compare Your Move With Another Choice

Select any move to see what you played alongside Stockfish's recommendation.
Board arrows highlight both choices, and the move insights show the evaluation
and estimated loss in position value.

- **Before move** shows the position where the decision was made.
- **Played line** shows the position after the move from the game.
- **Best line** shows the position after the engine's suggested alternative.

This makes it easier to ask a specific question: did you overlook a threat,
miss a stronger continuation, or choose a move that was already close to best?

## Try Your Own Ideas

Click or drag pieces to explore legal continuations for either side. Stockfish
evaluates the position you reach and suggests a next move, so you can test an
idea rather than simply accept the first recommendation.

Use **Undo** to take back a trial move or **Reset** to return to the reviewed
position. Exploring a variation leaves your original game, accuracy scores, and
evaluation graph unchanged.

## Understand Your Game Summary

### Accuracy

Each player receives an accuracy percentage based on how their moves affected
the position's winning chances. The calculation uses the Lichess accuracy method
with this app's Stockfish evaluations.

Use it as a summary of that game's decisions, then look at the individual moves
for context. Accuracy depends on the positions you faced, and scores can differ
from other chess sites because their engine analysis may differ.

### Estimated Performance Rating

When performance ratings are enabled, eligible completed bullet, blitz, and
rapid games with recorded clock information can receive an estimated rating
for each player. The estimate considers move quality, decision difficulty,
time use, and game context. It calculates separately while you continue reviewing.

This is an experimental, single-game estimate on the Chess.com rating scale,
not an official rating or a measure of your long-term strength. In testing,
the model's average absolute error was about **385 rating points**, so treat
the number as a rough perspective on one performance, not a precise verdict.

## Review Standard Chess and Chess960

Both standard chess and Chess960 games are supported for game review. The board
handles legal moves, castling, en passant, and promotions. In Chess960, castle
by moving your king onto the rook involved in castling.

The interface works on desktop and mobile, so you can review at your desk or
revisit a game on your phone.

## Make Each Review Useful

Start with one or two important moments instead of trying to memorize every
engine suggestion. Before opening the best line, ask what you would play now
and what your opponent is threatening. Then test your answer on the board.

Look for recurring habits across your reviews: overlooking forcing moves,
relaxing in winning positions, or rushing critical decisions. The goal is to
leave each game with something concrete to notice next time.

## Credits

ChessAnalyzer uses Stockfish for engine analysis, Chessground for the interactive
board, Chessops for legal moves, and
[ELO-Estimator](https://github.com/MCodrescu/ELO-Estimator) for performance estimates.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for acknowledgments and licenses.