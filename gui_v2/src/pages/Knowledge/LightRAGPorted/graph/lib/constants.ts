/**
 * Colours used by the sigma/graphology knowledge-graph canvas.
 *
 * IMPORTANT: these values are painted onto a <canvas> by sigma, which cannot
 * resolve CSS custom properties. `var(--primary-color)` here is an invalid
 * colour for the canvas and silently paints BLACK — do not "tokenise" these.
 * (That is exactly the regression a3e87423a introduced: every node turned
 * black except the three that still happened to be literal hex.)
 *
 * DOM-rendered graph chrome (Legend, toolbars, dialogs) may and does use
 * var(--…) freely — those go through the CSS engine.
 */
export const labelColorDarkTheme = '#e2e2e2';
export const labelColorLightTheme = '#222222';
export const nodeBorderColor = '#333333';
export const nodeBorderColorSelected = '#1e90ff';
/* A node that is not the clicked node nor one of its neighbours is FADED, not
   repainted. It keeps most of its own hue and simply loses contrast against the
   canvas, so the graph stays readable as a map of colours while the focused
   neighbourhood still stands out. A single flat grey used to be applied to
   every unfocused node on both themes, which collapsed the whole canvas to one
   colour the moment anything was clicked.

   The fade target is the CANVAS colour (`--bg-secondary`: #1e293b dark, #fff
   light), not a neutral grey. Blending toward a desaturated grey is what made
   the first attempt at this fail: at a low retained amount every hue converged
   onto the same muddy grey, so the canvas still looked like one colour. Blending
   toward the canvas instead reads as "recedes into the background", which is
   what an unfocused node should look like, and it needs no per-theme grey stop.
   White is a safe literal for the light canvas: `--bg-secondary` is `#fff`
   there (global.css:13). */
export const canvasColorDarkTheme =
  '#1e293b'; /* literal: canvas values must never be var(), sigma cannot resolve them */
export const canvasColorLightTheme = '#ffffff';
/* How much of the ORIGINAL colour survives the fade. Measured over the 12-entry
   nodeColors palette: at 0.35 the closest two faded hues differ by only ~11/765
   of channel distance, i.e. indistinguishable. 0.7 keeps that distance at ~24
   on both themes (vs 35 for full colour), so hues remain tellable apart, while
   the brightest faded node still sits ~5.9:1 (dark) / ~3.7:1 (light) against the
   canvas, leaving the highlighted neighbourhood clearly brighter. Lower this
   only with the palette check in hand. */
export const nodeFadeRetainedAmount = 0.7;
/* Blend a node's own colour toward the canvas. Used to fade the nodes outside
   the clicked node's neighbourhood: keeping most of the original hue is what
   stops a click from collapsing the canvas into a single flat colour.
   Sigma paints to a canvas, so this must return a literal `rgb()`, never a
   `var(--…)`. Unknown/invalid colours are returned untouched rather than
   guessed at.
   The parser tolerates the forms actually reachable here (`#abc`, `#rrggbb`)
   plus `rgb()`. Without the 3-digit branch and the whitespace tolerance a node
   whose colour did not parse would be returned UNCHANGED, i.e. left at full
   saturation while its neighbours faded — reading as MORE highlighted than the
   real selection, the inverse of the intent. */
/* Module scope, not inside `fadeNodeColor`: this runs once per node inside
   sigma's nodeReducer, i.e. on every layout tick. */
const HEX_COLOR_RE = /^\s*#([0-9a-f]{3}|[0-9a-f]{6})\s*$/i;
/* Anchored and alpha-excluding on purpose: a form whose opacity this helper
   cannot represent is REJECTED (returns the colour untouched, per the contract
   above) rather than silently painted opaque. `rgba(..., 0.5)` used to match
   and lose its alpha, which would have rendered a translucent node solid. */
const RGB_COLOR_RE = /^\s*rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*$/i;

const parseRgb = (value: string): [number, number, number] | null => {
  const hex = HEX_COLOR_RE.exec(value);
  if (hex) {
    const digits = hex[1];
    /* #abc is shorthand for #aabbcc. */
    const full = digits.length === 3
      ? digits.split('').map((d) => d + d).join('')
      : digits;
    const n = parseInt(full, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const rgb = RGB_COLOR_RE.exec(value);
  if (rgb) {
    return [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])];
  }
  return null;
};

export const fadeNodeColor = (
  color: string,
  isDarkTheme: boolean,
  amount = nodeFadeRetainedAmount
): string => {
  const from = parseRgb(color);
  const to = parseRgb(
    isDarkTheme ? canvasColorDarkTheme : canvasColorLightTheme
  );
  if (!from || !to) return color;

  const mix = from.map((channel, i) =>
    Math.round(channel * amount + to[i] * (1 - amount))
  );
  return `rgb(${mix[0]}, ${mix[1]}, ${mix[2]})`;
};
export const edgeColorDarkTheme = '#999999';
/* Light theme previously passed `undefined` for the edge colour, which made
   sigma fall back to its near-white default and left edges invisible on the
   white canvas. Pin an explicit mid-grey instead. */
