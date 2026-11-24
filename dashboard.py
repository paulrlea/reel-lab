"""Optional local Streamlit UI. Run: streamlit run dashboard.py --server.address 127.0.0.1"""
from datetime import datetime, timezone
import streamlit as st
from reel_lab.config import Config
from reel_lab.store import Store
from reel_lab.cli import add_job
from reel_lab.ai import caption_valid
from reel_lab.instagram import Instagram

st.set_page_config(page_title='Reel Lab', layout='wide')
c = Config.load(); s = Store(c)
st.title('Reel Lab — Trial Reel Manager')
st.warning('DRY RUN — no Instagram requests' if c.dry_run else 'LIVE MODE — approved jobs can publish')
st.caption('Keep this dashboard bound to localhost. Run the worker separately.')
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
        if j['state'] == 'draft':
            st.video(j['path'])
            with st.form('edit'+str(j['id'])):
                new_caption = st.text_area('Edit caption', j['caption'])
                new_due = st.text_input('Schedule', j['due'])
                if st.form_submit_button('Save changes'):
                    s.edit(j['id'], caption_valid(new_caption), new_due); st.rerun()
            confirm = st.checkbox('I reviewed the actual video, caption and trial settings', key=f"review-{j['id']}")
            if st.button('Approve', key=f"approve-{j['id']}", disabled=not confirm):
                if not c.dry_run: Instagram(c)
                s.approve(j['id']); st.rerun()
        if j['state'] in ('draft','approved') and st.button('Cancel', key=f"cancel-{j['id']}"):
            s.cancel(j['id']); st.rerun()
        if j['mode'] == 'dry' and j['state'] in ('simulated','approved') and st.button('Return to draft', key=f"reset-{j['id']}"):
            s.reset_dry(j['id']); st.rerun()
        if j['error']: st.write(j['error'])
st.subheader('Recent metrics')
st.json(s.history())
