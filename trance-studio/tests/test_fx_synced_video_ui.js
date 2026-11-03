'use strict';
// Regression: source-video FX metadata must be visible in the result panel.
// Source-derived clips and AI-generated clips are intentionally distinguished.
const fs=require('node:fs');
const assert=require('node:assert/strict');
const html=fs.readFileSync('trance-studio/web/studio.html','utf8');
const start=html.indexOf("$('storyboardInfo').textContent=j.video_mode");
const end=html.indexOf("$('videoPlayer').setAttribute",start);
assert.ok(start>0&&end>start,'Video UI result block is missing');
const block=html.slice(start,end);
assert.match(block,/video_edit_style==='voice_fx_synced_motion_warp'/,
             'Voice-FX synced MP4 must be identified');
assert.match(block,/video_edit_fx_cues/,
             'Voice-FX count must be shown to the user');
assert.ok(!block.includes("video_edit_style==='beat_cut_punch_in_speed_ramp'?\n    (j.video_edit_style==='voice_fx_synced_motion_warp'?"),
  'An FX mode can never be selected inside the mutually exclusive beat-cut branch');
assert.ok(block.indexOf("video_edit_style==='voice_fx_synced_motion_warp'")<
          block.indexOf("video_edit_style==='beat_cut_punch_in_speed_ramp'"),
          'Show synced effects before fallback beat-cut mode');
assert.match(html,/files\.some\(isVideoFile\)/,
             'Video inputs must select source-video editing automatically');
assert.match(html,/videoModeChosenByUser=true/,
             'An explicit video mode choice must be respected');
assert.match(html,/var hasSourceVideo=files\.some\(isVideoFile\)/,
             'After AI fails, offer source-video treatment for a shared video');
console.log('Kolbo synced original-video UI checks passed');
