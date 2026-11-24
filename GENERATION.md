# Automatic reel generation — phases 1–4

Reel Lab can now turn tagged original footage into a finished, unapproved Reel draft: select footage according to an account profile, create a constrained editing plan, render clips in sequence, overlay text, and write the caption and relevant hashtags. It does not publish or approve generated drafts. Optional music selection, mixing and beat matching are described in [AUDIO.md](AUDIO.md); animated subtitles remain a future phase.

## 1. Prepare the account profile

Open the local Reel Lab dashboard (`Reel Lab.cmd` on Windows). In Account creative profiles, enter your own account name, description, target audience, tone, typical subjects, editing style, and any content restrictions. Set desired length, maximum clips, and maximum hashtags. Save the profile. Use a lowercase slug for the name (e.g. `campus-life`). A profile describes a creative style; it is not an Instagram login or an authorization to post. The existing Instagram credentials still control the single publishing account. Keep personal or private footage out of the monitored inbox.

Alternatively, copy `profile.example.json` to a private file under `data/`, edit it, and import it. Do not place secrets in profiles. From the project directory:

```powershell
Copy-Item profile.example.json data\my-account.json
# Edit data\my-account.json to describe your account.
& ".\Reel Lab.cmd" profile-import data\my-account.json
& ".\Reel Lab.cmd" profile-list
& ".\Reel Lab.cmd" profile-show my-account
```

You can use multiple creative profiles; the generation worker uses one at a time. The default length is 7–30 seconds, up to four distinct source clips and five hashtags. Configure the optional soundtrack mode and music preferences as described in [AUDIO.md](AUDIO.md). The profile is stored in `data/profiles`, excluded from Git.

## 2. Analyze original footage

Your iPhone SMB workflow can keep putting files into `C:\ReelLab\incoming`. The existing `Watch Footage.cmd` continues calling `tag-footage --watch`. The refreshed catalog records dimensions, duration, orientation (including rotation), frame rate, codec, audio presence, and the existing local `qwen3-vl:2b` contact-sheet descriptions. Older entries still work. Stale or modified files are excluded until retagged. No footage is sent to a cloud service; the vision and creative director endpoints must be local.

```powershell
& ".\Reel Lab.cmd" tag-footage "C:\ReelLab\incoming" --watch
& ".\Reel Lab.cmd" footage-tags
```

Install the vision model if you need it: `ollama pull qwen3-vl:2b`. The GTX 950 may require some or all inference to fall back to RAM/CPU; the local vision and text calls request zero keep-alive so models don't remain loaded between jobs. If the PC cannot run the vision model, use a matching `.txt` brief for each clip and run:

```powershell
& ".\Reel Lab.cmd" tag-footage "C:\ReelLab\incoming" --metadata-only --watch
```

For example `IMG_1234.MOV` and `IMG_1234.txt` (describe what actually happens in the video). A transcript, brief or existing vision description is required for selection; technical metadata alone is not enough to determine what a clip contains. Vision describes three sampled frames, not a full temporal understanding of the video. Review its tags before trusting claims about subjects or actions.

### Optional speech transcription and scene boundaries

