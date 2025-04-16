import streamlit as st
import requests
import json
import time
from streamlit_geolocation import streamlit_geolocation # Requires: pip install streamlit-geolocation

# --- Configuration ---
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
SEARCH_RADIUS_METERS = 1500  # How far around the location to search (max 10000)
REFRESH_INTERVAL_SECONDS = 30 # How often to check

# --- Helper Function for Wikipedia Geosearch (Same as before) ---
def get_nearby_wikipedia_pages(latitude, longitude, radius_meters=1000, limit=10):
    """
    Queries the MediaWiki API to find Wikipedia pages near a given lat/lon.
    Returns list of pages, empty list if none found, or None on error.
    """
    params = {
        "action": "query",
        "list": "geosearch",
        "gsradius": radius_meters,
        "gscoord": f"{latitude}|{longitude}",
        "gslimit": limit,
        "format": "json",
        "formatversion": 2
    }
    try:
        response = requests.get(WIKIPEDIA_API_URL, params=params, timeout=10) # Add timeout
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

# --- Initialize Session State ---
# Used to store state across reruns
if 'running' not in st.session_state:
    st.session_state.running = False
if 'last_location' not in st.session_state:
    st.session_state.last_location = None
if 'last_results' not in st.session_state:
    st.session_state.last_results = [] # Initialize as empty list
if 'status_message' not in st.session_state:
    st.session_state.status_message = "Press 'Start Tracking' to begin."
if 'error_message' not in st.session_state:
    st.session_state.error_message = None

# --- Streamlit App UI ---
st.set_page_config(layout="wide")
st.title("🚶 Live Nearby Wikipedia Finder")

st.markdown(f"""
Press 'Start Tracking' to automatically check for nearby Wikipedia pages
every **{REFRESH_INTERVAL_SECONDS} seconds** using your current browser location.
You will likely need to grant location permissions in your browser.
""")
st.warning(f"""
🔴 **Warning:** This app uses a method (`time.sleep`) that may make the
UI unresponsive during the {REFRESH_INTERVAL_SECONDS}-second wait period between checks.
""")

# --- Control Buttons ---
col1, col2 = st.columns(2)
with col1:
    if st.button("🚀 Start Tracking", disabled=st.session_state.running, use_container_width=True):
        st.session_state.running = True
        st.session_state.status_message = "Initiating location tracking..."
        st.session_state.error_message = None # Clear previous errors
        st.session_state.last_results = [] # Clear previous results
        st.session_state.last_location = None
        st.experimental_rerun() # Start the loop immediately

with col2:
    if st.button("🛑 Stop Tracking", disabled=not st.session_state.running, use_container_width=True):
        st.session_state.running = False
        st.session_state.status_message = "Tracking stopped by user."
        st.session_state.error_message = None
        # Keep last results visible when stopped manually
        st.experimental_rerun() # Update UI immediately

# --- Display Status and Errors ---
if st.session_state.error_message:
    st.error(st.session_state.error_message)

st.info(st.session_state.status_message)


# --- Display Last Known Info ---
results_placeholder = st.container() # Create a container to hold results output
with results_placeholder:
    if st.session_state.last_location:
        try:
            loc = st.session_state.last_location
            ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(loc['timestamp']/1000))
            st.write(f"📍 Last known location: Lat={loc['latitude']:.5f}, Lon={loc['longitude']:.5f} (Accuracy: {loc.get('accuracy')}m) at {ts}")
        except Exception: # Catch potential errors if location format changes
             st.write(f"📍 Last known location data: {st.session_state.last_location}")


    if st.session_state.last_results:
        st.success(f"✅ You were near **{len(st.session_state.last_results)}** recognized Wikipedia page(s) at the last check:")
        for page in st.session_state.last_results:
            title = page.get('title', 'N/A')
            page_id = page.get('pageid', '#')
            distance = page.get('dist', 'N/A')
            wiki_url = f"https://en.wikipedia.org/?curid={page_id}"
            st.markdown(f"- **[{title}]({wiki_url})** (Distance: {distance:.1f}m)")
    elif st.session_state.running: # Only show "no results" if running and list is empty
        st.write("⚪ No pages found nearby at the last check.")


# --- Main Execution Loop ---
if st.session_state.running:
    # 1. Get Location using the custom component
    # This function call triggers the browser's request for location.
    # It returns None while waiting, or data/error when complete.
    location_data = streamlit_geolocation(key='geoloc') # Use a key to maintain state

    current_location = None
    if location_data and 'latitude' in location_data and 'longitude' in location_data:
        current_location = location_data
        st.session_state.last_location = current_location # Update last known location
        st.session_state.error_message = None # Clear any previous location error
        st.session_state.status_message = f"✅ Location acquired ({current_location['latitude']:.4f}, {current_location['longitude']:.4f}). Searching Wikipedia..."
        # We need to immediately rerun to show the updated status BEFORE the search
        # Use a temporary state variable to prevent infinite rerun loop just for status
        if not st.session_state.get('status_updated', False):
            st.session_state.status_updated = True
            st.experimental_rerun()

    elif location_data and 'error' in location_data:
        st.session_state.error_message = f"🚫 Geolocation Error: {location_data['error']['message']} (Code: {location_data['error']['code']}). Tracking stopped."
        st.session_state.status_message = "Tracking stopped due to location error."
        st.session_state.running = False
        st.session_state.status_updated = False # Reset flag
        st.experimental_rerun() # Stop the process and show error

    # Check if we are ready to search (location obtained and status was updated in previous run)
    if current_location and st.session_state.get('status_updated', False):
        # 2. Search Wikipedia if location is available
        lat = current_location['latitude']
        lon = current_location['longitude']
        nearby_pages = get_nearby_wikipedia_pages(lat, lon, SEARCH_RADIUS_METERS)

        if nearby_pages is not None: # Check for API errors (None) vs. no results ([])
            st.session_state.last_results = nearby_pages
            if not nearby_pages:
                st.session_state.status_message = f"⚪ No pages found within {SEARCH_RADIUS_METERS}m. Waiting {REFRESH_INTERVAL_SECONDS}s..."
            else:
                 st.session_state.status_message = f"✅ Found {len(nearby_pages)} page(s). Waiting {REFRESH_INTERVAL_SECONDS}s..."
        else:
            # Error occurred during API call, message already shown by function
             st.session_state.status_message = f"⚠️ Error searching Wikipedia. Waiting {REFRESH_INTERVAL_SECONDS}s..."
             st.session_state.last_results = [] # Clear results on error

        # 3. Wait and Schedule Rerun
        # Display countdown in a placeholder
        countdown_placeholder = st.empty()
        for i in range(REFRESH_INTERVAL_SECONDS, 0, -1):
            countdown_placeholder.write(f"⏳ Next check in {i} seconds...")
            time.sleep(1) # Blocking sleep! UI may freeze.
        countdown_placeholder.empty()

        st.session_state.status_updated = False # Reset status flag for next cycle
        st.experimental_rerun() # Trigger the next cycle

    elif not location_data and st.session_state.running:
         # Still waiting for location data from the browser component...
         st.session_state.status_message = "⏳ Waiting for browser location permission/data..."
         # Don't rerun or sleep here, let the component trigger the update when ready
         pass


# --- Add Footer ---
st.markdown("---")
st.caption(f"Using MediaWiki Geosearch API & `streamlit-geolocation`. Current check radius: {SEARCH_RADIUS_METERS}m. Refresh interval: {REFRESH_INTERVAL_SECONDS}s.")
