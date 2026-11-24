"""Optional local Streamlit UI. Run: streamlit run dashboard.py --server.address 127.0.0.1"""
from datetime import datetime, timezone
import streamlit as st
from reel_lab.config import Config
from reel_lab.store import Store
from reel_lab.cli import add_job
from reel_lab.ai import caption_valid
from reel_lab.instagram import Instagram
from reel_lab.profile import Profile, profiles, load_profile, save_profile
from reel_lab.generate import generate
from reel_lab import footage
from reel_lab.audio import AudioCatalog, OUTDOOR_ACCOUNTS
from reel_lab.acquire import register as register_spotdl

st.set_page_config(page_title='Reel Lab', layout='wide')
c = Config.load(); s = Store(c)
st.title('Reel Lab — Trial Reel Manager')
st.warning('DRY RUN — no publishing requests; explicit audio research is read-only' if c.dry_run else 'LIVE MODE — approved jobs can publish')
st.caption('Keep this dashboard bound to localhost. Run the worker separately.')
st.subheader('Account creative profiles')
existing_profiles=profiles(c.data)
selected=st.selectbox('Choose a profile to view or edit', ['(new)',*existing_profiles])
saved=load_profile(c.data,selected) if selected!='(new)' else None
with st.form('creative-profile-'+selected):
    name=st.text_input('Profile name (lowercase slug)',value=saved.name if saved else 'my-account')
    description=st.text_area('Account description',value=saved.description if saved else '',max_chars=1000)
    audience=st.text_input('Audience',value=saved.audience if saved else '',max_chars=1000)
    tone=st.text_input('Tone',value=saved.tone if saved else 'Natural and concise',max_chars=1000)
    categories=st.text_input('Content categories',value=saved.categories if saved else '',max_chars=1000)
    style=st.text_input('Editing style',value=saved.editing_style if saved else 'Clean, fast-paced cuts',max_chars=1000)
    music=st.text_input('Music preferences',value=saved.music_preferences if saved else '',max_chars=1000)
    modes=('off','local','native','auto'); mixes=('auto','cinematic','dialogue','natural')
    audio_mode=st.selectbox('Soundtrack source',modes,index=modes.index(saved.audio_mode) if saved else 0)
    mix_style=st.selectbox('Audio mix preset',mixes,index=mixes.index(saved.mix_style) if saved else 0)
    beat_sync=st.checkbox('Align cuts to detected beats for local music',value=saved.beat_sync if saved else True)
    require_ads=st.checkbox('Require advertising eligibility (recommended for brands)',value=saved.require_ad_eligible if saved else True)
    restricted=st.text_area('Restricted topics / privacy rules',value=saved.restricted_topics if saved else '',max_chars=1000)
    minimum=st.number_input('Minimum seconds',3,90,saved.min_duration if saved else 7)
    maximum=st.number_input('Maximum seconds',3,90,saved.max_duration if saved else 30)
    clips=st.number_input('Maximum clips',1,6,saved.max_clips if saved else 4)
    hashtags=st.number_input('Maximum hashtags',0,10,saved.max_hashtags if saved else 5)
    if st.form_submit_button('Save account profile'):
        try:
            p=Profile.parse(dict(name=name,description=description,audience=audience,tone=tone,categories=categories,
                editing_style=style,music_preferences=music,restricted_topics=restricted,min_duration=int(minimum),
                max_duration=int(maximum),max_clips=int(clips),max_hashtags=int(hashtags),audio_mode=audio_mode,
                mix_style=mix_style,beat_sync=beat_sync,require_ad_eligible=require_ads))
            save_profile(c.data,p); st.rerun()
        except ValueError as exc: st.error(str(exc))

st.subheader('Audio research and music library')
music_catalog=AudioCatalog(c.data)
with st.expander('Discover Instagram audio (explicit read-only API call)'):
    st.caption('Requires Facebook Login and an authorized token. Blank query means general trending audio, not outdoor-specific popularity.')
    with st.form('discover-audio'):
        query=st.text_input('Track/artist search (leave blank for trending)')
        kind=st.selectbox('Catalog',('music','original_sound'))
        if st.form_submit_button('Search Instagram'):
            try:
                found=music_catalog.discover(c,query,kind); st.success(f'Saved {len(found)} results.')
                st.dataframe([{k:t.get(k) for k in ('key','title','artist','duration','ads_eligible')} for t in found])
            except Exception as exc: st.error(f'Audio discovery failed: {str(exc) if isinstance(exc,ValueError) else type(exc).__name__}')
    st.dataframe(music_catalog.discoveries()[:50])