export const edgeColorLightTheme = '#9aa4b2';
export const edgeColorHighlightedDarkTheme = '#66ccff';
export const edgeColorHighlightedLightTheme = '#0077cc';
export const minNodeSize = 4;
export const maxNodeSize = 18;
export const controlButtonVariant: 'ghost' | 'default' = 'ghost';

/* Sigma paints the hovered/selected node's label bubble itself, with a
   hard-coded `#FFF` fill and `#000` shadow (sigma/dist/index-*.esm.js
   `drawDiscNodeHover`). On the dark canvas that is a white box with white
   text. GraphControl overrides that draw with these palette values. */
/* #64748b is the darkest slate that still clears 3:1 (AA for large text)
   against the dark canvas #1e293b, so the bubble reads as a raised chip while
   keeping the #f8fafc label at 4.55:1. Do not lighten without re-checking. */
export const hoverBubbleFillDarkTheme = '#64748b';
export const hoverBubbleFillLightTheme = '#ffffff';
export const hoverBubbleLabelDarkTheme = '#f8fafc';
export const hoverBubbleLabelLightTheme = '#1f2937';
export const hoverBubbleShadowDarkTheme = 'rgba(0,0,0,0.75)';
export const hoverBubbleShadowLightTheme = 'rgba(15,23,42,0.35)';
/* Must mirror sigma's own label defaults (settings.js: labelFont "Arial",
   labelSize 14, labelWeight "normal"). The bubble is measured with the same
   font the node's own label is drawn in, so the box must not drift from the
   text it encloses. */
export const hoverBubbleLabelSize = 14;
export const hoverBubbleLabelFont = 'Arial';
export const hoverBubbleLabelWeight = 'normal';

/* Sigma's built-in hover painter (`drawDiscNodeHover`) hard-codes fill `#FFF`
   and shadow `#000`, which paints a white box under the near-white dark-theme
   label. This is a faithful re-implementation of that geometry with the
   palette above. Declared here (not inside GraphControl) so `GraphViewer` can
   hand it to SigmaContainer as a constructor setting: sigma stores
   `defaultDrawNodeHover` at construction, and a later `setSettings` is lost
   whenever react-sigma rebuilds the Sigma instance. */
export const makeDrawNodeHover =
  (isDarkTheme: boolean) =>
  (context: CanvasRenderingContext2D, data: any): void => {
    const label = data.label;
    const size = hoverBubbleLabelSize;
    const PADDING = 2;
    const radius = Math.max(data.size, size / 2) + PADDING;

    context.save();
    context.fillStyle = isDarkTheme
      ? hoverBubbleFillDarkTheme
      : hoverBubbleFillLightTheme;
    context.shadowOffsetX = 0;
    context.shadowOffsetY = 0;
    context.shadowBlur = 8;
    context.shadowColor = isDarkTheme
      ? hoverBubbleShadowDarkTheme
      : hoverBubbleShadowLightTheme;

    if (typeof label === 'string') {
      const textWidth = context.measureText(label).width;
      const boxWidth = Math.round(textWidth + 5);
      const boxHeight = Math.round(size + 2 * PADDING);
      const angleRadian = Math.asin(boxHeight / 2 / radius);
      const xDeltaCoord = Math.sqrt(
        Math.abs(Math.pow(radius, 2) - Math.pow(boxHeight / 2, 2))
      );

      context.beginPath();
      context.moveTo(data.x + xDeltaCoord, data.y + boxHeight / 2);
      context.lineTo(data.x + radius + boxWidth, data.y + boxHeight / 2);
      context.lineTo(data.x + radius + boxWidth, data.y - boxHeight / 2);
      context.lineTo(data.x + xDeltaCoord, data.y - boxHeight / 2);
      context.arc(data.x, data.y, radius, angleRadian, -angleRadian);
      context.closePath();
      context.fill();
    } else {
      /* Matches sigma: a label-less node still gets a plain disc shadow, so
         highlighted label-less neighbours keep their hover feedback. */
      context.beginPath();
      context.arc(data.x, data.y, data.size + PADDING, 0, Math.PI * 2);
      context.closePath();
      context.fill();
    }

    context.shadowOffsetX = 0;
    context.shadowOffsetY = 0;
    context.shadowBlur = 0;

    if (typeof label === 'string' && label) {
      context.fillStyle = isDarkTheme
        ? hoverBubbleLabelDarkTheme
        : hoverBubbleLabelLightTheme;
      context.font =
        hoverBubbleLabelWeight +
        ' ' +
        String(size) +
        'px ' +
        hoverBubbleLabelFont;
      context.fillText(label, data.x + data.size + 3, data.y + size / 3);
    }

    context.restore();
  };

/** Highlighted-label colour for the dark canvas (was #ffffff before a3e87423a). */
export const labelColorHighlightedDarkTheme = '#ffffff';

export const nodeColors = [
  '#1677ff', // blue-primary
  '#52c41a', // green-success
  '#faad14', // yellow-warning
  '#f5222d', // red-error
  '#722ed1', // purple
  '#13c2c2', // cyan
  '#eb2f96', // magenta
  '#fa8c16', // orange
  '#2f54eb', // geekblue
  '#a0d911', // lime
  '#fadb14', // gold
  '#fa541c'  // volcano
];
