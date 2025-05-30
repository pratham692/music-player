import streamlit as st
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE
from mutagen.id3 import ID3NoHeaderError
from mutagen import File as MutagenFile
import io
import os
import time
from datetime import datetime, timedelta
import requests
import random # For shuffle

# --- Page Configuration ---
st.set_page_config(
    page_title="Advanced Music Player Pro",
    page_icon="🎶",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Helper Functions ---
def get_metadata(file_obj, filename=""):
    """Extracts metadata from an audio file object."""
    metadata = {"title": os.path.splitext(filename)[0] if filename else "Unknown Title",
                "artist": "Unknown Artist",
                "album": "Unknown Album",
                "duration": 0,
                "art": None}
    try:
        # Ensure file_obj is seekable and at the beginning
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)

        file_type_hint = filename.lower().split('.')[-1] if filename else None

        if file_type_hint == "mp3":
            audio = MP3(file_obj)
        elif file_type_hint == "flac":
            audio = FLAC(file_obj)
        elif file_type_hint == "ogg":
            audio = OggVorbis(file_obj)
        elif file_type_hint == "wav":
            audio = WAVE(file_obj)
        else: # Fallback to generic MutagenFile if type is unknown or not handled above
            audio = MutagenFile(file_obj, easy=True) # easy=True can simplify tag access

        if not audio: # If MutagenFile couldn't parse it
            return metadata

        metadata["duration"] = int(audio.info.length)

        if isinstance(audio, MP3):
            if 'TIT2' in audio: metadata["title"] = str(audio['TIT2'])
            if 'TPE1' in audio: metadata["artist"] = str(audio['TPE1'])
            if 'TALB' in audio: metadata["album"] = str(audio['TALB'])
            if 'APIC:' in audio: metadata["art"] = audio['APIC:'].data
        elif isinstance(audio, FLAC):
            if 'title' in audio: metadata["title"] = ", ".join(audio['title'])
            if 'artist' in audio: metadata["artist"] = ", ".join(audio['artist'])
            if 'album' in audio: metadata["album"] = ", ".join(audio['album'])
            if audio.pictures: metadata["art"] = audio.pictures[0].data
        elif isinstance(audio, OggVorbis): # OggVorbis uses lowercase keys
            if 'title' in audio: metadata["title"] = ", ".join(audio['title'])
            if 'artist' in audio: metadata["artist"] = ", ".join(audio['artist'])
            if 'album' in audio: metadata["album"] = ", ".join(audio['album'])
        elif isinstance(audio, WAVE): # WAVE metadata is less standard
            pass # Duration is primary for WAV here
        elif audio.tags: # For MutagenFile with easy=True
             if 'title' in audio.tags: metadata["title"] = str(audio.tags['title'][0])
             if 'artist' in audio.tags: metadata["artist"] = str(audio.tags['artist'][0])
             if 'album' in audio.tags: metadata["album"] = str(audio.tags['album'][0])

    except ID3NoHeaderError:
        st.warning(f"File '{filename}' appears to be an MP3 but has no ID3 tags. Using filename as title.")
    except Exception as e:
        st.debug(f"Could not read metadata for '{filename}': {e}") # More detailed debug
    finally:
        if hasattr(file_obj, 'seek'): # Reset cursor for potential reuse
            file_obj.seek(0)
    return metadata

def format_duration(seconds):
    """Formats seconds into MM:SS string."""
    if seconds is None or not isinstance(seconds, (int, float)) or seconds < 0:
        return "--:--"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"

def fetch_url_content(url):
    """Fetches content from a URL, returns BytesIO object and filename."""
    try:
        response = requests.get(url, stream=True, timeout=10)
        response.raise_for_status()
        content = io.BytesIO(response.content)
        filename = url.split('/')[-1].split('?')[0]
        if not filename: # If URL ends with / or has no clear filename part
            filename = "audio_from_url"
        return content, filename
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching URL '{url}': {e}")
        return None, None

