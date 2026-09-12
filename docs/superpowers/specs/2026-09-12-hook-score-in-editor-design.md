# Hook Score in Editor — Design

## Context
User wants hook viral score + reasons visible inside editor without mandatory clip selection. Flow A: analyze -> editor directly, all hook windows visible.

## Decisions
- Drop mandatory /pick step; Dashboard navigate -> /editor/:id directly.
- Editor loads hooks from GET /projects/:id (already returns hooks[] with score, reasons_json, weaknesses_json).
- No backend deletion of clips; clip creation deferred to export if needed.

## UI
- **Sidebar new tab "hook"**: sorted desc by score. Per row: score badge (green >=80, amber >=50), start->end, duration, reasons chips, weakness italic. Click row -> seek video to hook.start.
- **Timeline**: small score label above each block (reuse hook score).
- **Remove** selected-video mandatory gate; keep main preview/crop/export intact.
- Keep ClipPicker.tsx file but unused (no route removal needed for now; just bypass).

## Non-goals
- Deleting clips table.
- Changing scoring algorithm.

## Verification
- Analyze YouTube -> lands in editor.
- Hooks visible with scores/reasons.
- Click hook seeks correctly.
- Existing crop/caption/export still works.

## Risks
- Polling status: editor must handle "processing" hooks empty -> show placeholder.
