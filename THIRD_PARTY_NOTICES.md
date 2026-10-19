# Third-party frontend components

The game-review UI uses [Lichess Chessground](https://github.com/lichess-org/chessground)
10.4.2, copyright its contributors, under **GPL-3.0-or-later**. The frontend build
copies its unmodified assets and full license into the local static bundle.
The Cburnett chess-piece artwork distributed with Chessground is by Colin M. L.
Burnett; preserve its embedded attribution/license notices with the assets.

Chessground's upstream documentation states that a website's combined work must
be distributed under the GPL and its source released to website users. Before
distribution/deployment, ensure the combined work's licensing is compatible and
provide the required notices, license, and corresponding source (including build
instructions). This notice does not relicense other repository code or replace
those obligations. See the upstream README and bundled license for full terms.

Stockfish is installed separately; its redistribution obligations also apply if
you distribute an image containing the engine. No Lichess server code, branding,
or remote analysis services are used by this interface.

Legal interactive moves use [Chessops](https://github.com/niklasf/chessops) 0.15.1,
copyright its contributors, under **GPL-3.0-or-later**. The frontend build
bundles it locally and copies its full license into the static vendor assets.