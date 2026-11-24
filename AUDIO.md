# Audio: phases 5A–5F

Reel Lab can discover music, collect outdoor reference Reel observations, automatically select a soundtrack, mix local audio, move cuts to detected beats, and report music performance. Generation still creates an unapproved draft. Existing profiles default to `audio_mode: off` so updating the app won't unexpectedly change existing output.

## Quick start on the deployment PC

From the existing project folder, pull this update (`git pull --ff-only`) and launch `Reel Lab.cmd`. Under **Account creative profiles**, open your actual TALON profile and set:

| Setting | Suggested starting value |
|---|---|
| Music preferences | Ambient electronic, cinematic instrumental, indie rock, natural mountain sounds |
| Soundtrack source | local (recommended first), native, auto, or off |
| Audio mix preset | auto |
| Align cuts to detected beats | checked |
| Require advertising eligibility | checked |

Save the profile. The `auto` source considers both local and authorized native tracks; it does not download songs from other creators or silently substitute an unlicensed track. With music enabled, insufficient eligible music stops generation before queuing a draft. There is no extra paid service or Python dependency. FFmpeg and ffprobe are required for local audio analysis and rendering.

## 5A. Discover Instagram music and trend snapshots

Use [Meta's official Instagram Audio API](https://developers.facebook.com/documentation/instagram-platform/content-publishing/audio-api). This implementation uses Facebook Login, a connected professional Instagram account, its numeric user ID, and a valid token with `instagram_basic` and `instagram_content_publish`. Do not paste tokens into the chat or dashboard. Use your existing private `.env` setup. The API may require app approval or account-specific access; audio availability differs from the mobile app. This is not verified against your live account yet.

The dashboard's **Discover Instagram audio** section performs a read-only search. A blank query saves the platform's general trending list; a query saves keyword search results. These are not evidence of popularity among mountaineers. The returned track ID, artist, title, duration and available ads eligibility are stored in `data/audio.sqlite3`. Temporary download URLs are not stored or used. The discovery commands explicitly request Meta data even in dry-run mode; there are no posting requests.

```powershell
& ".\Reel Lab.cmd" audio-discover
& ".\Reel Lab.cmd" audio-discover --query "cinematic"
& ".\Reel Lab.cmd" audio-refresh --query "ambient" --query "indie"
& ".\Reel Lab.cmd" audio-list
& ".\Reel Lab.cmd" audio-trends
```

You can inspect original-sound results with `audio-discover --type original_sound`, but automatic native selection restricts itself to music because an original sound label by itself does not establish music or commercial rights. The ads eligibility flag is a conservative platform signal, not a blanket license for external use. Unknown or false eligibility is excluded by default. Manually review the audio and current terms for brand use.

### Native attachment, not rebaking tracks

Native selection is opt-in: set `ALLOW_NATIVE_AUDIO=true` in your private `.env` and choose `native` or `auto` in your profile. Reel Lab only selects fresh cached native music belonging to the configured IG account (refreshed within seven days). It sends the documented `audio_configuration` object during media-container creation, including the selected audio ID and volume levels. Meta adds the music at publication; the local video preview **does not contain the native track**, and native music is not beat-snapped or ducked locally. The integration explicitly revalidates the track ID, type, length and required ads eligibility before posting, and requires a separate soundtrack review at approval. CLI: `approve ID --review-native-audio`.

The official API documents attachment for Reels, but the combination of Trial Reel parameters and our resumable upload has not been tested with your live account. Test one authorized Trial Reel before enabling native music for a production queue; URL upload is the documented example for native audio. Reel Lab does not silently revert to an ordinary Reel or retry without music if Meta rejects the request. The original publishing safety settings still apply. For native tracks where Meta does not provide the necessary eligibility metadata, choose local licensed audio instead.

## 5B. Study outdoor accounts without inventing song data

The **Outdoor Reel research** dashboard includes a starting watchlist: Arc'teryx, Patagonia, Mammut, Mountain Hardwear, Black Diamond, Norrøna, Cody Townsend, and The Fifty Project. For supported public professional accounts, the optional read-only Business Discovery lookup retrieves recent Reel metadata (permalink, timestamp, audio type where exposed, likes/comments). It may be unavailable or reject a field for a given account. It will not identify exact tracks, access restricted content, or download competitor videos.

```powershell
& ".\Reel Lab.cmd" audio-research mammut --limit 20
& ".\Reel Lab.cmd" audio-research-list
```

Open a public reference Reel in Instagram, tap its audio label, and record the actual song and artist (or original sound label) together with its permalink. If a matching authorized catalog item exists, record its key. Otherwise keep it as research only. Example syntax with illustrative values (replace them with a real observation):

```powershell
& ".\Reel Lab.cmd" audio-reference "https://www.instagram.com/reel/REPLACE_ME/" --account mammut --title "Observed title" --artist "Observed artist" --tags "cinematic, snow, alpine"
& ".\Reel Lab.cmd" audio-references
```

I recommend sampling 5–10 recent Reels per account and noting their footage category. Track matches influence the music candidate score only when the recorded key matches or the track title and artist both match. A research reference is never a license or a publishable track. Dates and ranks distinguish observed research from general platform trends. There are no prepopulated or fictitious reports of competitor soundtrack use.

## 5C. Local music library and automatic selection

For complete offline editing, collect original tracks or music you have verified permits synchronization with commercial social video, including ads if needed. You may use a no-cost licensed library if its terms cover your intended usage. A downloaded social-media track or a music streaming subscription is not enough by itself. Keep your license record, creator attribution where required, and the exact audio file. Reel Lab requires an explicit rights confirmation and note for each imported local track; it does not establish legal eligibility itself. Store the tracks in a private folder and keep those paths stable.

```powershell
& ".\Reel Lab.cmd" audio-import "C:\ReelLab\music\alpine.wav" --title "Alpine" --artist "Actual artist" --tags "ambient cinematic mountaineering" --license-note "Your verified license source and permission" --confirm-rights --ads-eligible
```

Only use `--ads-eligible` if you have verified the license permits advertising. Optional `--offset 12.5` starts the soundtrack 12.5 seconds into the local file. Registration calculates a file hash, duration, approximate tempo and beat times. A track must be long enough after that offset to cover the whole reel. No looping, downloading, or rights inference occurs.

The director creates the video editing plan as before. Then the soundtrack selector filters rights, duration, freshness, account, and source settings, ranks tracks using account preferences, footage labels, verified reference observations, general trend recency, and supported performance signals, and asks the local text LLM to choose from the top six eligible candidates. If its choice is invalid or the local music-selection call is unavailable, the highest-ranked eligible candidate is used. The model never receives credentials, local paths, raw audio or permission to supply external track IDs. The exact selection and reason are stored with the draft.

To revoke a track, disable it from the dashboard or use `audio-disable TRACK_KEY`; `audio-enable TRACK_KEY` restores availability only after you have reviewed its rights. Disabling survives native refreshes. It blocks new selection and approval and stops an already-approved soundtrack at the publishing worker. Pause the worker and cancel any pending approved jobs for a revoked track, since the existing worker treats failed live attempts conservatively as uncertain until reconciled.

### Continuous discovery and generation

For a named profile with native/auto enabled and `ALLOW_NATIVE_AUDIO=true`, opt in to scheduled discovery within the local generation worker:

```powershell
& ".\Reel Lab.cmd" generate-worker talon-mountain-wear --max-pending 2 --spacing-hours 24 --refresh-native-hours 24 --audio-query "cinematic" --audio-query "ambient"
```

This worker runs locally and is separate from the publisher. Its explicit refresh option reads the native catalog once on startup and periodically at the selected interval, then selects only eligible cached tracks. If discovery fails, cached tracks can still be used until their freshness window expires. Only drafts are generated. To run fully offline with registered local music, omit the refresh options and select local mode.

## 5D. Mixing and loudness

| Mix preset | Music level | Original audio level |
|---|---:|---:|
| Cinematic | 80% | 35% |
| Dialogue | 20% | 100% |
| Natural | 30% | 85% |

`auto` chooses dialogue when the selected footage has nonempty transcripts; otherwise cinematic. Choose natural mode for wind, snow, rope and equipment sounds. Audio levels are relative mix settings, not measured perceived loudness. For local music, FFmpeg mixes the track, fades its ends, dynamically ducks it in dialogue mode (using the original audio as a side-chain), targets -16 LUFS integrated loudness and -1.5 dBTP via its single-pass loudness normalizer, and preserves the video stream. Actual loudness may vary; listen to the output. The mixed MP4 is the final preview that is uploaded. Native attachment uses just the two volume levels provided by Meta, not those local filters.

## 5E. Beat-aligned cuts

A lightweight CPU-only onset analyzer decodes the first three minutes of a registered local track into mono PCM, estimates inter-onset tempo and stores detected beat candidates plus a regularity confidence score. It is intentionally conservative, not a professional beat tracker. When reliable (confidence at least 0.65), the editor moves each internal cut by at most 0.35 seconds to the nearest detected beat, only if both neighboring clips have sufficient source footage and stay at least one second long. The overall duration and text-overlay timeline are preserved. Uncertain/irregular music, tracks without detected beats, and native tracks leave the original cut plan unchanged. Actual cuts are quantized to the video frame rate, not sample-perfect. Review the result; future improvements can include a more advanced tempo/beat model and phrase boundaries.

## 5F. Performance feedback

```powershell
& ".\Reel Lab.cmd" audio-report --profile talon-mountain-wear --age 72
& ".\Reel Lab.cmd" audio-report --profile talon-mountain-wear --age 24
```

The report joins real published live jobs, their selected audio snapshots and existing metrics at a single age (24 or 72 hours), grouped by creative profile and track. It reports record count, mean views, complete sample count and mean `(likes + comments + shares + saved) / views` for complete, positive-view snapshots. Missing metrics are not interpreted as zeros; simulated posts are excluded. The selection ranking considers the 72-hour interaction rate only after at least three complete samples for the same profile, and caps this signal. Differences between audio tracks are descriptive, not proof that the music caused engagement; footage, timing and audiences vary. Test different styles on genuinely distinct, comparable content.

## Verification and limits

The tests cover official API request shapes using mocks, read-only reference discovery, licensing/eligibility gating, disabled tracks, generation provenance, beat-timing bounds, metric grouping, and real FFmpeg rendering with synthetic test audio. No real Meta token is required for these tests. Native availability, Trial Reel + audio compatibility, actual Ollama quality, specific commercial licenses, and performance on your GTX 950 require an authorized deployment test. Keep the approval gate on. All music metadata and license notes are stored locally under `data/`, excluded from Git.