# --- Session State Initialization ---
default_states = {
    'playlist': [],
    'current_track_index': -1,
    'sleep_timer_active': False,
    'sleep_timer_end_time': None,
    'autoplay_next': True,
    'shuffle_mode': False,
    'loop_current_track': False,
    'upload_method': 'Upload Audio Files' # Default upload method
}
for key, value in default_states.items():
    if key not in st.session_state:
        st.session_state[key] = value

# --- Custom CSS ---
st.markdown("""
<style>
    /* ... [Same CSS as before or your preferred styling] ... */
    .stApp {}
    .stButton>button { border-radius: 10px; padding: 8px 15px; margin: 5px 2px; }
    .stFileUploader label, .stTextInput label, .stNumberInput label, .stRadio label { font-weight: bold; }
    .song-info { padding: 15px; border-radius: 10px; background-color: #e9ecef; margin-bottom: 20px; text-align: center; }
    .song-title { font-size: 1.5em; font-weight: bold; color: #333; }
    .song-artist-album { font-size: 1.1em; color: #555; }
    .playlist-item-button {
        width: 100%;
        text-align: left;
        padding: 10px;
        border: 1px solid transparent; /* For consistent height */
        background-color: transparent;
    }
    .playlist-item-button:hover {
        background-color: #f0f0f0;
        border-color: #ddd;
    }
    .current-playlist-item .playlist-item-button {
        background-color: #d0e0f0; /* Highlight current track */
        font-weight: bold;
        border-color: #b0c0d0;
    }
    .album-art { max-width: 200px; max-height: 200px; border-radius: 8px; margin: auto; display: block; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
</style>
""", unsafe_allow_html=True)


# --- Sidebar ---
with st.sidebar:
    st.header("🎵 Music Source")

    st.session_state.upload_method = st.radio(
        "Choose input method:",
        ('Upload Audio Files', 'Enter Audio URL'),
        key='upload_method_radio',
        horizontal=True
    )

    if st.session_state.upload_method == 'Upload Audio Files':
        uploaded_files = st.file_uploader(
            "Select audio files from your computer (MP3, FLAC, WAV, OGG). You can select multiple files from a folder.",
            type=["mp3", "flac", "wav", "ogg"],
            accept_multiple_files=True,
            key="file_uploader_key" # Add a key for stability if needed
        )
        if uploaded_files:
            new_files_added_count = 0
            for uploaded_file in uploaded_files:
                if not any(item['name'] == uploaded_file.name for item in st.session_state.playlist):
                    file_bytes_main = io.BytesIO(uploaded_file.getvalue()) # For playback
                    file_bytes_meta = io.BytesIO(uploaded_file.getvalue()) # Fresh BytesIO for metadata
                    metadata = get_metadata(file_bytes_meta, uploaded_file.name)
                    st.session_state.playlist.append({
                        'source': file_bytes_main,
                        'metadata': metadata,
                        'type': 'file',
                        'name': uploaded_file.name
                    })
                    new_files_added_count += 1
            if new_files_added_count > 0:
                st.success(f"Added {new_files_added_count} new file(s) to playlist!")
                if st.session_state.current_track_index == -1 and st.session_state.playlist:
                    st.session_state.current_track_index = 0 # Auto-select first if nothing playing
            uploaded_files = [] # Clear to prevent re-processing on simple rerun, though uploader handles this


    elif st.session_state.upload_method == 'Enter Audio URL':
        url_input = st.text_input("Enter direct audio URL (e.g., link to .mp3)")
        if st.button("Add from URL") and url_input:
            if not any(item['source'] == url_input for item in st.session_state.playlist if item['type'] == 'url'):
                # For URLs, full metadata extraction downloads the file.
                # Consider a lighter approach if this is too slow, e.g., just filename.
                content_for_meta, filename_from_url = fetch_url_content(url_input)
                if content_for_meta:
                    metadata = get_metadata(content_for_meta, filename_from_url)
                    st.session_state.playlist.append({
                        'source': url_input, # Store URL string for st.audio
                        'metadata': metadata,
                        'type': 'url',
                        'name': filename_from_url if filename_from_url else url_input
                    })
                    st.success(f"Added '{filename_from_url if filename_from_url else url_input}' to playlist!")
                    if st.session_state.current_track_index == -1 and st.session_state.playlist:
                        st.session_state.current_track_index = 0
                # No else here, fetch_url_content already shows error
            else:
                st.warning("This URL is already in the playlist.")

    st.header("⚙️ Playback Options")
    st.session_state.autoplay_next = st.checkbox("Autoplay when track changes", value=st.session_state.get('autoplay_next', True))
    st.session_state.shuffle_mode = st.checkbox("Shuffle Playback", value=st.session_state.get('shuffle_mode', False))
    st.session_state.loop_current_track = st.checkbox("Loop Current Track", value=st.session_state.get('loop_current_track', False))


    st.header("⏱️ Sleep Timer")
    sleep_minutes = st.number_input("Stop after (minutes):", min_value=0, value=st.session_state.get('set_sleep_minutes', 0), step=5, key="sleep_min_input")

    col1_sleep, col2_sleep = st.columns(2)
    if col1_sleep.button("Start Sleep Timer", disabled=(sleep_minutes == 0), use_container_width=True):
        st.session_state.sleep_timer_active = True
        st.session_state.sleep_timer_end_time = datetime.now() + timedelta(minutes=sleep_minutes)
        st.session_state.set_sleep_minutes = sleep_minutes # Remember value
        st.success(f"Sleep timer set for {sleep_minutes} minutes.")
    if col2_sleep.button("Cancel Sleep Timer", disabled=not st.session_state.sleep_timer_active, use_container_width=True):
        st.session_state.sleep_timer_active = False
        st.session_state.sleep_timer_end_time = None
        st.session_state.set_sleep_minutes = 0 # Reset
        st.info("Sleep timer cancelled.")

    if st.session_state.sleep_timer_active and st.session_state.sleep_timer_end_time:
        remaining_time = st.session_state.sleep_timer_end_time - datetime.now()
        if remaining_time.total_seconds() > 0:
            st.info(f"Stopping in: {str(timedelta(seconds=int(remaining_time.total_seconds())))}")
        else: # Timer might have just expired
            st.info("Sleep timer active but end time reached.")


