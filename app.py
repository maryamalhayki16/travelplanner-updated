import streamlit as st
import requests
from datetime import timedelta

BASE_URL = "https://travelplanner-updated.onrender.com"

st.markdown(
    """
    <style>
    .stMarkdown p {
        margin-bottom: 0.2rem;
        line-height: 1.2;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown("""
<style>
    .block-container {
        max-width: 1100px;
        padding-top: 2rem;
    }
    </style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="AI Travel Planner", page_icon="✈️", layout="centered")

st.title("🗺️ Travel Planner")
st.markdown(
    "##### Sick of planning vacations? Create your perfect itinerary with AI!\n"
    "Get personalized recommendations for ***flights, hotels, and activities***"
)

if "results" not in st.session_state:
    st.session_state.results = None


# user inputs
with st.container(border=True):
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        st.markdown("#### 🎯 Preferences")
    with col2:
        include_flights = st.checkbox("Include Flights ✈️")

    with col3: 
        include_hotels = st.checkbox("Include Hotels 🏨")

    destinations = st.text_input("Destinations (comma separated)", placeholder='e.g. Rome, Milan')
    destinations_list = [d.strip() for d in destinations.split(",") if d.strip()]

    budget = st.number_input("Budget (dollars)", min_value=700)

    trip_duration = st.slider("Trip Duration (days)", 1, 30, 5)

    trip_type = st.selectbox(
        "Trip Type",
        ["Solo Trip", "Couple Getaway", "Family Vacation", "Friends Adventure"]
    )

    vibe = st.multiselect(
        "Interests",
        ["Exploring", "Historical", "Chill", "Adventure", "Sightseeing", "Nature"]
    )


if include_flights and include_hotels:
    with st.container(border=True):
        col1, col2= st.columns(2)
        with col1: 
            st.markdown("#### ✈️ Flight Details")
            source = st.text_input("From (Airport Code)", placeholder='e.g. BAH')
            arrival = st.text_input("To (Airport Code)", placeholder='e.g. FCO')
            outbound_date = st.date_input("Outbound Date", min_value="today")
        with col2:
            st.markdown("#### 🏨 Hotel Details")
            hotel_location = st.text_input("Hotel Location", placeholder='e.g. Rome')
            check_in = st.date_input("Check-in Date", min_value="today")
elif include_flights:
    with st.container(border=True):
        st.markdown("#### ✈️ Flight Details")
        source = st.text_input("From (Airport Code)", placeholder='e.g. BAH')
        arrival = st.text_input("To (Airport Code)", placeholder='e.g. FCO')
        outbound_date = st.date_input("Outbound Date", min_value="today")
elif include_hotels:
    with st.container(border=True):
        st.markdown("#### 🏨 Hotel Details")
        hotel_location = st.text_input("Hotel Location", placeholder='e.g. Rome')
        check_in = st.date_input("Check-in Date", min_value="today")


def render_flights(flights):
    cols = st.columns(2)

    for i, flight in enumerate(flights):
        with cols[i % 2]:
            with st.container(border=True):

                segments = flight.get("segments", [])

                if segments:
                    origin_name = segments[0].get("from_name", "N/A")
                    destination_name = segments[-1].get("to_name", "N/A")
                    st.markdown(f"#### ✈︎ {origin_name} → {destination_name}")

                price = flight.get("price", "N/A")
                duration = flight.get("total_duration", "N/A")

                for seg in segments[:2]:
                    st.markdown(
                        f"🛫 **Departure:** {seg.get('from_name')} ({seg.get('from_id')}) at {seg.get('departure_time')}"
                    )
                    st.markdown(
                        f"🛬 **Arrival:** {seg.get('to_name')} ({seg.get('to_id')}) at {seg.get('arrival_time')}"
                    )
                    st.markdown(
                        f"🎫 **Airline:** {seg.get('airline')} ({seg.get('travel_class')})"
                    )

                st.markdown(f"⏱️ **Duration:** {duration} min")
                st.markdown(f"💰 **Price:** ${price}")

def render_hotels(hotels, cols_num=3):
    cols = st.columns(cols_num)

    for i, hotel in enumerate(hotels):
        with cols[i % cols_num]:
            with st.container(border=True):

                st.markdown(f"#### **🏨 {hotel.get('name', 'N/A')}**")

                price = hotel.get("price_per_night") or "N/A"
                rating = hotel.get("rating") or "N/A"
                Type = hotel.get("Type") or "N/A"

                st.markdown(f"📍 **Type:** {Type}")
                st.markdown(f"💰 **Price**: ${price} a Night")
                st.markdown(f"⭐ **Rating:** {rating}")

                amenities = hotel.get("amenities", [])

                if amenities:
                    st.markdown("🛎️ **Available Amenities:** " + ", ".join(amenities[:4]))
                else:
                    st.caption("No amenities listed")



if st.button("🚀 Generate My Trip"):

    if not destinations_list:
        st.error("Please enter at least one destination.")
        st.stop()

    if include_flights and (not source or not arrival or not outbound_date):
        st.error("Flight details required.")
        st.stop()

    if include_hotels and not check_in:
        st.error("Check-in date required for hotels.")
        st.stop()

    with st.spinner("Planning your trip..."):

        flight_payload = None
        if include_flights:
            flight_payload = {
                "source": source,
                "destination": arrival,
                "outbound_date": str(outbound_date),
                "trip_duration": trip_duration
            }

        hotel_payload = None
        if include_hotels:
            hotel_payload = {
                "location": hotel_location if hotel_location else destinations_list[0],
                "check_in_date": str(check_in),
                "trip_duration": trip_duration
            }

        itinerary_payload = {
            "destinations": destinations_list,
            "check_in_date": str(check_in) if include_hotels else None,
            "trip_duration": trip_duration,
            "budget": budget,
            "interests": vibe,
            "trip_type": trip_type,
            "include_flights": include_flights,
            "include_hotels": include_hotels
        }

        try:
            itinerary_res = requests.post(
                f"{BASE_URL}/generate/itinerary",
                json={
                    "itinerary_request": itinerary_payload,
                    "flight_request": flight_payload,
                    "hotel_request": hotel_payload
                }
            ).json()

            st.session_state.results = itinerary_res

            st.toast("Trip generated successfully ✈️")

        except Exception as e:
            st.error(f"Something went wrong: {e}")


if st.session_state.results:

    results = st.session_state.results

    tab_labels = []

    if include_flights:
        tab_labels.append("✈️ All Flights")
        tab_labels.append("⭐ Recommended Flights")

    if include_hotels:
        tab_labels.append("🏨 All Hotels")
        tab_labels.append("⭐ Recommended Hotels")
    
    tab_labels.append("🗺️ Itinerary")
    tabs = st.tabs(tab_labels)

    i = 0

    if include_flights:
        with tabs[i]:
            render_flights(results.get("flights", []))
        i += 1

        with tabs[i]:
            render_flights(results.get("top_flights", []))
        i += 1

    if include_hotels:
        with tabs[i]:
            render_hotels(results.get("hotels", []))
        i += 1

        with tabs[i]:
            render_hotels(results.get("top_hotels", []))
        i += 1

    with tabs[i]:
        itinerary = results.get("itinerary", "")
        st.code(itinerary, language="markdown")
        st.download_button(
                "📥 Download Itinerary",
                itinerary,
                file_name=f"{destinations} itinerary.txt",
                mime="text/plain"
            )