with st.expander('Outdoor Reel research'):
    st.caption('Public professional-account metadata does not identify an exact song. Open the Reel and record its observed audio label yourself.')
    for account in OUTDOOR_ACCOUNTS: st.write(f'[@{account}](https://www.instagram.com/{account}/)')
    with st.form('research-public'):
        account=st.text_input('Public professional Instagram username',value='mammut')
        if st.form_submit_button('Read recent public Reel metadata'):
            try: st.dataframe(music_catalog.research(c,account))
            except Exception as exc: st.error(f'Research unavailable ({type(exc).__name__}); open reference Reels manually.')
    st.dataframe(music_catalog.research_posts()[:100])
    with st.form('observed-audio'):
        url=st.text_input('Observed Reel permalink')
        account=st.text_input('Creator username')
        title=st.text_input('Observed audio title')
        artist=st.text_input('Observed artist')
        tags=st.text_input('Mood, genre or footage category')
        key=st.text_input('Optional matching catalog track key')
        if st.form_submit_button('Record observed soundtrack'):
            try: music_catalog.add_reference(url,account,title,artist,tags,key); st.rerun()
            except ValueError as exc: st.error(str(exc))
    st.dataframe(music_catalog.references())
with st.expander('Authorize on-demand spotDL acquisition'):
    st.caption('Only register an exact recording you have permission to download and synchronize with commercial video. No automatic matching from unapproved Instagram tracks.')
    with st.form('spotdl-track'):
        spotify=st.text_input('Spotify track URL (without tracking parameters)')
        youtube=st.text_input('Authorized exact YouTube watch URL')
        title=st.text_input('Recording title'); artist=st.text_input('Recording artist'); tags=st.text_input('Mood and genre')
        duration=st.number_input('Expected recording duration (seconds)',3.0,1800.0,180.0)
        note=st.text_area('Permission to download and commercial synchronization license')
        rights=st.checkbox('I verified download and commercial synchronization rights for this exact source')
        ads=st.checkbox('The license also permits advertising')
        if st.form_submit_button('Register authorized recording'):
            try:
                register_spotdl(music_catalog,spotify,youtube,title,artist,tags,note,float(duration),rights_confirmed=rights,ads_eligible=ads); st.rerun()
            except ValueError as exc: st.error(str(exc))
    st.caption('Acquisition occurs only if selected, and requires ALLOW_SPOTDL=true and spotDL installed in the Reel Lab environment.')
with st.expander('Register a licensed local track'):
    with st.form('local-track'):
        path=st.text_input('Local audio file path')
        title=st.text_input('Song title'); artist=st.text_input('Artist')
        tags=st.text_input('Mood, genre, footage style')
        note=st.text_area('License source and commercial synchronization permission')
        rights=st.checkbox('I have verified rights to combine this audio with commercial brand videos')
        ads=st.checkbox('My license also allows advertising')
        offset=st.number_input('Music start offset (seconds)',min_value=0.0,value=0.0)
        if st.form_submit_button('Analyze and register track'):
            try:
                music_catalog.register_local(path,title,artist,tags,note,rights_confirmed=rights,ads_eligible=ads,offset=float(offset)); st.rerun()
            except Exception as exc: st.error(f'Import failed: {str(exc) if isinstance(exc,ValueError) else type(exc).__name__}')
    tracks=music_catalog.tracks()
    st.dataframe([{k:t.get(k) for k in ('key','title','artist','source','provider','tags','duration','bpm','confidence','ads_eligible','enabled')} for t in tracks])
    if tracks:
        with st.form('disable-track'):
            track_key=st.selectbox('Manage a soundtrack',[t['key'] for t in tracks])
            enabled=st.checkbox('Enable after verifying rights; uncheck to disable')
            if st.form_submit_button('Save soundtrack availability'):
                music_catalog.set_enabled(track_key,enabled); st.rerun()
with st.expander('Audio performance — equal-age descriptive comparisons'):
    age=st.selectbox('Metric snapshot age (hours)',(72,24))
    st.caption('Not a causal comparison. Missing interaction metrics are excluded; small samples do not influence music ranking.')
    st.dataframe(s.audio_report(age=age))

st.subheader('Automatic reel generation')
catalog=footage.export(c.data/'footage.sqlite3')
st.caption(f'{len(catalog)} current footage records; only footage with a description is eligible.')
with st.expander('Footage catalog'):
    for item in catalog[:50]:
        st.write(item.get('summary') or item.get('brief') or item.get('transcript','')[:200] or '(No description)',
                 f"{item.get('duration_seconds',0):.1f}s",item.get('tags',[]))
