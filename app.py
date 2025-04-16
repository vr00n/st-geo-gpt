import streamlit as st
import requests
import json
import time
from streamlit_geolocation import streamlit_geolocation
import openai # Import OpenAI library

# --- Configuration ---
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
SEARCH_RADIUS_METERS = 1500
REFRESH_INTERVAL_SECONDS = 30

# --- Check for OpenAI API Key ---
openai_api_key = st.secrets.get("OPENAI_API_KEY")
if not openai_api_key:
    st.warning("OpenAI API Key not found in st.secrets. Summarization feature will be disabled.", icon="⚠️")
    openai_enabled = False
else:
    openai.api_key = openai_api_key
    openai_enabled = True

# --- Helper Function for Wikipedia Geosearch (Same as before) ---
def get_nearby_wikipedia_pages(latitude, longitude, radius_meters=1000, limit=5): # Limit results to reduce API calls
    """
    Queries the MediaWiki API to find Wikipedia pages near a given lat/lon.
    Returns list of pages, empty list if none found, or None on error.
    """
    params = {
        "action": "query",
        "list": "geosearch",
        "gsradius": radius_meters,
        "gscoord": f"{latitude}|{longitude}",
        "gslimit": limit, # Limit pages fetched
        "format": "json",
        "formatversion": 2
    }
    try:
        response = requests.get(WIKIPEDIA_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            st.error(f"Wikipedia API Error: {data['error'].get('info', 'Unknown error')}")
            return None
        return data.get("query", {}).get("geosearch", [])
    except requests.exceptions.Timeout:
        st.error("Wikipedia API request timed out.")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Network or API request failed: {e}")
        return None
    except json.JSONDecodeError:
        st.error("Failed to decode the response from Wikipedia API.")
        return None

# --- Helper Function for OpenAI Summarization ---
@st.cache_data(ttl=3600) # Cache summaries for an hour to save API calls
def get_openai_summary(page_title):
    """
    Uses OpenAI API to get a brief summary of a Wikipedia page title.
    """
    if not openai_enabled:
        return "OpenAI summarization disabled (API key missing)."

    try:
        prompt = f"Briefly summarize the subject of the Wikipedia page titled '{page_title}' in one concise sentence."

        response = openai.chat.completions.create(
            model="gpt-3.5-turbo", # Or "gpt-4" if available and preferred
            messages=[
                {"role": "system", "content": "You are an assistant that summarizes Wikipedia page topics concisely."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=60,
            temperature=0.3, # Lower temperature for more factual summary
            timeout=15 # Add timeout for OpenAI call
        )
        summary = response.choices[0].message.content.strip()
        return summary
    except openai.APITimeoutError:
         st.warning(f"OpenAI request timed out for '{page_title}'.", icon="⏳")
         return None
    except Exception as e:
        # Avoid showing full error details which might leak info
        st.warning(f"Could not get OpenAI summary for '{page_title}'. Error: {type(e).__name__}", icon="⚠️")
        # print(f"OpenAI Error for '{page_title}': {e}") # Optional: Log detailed error server-side
        return None


# --- Initialize Session State ---
if 'running' not in st.session_state:
    st.session_state.running = False
if 'last_location' not in st.session_state:
    st.session_state.last_location = None
if 'last_results' not in st.session_state:
    st.session_state.last_results = []
if 'status_message' not in st.session_state:
    st.session_state.status_message = "Press 'Start Tracking' to begin."
if 'error_message' not in st.session_state:
    st.session_state.error_message = None
if 'summaries' not in st.session_state:
     st.session_state.summaries = {} # Store summaries {page_id: summary_text}


# --- Streamlit App UI ---
st.set_page_config(layout="wide")
st.title("🚶 Live Nearby Wikipedia Finder with AI Summaries")

st.markdown(f"""
Press 'Start Tracking' to automatically check for nearby Wikipedia pages
every **{REFRESH_INTERVAL_SECONDS} seconds** using your current browser location.
If pages are found and OpenAI is configured, AI summaries will be generated.
""")
st.warning(f"""
🔴 **Warning:** This app uses a method (`time.sleep`) that may make the
UI unresponsive during the {REFRESH_INTERVAL_SECONDS}-second wait period between checks.
Also, frequent AI summaries may incur OpenAI API costs.
""")


# --- Control Buttons ---
col1, col2 = st.columns(2)
with col1:
    if st.button("🚀 Start Tracking", disabled=st.session_state.running, use_container_width=True):
        st.session_state.running = True
        st.session_state.status_message = "Initiating location tracking..."
        st.session_state.error_message = None
        st.session_state.last_results = []
        st.session_state.last_location = None
        st.session_state.summaries = {} # Clear summaries on start
        st.experimental_rerun()

with col2:
    if st.button("🛑 Stop Tracking", disabled=not st.session_state.running, use_container_width=True):
        st.session_state.running = False
        st.session_state.status_message = "Tracking stopped by user."
        st.session_state.error_message = None
        st.experimental_rerun()

# --- Display Status and Errors ---
if st.session_state.error_message:
    st.error(st.session_state.error_message)

st.info(st.session_state.status_message)

# --- Display Last Known Info ---
results_placeholder = st.container()
with results_placeholder:
    # Display Location
    if st.session_state.last_location:
        try:
            loc = st.session_state.last_location
            ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(loc['timestamp']/1000))
            st.write(f"📍 Last known location: Lat={loc['latitude']:.5f}, Lon={loc['longitude']:.5f} (Accuracy: {loc.get('accuracy')}m) at {ts}")
        except Exception:
             st.write(f"📍 Last known location data: {st.session_state.last_location}")

    # Display Results and Summaries
    if st.session_state.last_results:
        st.success(f"✅ Found **{len(st.session_state.last_results)}** recognized Wikipedia page(s):")
        for page in st.session_state.last_results:
            page_id = page.get('pageid')
            title = page.get('title', 'N/A')
            distance = page.get('dist', 'N/A')
            wiki_url = f"https://en.wikipedia.org/?curid={page_id}"

            col_link, col_summary = st.columns([2,3]) # Layout columns for link and summary

            with col_link:
                st.markdown(f"**[{title}]({wiki_url})**")
                st.caption(f"Distance: {distance:.1f}m")

            with col_summary:
                # Check if summary already generated and stored, or generate it
                if page_id in st.session_state.summaries:
                    summary = st.session_state.summaries[page_id]
                    if summary:
                         st.info(f"**AI Summary:** {summary}")
                    else:
                         st.caption("Summary not available.")
                elif openai_enabled: # Only try to generate if not already stored and openai is enabled
                    with st.spinner(f"Generating summary for '{title}'..."):
                        summary = get_openai_summary(title)
                        st.session_state.summaries[page_id] = summary # Store summary (even if None)
                        if summary:
                            st.info(f"**AI Summary:** {summary}")
                        else:
                            st.caption("Could not retrieve summary.")
                else:
                     st.caption("OpenAI Summaries disabled.") # Show if OpenAI is off

            st.divider() # Separator between entries

    elif st.session_state.running:
        st.write("⚪ No pages found nearby at the last check.")


# --- Main Execution Loop ---
if st.session_state.running:
    # 1. Get Location
    location_data = streamlit_geolocation(key='geoloc')

    current_location = None
    if location_data and 'latitude' in location_data and 'longitude' in location_data:
        current_location = location_data
        st.session_state.last_location = current_location
        st.session_state.error_message = None
        st.session_state.status_message = f"✅ Location acquired ({current_location['latitude']:.4f}, {current_location['longitude']:.4f}). Searching Wikipedia..."
        if not st.session_state.get('status_updated', False):
            st.session_state.status_updated = True
            st.experimental_rerun()

    elif location_data and 'error' in location_data:
        st.session_state.error_message = f"🚫 Geolocation Error: {location_data['error']['message']} (Code: {location_data['error']['code']}). Tracking stopped."
        st.session_state.status_message = "Tracking stopped due to location error."
        st.session_state.running = False
        st.session_state.status_updated = False
        st.experimental_rerun()

    # 2. Search Wikipedia & Trigger Summaries (if location obtained and status updated)
    if current_location and st.session_state.get('status_updated', False):
        lat = current_location['latitude']
        lon = current_location['longitude']
        nearby_pages = get_nearby_wikipedia_pages(lat, lon, SEARCH_RADIUS_METERS)

        # Clear old summaries before adding new ones for the current results
        st.session_state.summaries = {}

        if nearby_pages is not None:
            st.session_state.last_results = nearby_pages
            if not nearby_pages:
                st.session_state.status_message = f"⚪ No pages found within {SEARCH_RADIUS_METERS}m. Waiting {REFRESH_INTERVAL_SECONDS}s..."
            else:
                 # Summaries will be generated during the results display phase on the next rerun
                 st.session_state.status_message = f"✅ Found {len(nearby_pages)} page(s). Waiting {REFRESH_INTERVAL_SECONDS}s..."
        else:
             st.session_state.status_message = f"⚠️ Error searching Wikipedia. Waiting {REFRESH_INTERVAL_SECONDS}s..."
             st.session_state.last_results = []

        # 3. Wait and Schedule Rerun
        countdown_placeholder = st.empty()
        for i in range(REFRESH_INTERVAL_SECONDS, 0, -1):
            countdown_placeholder.write(f"⏳ Next check in {i} seconds...")
            time.sleep(1)
        countdown_placeholder.empty()

        st.session_state.status_updated = False
        st.experimental_rerun()

    elif not location_data and st.session_state.running:
         st.session_state.status_message = "⏳ Waiting for browser location permission/data..."
         # Let component handle rerun


# --- Add Footer ---
st.markdown("---")
st.caption(f"Using MediaWiki Geosearch API, OpenAI ({'Enabled' if openai_enabled else 'Disabled'}), & `streamlit-geolocation`. Radius: {SEARCH_RADIUS_METERS}m. Interval: {REFRESH_INTERVAL_SECONDS}s.")
