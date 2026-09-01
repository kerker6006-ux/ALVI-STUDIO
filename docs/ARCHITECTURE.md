# Architecture

## Trust and storage boundary

The executable resolves exactly one storage root, normally the selected installation directory recorded in `storage-root.json`. `StorageLayout` creates every managed directory, redirects third-party cache/temp environment variables, and rejects paths that do not resolve beneath the root. The AI engine runs in a separate private-Python process with that environment inherited.

## Desktop layer

`dubstudio.app` provides the Tk desktop UI. `DubbingPipeline` validates component readiness, persists a resumable project JSON document, and starts the private worker. Progress is streamed back as JSON lines so model crashes do not take down the UI.

## Engine layer

`dubstudio_engine.pipeline` executes extraction, cinematic stem separation, word-timed ASR, diarization, voice-family analysis, emotion estimation, translation, multi-take TTS, duration fitting, reaction preservation, soundtrack mixing, and output-duration validation.

Each project retains intermediate stems, transcripts, translations, candidate takes, selected takes and a score manifest. This is intentionally disk-heavy but makes quality problems auditable and later editing possible.

## Updates

`GitHubUpdater` reads the repository's latest GitHub release over HTTPS, compares semantic versions, validates the published SHA-256 sidecar, verifies the Windows Authenticode publisher when configured, and silently reinstalls to the current root. Models/projects are not part of the application update payload.