if existing_profiles and catalog:
    with st.form('generate'):
        generation_profile=st.selectbox('Account profile',existing_profiles)
        gen_due=st.text_input('Draft schedule (with timezone)',datetime.now(timezone.utc).isoformat(timespec='seconds'))
        reuse=st.checkbox('Allow footage already used in previous generated drafts')
        if st.form_submit_button('Generate Reel draft'):
            try:
                with st.spinner('Planning and rendering on this PC...'):
                    id=generate(c,s,load_profile(c.data,generation_profile),gen_due,allow_reuse=reuse)
                st.success(f'Generated draft {id}. Review it below.'); st.rerun()
            except Exception as exc: st.error(f'Generation failed: {str(exc) if isinstance(exc,ValueError) else type(exc).__name__}')
else:
    st.info('Save an account profile and run the footage tagger before generating.')
with st.form('new'):
    st.subheader('Create a draft')
    source = st.text_input('Local video path (owned or authorized content)')
    brief = st.text_area('Describe the video, intended audience and concept')
    caption = st.text_area('Caption override (leave blank for local AI)')
    due = st.text_input('Schedule with timezone offset', datetime.now(timezone.utc).isoformat(timespec='seconds'))
    start = st.number_input('Trim start (seconds)', min_value=0.0, value=0.0)
    duration = st.number_input('Duration (seconds)', min_value=3.0, max_value=90.0, value=30.0)
    auto = st.checkbox('Allow Instagram to promote successful trials to followers')
    url = st.text_input('Public HTTPS video URL (URL upload only; must match rendered clip)')
    if st.form_submit_button('Render and draft'):
        try:
            id = add_job(c,s,source,brief,caption,due,start,duration,'SS_PERFORMANCE' if auto else 'MANUAL',url)
            st.success(f'Draft {id} created')
        except Exception as exc: st.error(f'Draft failed ({type(exc).__name__}); check input and configuration.')
st.subheader('Queue')
for j in s.rows():
    with st.expander(f"#{j['id']} • {j['state']} • {j['due']}"):
        st.write(j['caption']); st.write(j['hypothesis']); st.write(j['trial'], j['mode'])
        generation=s.generated(j['id'])
        if generation:
            st.caption('Generated from account: '+generation['profile']['name'])
            st.json(generation['plan'],expanded=False)
        selected_audio=s.audio(j['id'])
        if selected_audio:
            st.write('Soundtrack:',selected_audio['title'],selected_audio['artist'],selected_audio['source'])
            st.caption(f"Music {selected_audio['music_volume']}%, original {selected_audio['video_volume']}%; {selected_audio['mix_style']} mix; {len(selected_audio.get('beat_shifts',[]))} aligned cuts")
            st.caption(selected_audio.get('reason',''))
            if selected_audio['source']=='native': st.warning('Instagram adds this music at publication. The local preview does not include the native soundtrack.')
        if j['state'] == 'draft':
            st.video(j['path'])
            with st.form('edit'+str(j['id'])):
                new_caption = st.text_area('Edit caption', j['caption'])
                new_due = st.text_input('Schedule', j['due'])
                if st.form_submit_button('Save changes'):
                    s.edit(j['id'], caption_valid(new_caption), new_due); st.rerun()
            confirm = st.checkbox('I reviewed the actual video, caption and trial settings', key=f"review-{j['id']}")
            native_review=not selected_audio or selected_audio['source']!='native'
            if not native_review: native_review=st.checkbox('I reviewed the native track and volume; I understand the final soundtrack cannot be previewed locally',key=f"native-review-{j['id']}")
            if st.button('Approve', key=f"approve-{j['id']}", disabled=not (confirm and native_review)):
                try:
                    if not c.dry_run: Instagram(c)
                    s.approve(j['id'],native_audio_reviewed=native_review); st.rerun()
                except ValueError as exc: st.error(str(exc))
        if j['state'] in ('draft','approved') and st.button('Cancel', key=f"cancel-{j['id']}"):
            s.cancel(j['id']); st.rerun()
        if j['mode'] == 'dry' and j['state'] in ('simulated','approved') and st.button('Return to draft', key=f"reset-{j['id']}"):
            s.reset_dry(j['id']); st.rerun()
        if j['error']: st.write(j['error'])
st.subheader('Recent metrics')
st.json(s.history())