# --- Main Area ---
st.title("🎧 Advanced Music Player Pro")

if not st.session_state.playlist:
    st.info("Upload some music files or add a URL to get started!")
else:
    # --- Playlist Display and Selection ---
    st.subheader("📜 Playlist / Queue")
    # Using st.container for better layout control if needed, and custom styling for items
    playlist_container = st.container()
    with playlist_container:
        for i, track in enumerate(st.session_state.playlist):
            track_name_display = f"{i + 1}. {track['metadata'].get('title', track['name'])}"
            is_current = (i == st.session_state.current_track_index)

            # Use a div styled as a button via markdown for better control over appearance if st.button is limiting
            item_class = "playlist-item-button-wrapper" # For potential outer styling
            if is_current:
                item_class += " current-playlist-item"

            # Use actual st.button for interactivity
            # We assign a unique key to each button in the playlist
            if st.button(track_name_display, key=f"playlist_track_{i}", use_container_width=True,
                         help=f"Play: {track['metadata'].get('title', track['name'])}"):
                st.session_state.current_track_index = i
                # Autoplay will be handled by st.audio based on st.session_state.autoplay_next

    # --- Current Song Info and Player ---
    if 0 <= st.session_state.current_track_index < len(st.session_state.playlist):
        current_track_data = st.session_state.playlist[st.session_state.current_track_index]
        metadata = current_track_data['metadata']

        st.markdown("---")
        st.subheader("🎶 Now Playing")

        info_cols = st.columns([1,2]) # Album Art (optional), Text Info

        with info_cols[0]:
            if metadata.get("art"):
                try:
                    st.image(metadata["art"], use_column_width='auto', width=200, caption="Album Art", output_format="auto",
                             # Apply class for centering and styling if needed
                             # Not directly stylable like HTML img, but st.image has width
                             )
                except Exception as e:
                    st.caption("Art display error.")
            else:
                st.markdown("<div style='height: 200px; display: flex; align-items: center; justify-content: center; background-color: #f0f0f0; border-radius: 8px; color: #aaa;'>No Album Art</div>", unsafe_allow_html=True)


        with info_cols[1]:
            st.markdown(f"<div class='song-title'>{metadata.get('title', 'Unknown Title')}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='song-artist-album'>🎤 Artist: {metadata.get('artist', 'Unknown Artist')}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='song-artist-album'>📀 Album: {metadata.get('album', 'Unknown Album')}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='song-artist-album'>⏱️ Duration: {format_duration(metadata.get('duration', 0))}</div>", unsafe_allow_html=True)

        # --- Audio Player Element ---
        audio_source = current_track_data['source']
        audio_data_to_play = audio_source.getvalue() if isinstance(audio_source, io.BytesIO) else audio_source

        audio_format = "audio/basic" # Let Streamlit infer, or be more specific
        if isinstance(current_track_data['name'], str):
            ext = current_track_data['name'].lower().split('.')[-1]
            if ext == "mp3": audio_format = "audio/mpeg"
            elif ext == "wav": audio_format = "audio/wav"
            elif ext == "ogg": audio_format = "audio/ogg"
            elif ext == "flac": audio_format = "audio/flac" # Add FLAC format

        st.audio(
            audio_data_to_play,
            format=audio_format,
            start_time=0,
            autoplay=st.session_state.autoplay_next, # Autoplay if new track and enabled
            loop=st.session_state.loop_current_track # Loop current track if enabled
        )

        # --- Music Controls ---
        st.markdown("---")
        # Use 3 columns for Prev, Spacer, Next to center them a bit more easily
        # Or use 5 columns if you want more space: [1,1, spacer, 1,1]
        c1, c2, c3 = st.columns([1,0.2,1])

        with c1:
            if st.button("⏮️ Previous", use_container_width=True, help="Go to previous track"):
                if st.session_state.playlist: # Ensure playlist is not empty
                    if st.session_state.current_track_index > 0:
                        st.session_state.current_track_index -= 1
                    else: # Loop to last track
                        st.session_state.current_track_index = len(st.session_state.playlist) - 1
        with c3:
            if st.button("Next ⏭️", use_container_width=True, help="Go to next track"):
                if st.session_state.playlist:
                    if st.session_state.shuffle_mode:
                        if len(st.session_state.playlist) > 1:
                            new_idx = st.session_state.current_track_index
                            while new_idx == st.session_state.current_track_index:
                                new_idx = random.randint(0, len(st.session_state.playlist) - 1)
                            st.session_state.current_track_index = new_idx
                        # If only 1 song, shuffle does nothing, current index remains
                    else: # Serial mode
                        if st.session_state.current_track_index < len(st.session_state.playlist) - 1:
                            st.session_state.current_track_index += 1
                        else: # Loop to first track
                            st.session_state.current_track_index = 0
    else:
        if st.session_state.playlist:
            st.info("Select a track from the playlist to start, or the first track will load if autoplay is on.")
            # Auto-select first track if not already selected and playlist exists
            if st.session_state.current_track_index == -1:
                 st.session_state.current_track_index = 0
                 st.experimental_rerun() # Rerun to load and play the first track

# --- Sleep Timer Logic ---
if st.session_state.sleep_timer_active and st.session_state.sleep_timer_end_time:
    if datetime.now() >= st.session_state.sleep_timer_end_time:
        st.session_state.sleep_timer_active = False
        st.session_state.sleep_timer_end_time = None
        st.session_state.current_track_index = -1 # Stop playback
        st.session_state.set_sleep_minutes = 0 # Reset timer input
        st.warning("😴 Sleep timer finished. Playback stopped.")
        st.experimental_rerun() # Rerun to reflect the stopped state

# --- Footer ---
st.markdown("---")
st.markdown("<div style='text-align: center; color: grey;'>Music Player Pro V2</div>", unsafe_allow_html=True)