Install the CPU version of [whisper.cpp](https://github.com/ggml-org/whisper.cpp) and a compatible GGML `base.en` or `tiny.en` model using their installation documentation. For multilingual footage choose a non-`.en` model. Put the executable and model in a private local directory. Reel Lab invokes `whisper-cli` in CPU mode; it extracts up to three minutes of audio per clip and catalogs the text, without generating subtitles yet. With the optional `--scenes` flag, a low-resolution pass estimates visual scene transitions in up to the first two minutes. Both passes add processing time; omit scene detection if the PC is slow.

```powershell
& ".\Reel Lab.cmd" tag-footage "C:\ReelLab\incoming" --watch --whisper-cli "C:\tools\whisper\whisper-cli.exe" --whisper-model "C:\tools\whisper\ggml-base.en.bin" --scenes
```

Or set `WHISPER_CLI` and `WHISPER_MODEL` in the environment of your shell/Windows task (both must be set). If you also use `--metadata-only`, transcripts and text briefs work without the vision model. Do not run competing catalog watchers on the same database. The scan waits for sufficiently old file modification times and rechecks source metadata; if your transfers are unusually slow, allow them to complete before tagging. A failed vision call can fall back to a genuine brief/transcript; otherwise the clip is not tagged.

## 3. Generate one complete draft

In the dashboard, select the saved account profile and click **Generate Reel draft** after the footage catalog has entries. Or use the CLI:

```powershell
& ".\Reel Lab.cmd" generate my-account --at 2027-01-01T18:00:00-06:00
```

Replace the example schedule with your preferred date/time, including the UTC offset. The director uses up to six eligible footage records, ranked by account description/category keyword overlap and recency. It automatically chooses one to six distinct clips, trim points, on-screen text, caption and hashtags. The model is bounded to known clip IDs, not file paths or commands. It retries once if the plan violates the schema, clip bounds, total duration, hashtag limits or overlay timings. If no valid plan can be made, it creates no job. The current Qwen3 1.7B text model is adequate for trying this; CPU offload is fine for background generation. A 4B model can be tested later if more RAM is available. The 4096-token director context may need CPU offload on a 2 GB card.

By default, an original used in a previous generated draft is excluded from later automatic selections, even if that draft is canceled; this helps keep content distinct. An intentional manual reuse is possible with `generate ... --allow-reuse` or the dashboard checkbox. The rendered hash still prevents exact duplicate outputs. The queue stores the full validated plan, account profile snapshot and source hashes alongside the job. Review the actual video, text, caption and privacy restrictions before approval. Account restrictions and quality judgments are guidance for the model, not guarantees.

## 4. Render and review

The renderer uses FFmpeg and ffprobe. Install a full build with H.264/AAC encoders and the `drawtext` filter (with FreeType support). Windows Arial or Linux DejaVu Sans is used for text; the font must be present. The program verifies that original source hashes match the catalog, normalizes each segment to 1080x1920 at 30 fps, pads landscape clips without cropping, preserves original audio or supplies silence, and joins them. Overlay text is passed as literal UTF-8 text files, not FFmpeg code. Output duration, dimensions, audio and size are checked before the draft is queued. Generated MP4s and metadata remain in `data/`.

```powershell
& ".\Reel Lab.cmd" list
& ".\Reel Lab.cmd" show 1
```

Use the actual job ID. In the dashboard, preview the generated clip and its plan. Only approve after reviewing. The existing dry-run/live approval behavior, manual Trial Reel promotion default and worker safeguards still apply. The generation command never calls Instagram.

## 5. Automatic draft queue

Run one catalog watcher (the existing `Watch Footage.cmd`) and one generation worker from separate terminals. The generation worker polls the catalog and creates drafts until the pending queue reaches the configured size; it does not require the publishing worker to be running.

```powershell
& ".\Reel Lab.cmd" generate-worker my-account --max-pending 2 --spacing-hours 24 --seconds 180
```

The worker respects the current queue's pending draft/approved/publishing/uncertain states, picks a staggered due time, and only uses previously unused described footage. It waits when the queue is full or when footage is insufficient. Use Ctrl+C to stop it. Start only one generation worker; pause the worker when modifying its account profile and restart so it loads the new profile. If starting automatically using Windows Task Scheduler, run it under the same user as the existing watcher using the full project path and `Reel Lab.cmd generate-worker my-account ...`. Keep all network shares password-protected.

## Testing

```powershell
python -m unittest discover -s tests -v
```

The test suite includes mocked AI/queue tests and a real synthetic video integration test (skipped if FFmpeg/ffprobe are not installed). The GitHub Linux CI installs FFmpeg and a font for the render test. The local model and actual Instagram account still require testing on the deployment machine.
