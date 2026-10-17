# Subtitle position patch (v2.10 -> v2.10.1)

Only change: default `subtitle_anchor_pct` from `75.5` to `85.0` (85% from top), baseline Y=1632 on 1080x1920.

Updated renderer validation upper bound to accept 85%; kept font (3.2% frame width, ~35px), 3 words/cue, ASMR mix, all other logic unchanged.

Apply `render_preferences.json` at the batch root, or deploy the updated renderer. Existing batch/project configurations that explicitly override the position will still take precedence.
