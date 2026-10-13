# Kolbo GPU donor — media proof gate v2 (2026-10-13)

This patch hardens the donor admission *review* gate; it does not allocate a GPU,
enable production, register a worker, or prove a video was made by an AI model.

## Local proof format

Run a donor's own authorized model on a **synthetic prompt, without user photos**.
Save the resulting output as `synthetic-proof.mp4` in a dedicated local folder.
The sample must be a 1–16 second MP4 with genuine decoded motion and an audible-level
audio track. Example receipt next to the video:

```json
{"schema_version": 2, "media_file": "synthetic-proof.mp4", "sha256": "<64-hex-file-digest>"}
```

Generate the SHA-256 with a standard offline hashing utility. Avoid public
upload of the sample unless the operator independently authorizes it.

To inspect a local receipt:

```sh
python3 -c 'import sys; sys.path.insert(0,"gpu-donor"); from pathlib import Path; from proof_validation import inspect_local_receipt; print(inspect_local_receipt(Path("/path/to/proof/receipt.json")))'
```

`inspect_donor()` now refuses `eligible_for_independent_review` when the
receipt contains only claimed flags. It independently checks the media hash,
decodes multiple actual video frames and PCM audio, checks frame differences
and rejects silent audio. It never marks the donor `owner_approved`, never
registers a worker, and never transfers private media.

### Known limitations

- Decode-level motion/audio do **not** establish AI generation, GPU provenance,
  semantic accuracy, subject identity, lip-sync, artistic quality or rights.
- GPU operation and model provenance still require separate operator-supervised
  inference evidence and a trusted, authenticated worker.
- Audio RMS is an objective signal check, not a perceptual quality guarantee.
- Run FFmpeg on untrusted files in an unprivileged sandbox, with no network.
- No paid compute or provider fallback may be silently enabled.
- No daily *application* quota is introduced; physical capacity remains finite.

## Test

```sh
python3 -m unittest discover -s gpu-donor/tests -v
```

Tests use locally generated synthetic FFmpeg media (no GPU, no API account,
no images of real people). They cover moving video, static video, missing and
silent audio, digest tampering, and disallowed paths.
