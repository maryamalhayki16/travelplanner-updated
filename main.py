import logging
import os
from datetime import datetime, timedelta
from functools import lru_cache
import asyncio
from typing import List, Optional
from dotenv import load_dotenv
from pydantic import BaseModel
from crewai import Agent, Task, Crew, Process, LLM
from crewai_tools import EXASearchTool
from fastapi import FastAPI, HTTPException
import serpapi

load_dotenv()

SERPAPI_API_KEY = os.getenv('SERPAPI_API_KEY')
client = serpapi.Client(api_key=SERPAPI_API_KEY)

exa_tool = EXASearchTool()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title='Travel Planner', version='1.0')

GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
@lru_cache(maxsize=1)
def initialize_llm(): # initialize and cache the llm, using claude
    return LLM(
    model="gemini-2.5-flash",
    provider="google",
    api_key=GOOGLE_API_KEY
    )

# pydantic models
class FlightRequest(BaseModel):
    source: str
    destination: str
    outbound_date: str
    trip_duration: int

class HotelRequest(BaseModel):
    location: str
    check_in_date: str
    trip_duration: int

class FlightInfo(BaseModel):
    segments: list
    total_duration: Optional[int]
    price: Optional[float]

class HotelInfo(BaseModel):
    name: str
    Type: str | None = None
    price_per_night: float | None = None
    total_price: float | None = None
    rating: float | None = None
    amenities: list | None = None

class ItineraryRequest(BaseModel):
    destinations: List[str]
    check_in_date: Optional[str] = None
    check_out_date: Optional[str] = None
    trip_duration: int

    budget: float
    interests: List[str]
    trip_type: str

    include_flights: bool = False
    include_hotels: bool = False

class AIResponse(BaseModel):
    flights: List[FlightInfo] = []
    hotels: List[HotelInfo] = []
    top_flights: List[FlightInfo] = []
    top_hotels: List[HotelInfo] = []
    itinerary: str = ""

# calculate trip dates
def resolve_trip_dates(check_in_date, check_out_date, trip_duration):
    try:
        if check_in_date and trip_duration:
            check_in = datetime.strptime(check_in_date, '%Y-%m-%d')
            check_out = check_in + timedelta(days=trip_duration)
            return check_in, check_out, trip_duration

        if check_in_date and check_out_date:
            check_in = datetime.strptime(check_in_date, '%Y-%m-%d')
            check_out = datetime.strptime(check_out_date, '%Y-%m-%d')
            days = (check_out - check_in).days
            return check_in, check_out, days

        today = datetime.today()
        return today, today + timedelta(days=5), 5

    except Exception as e:
        logger.warning(f"Date error: {e}")
        today = datetime.today()
        return today, today + timedelta(days=5), 5

# get top 3 best flights
def get_top_flights(formatted_flights, top_n=3):
    return sorted(
        formatted_flights,
        key=lambda x: (
            x.price if x.price else float('inf'),
            x.total_duration if x.total_duration else float('inf')
        )
    )[:top_n]
# get top 3 best hotels
def get_top_hotels(formatted_hotels, top_n=3):
    return sorted(
        formatted_hotels,
        key=lambda x: (
            -(x.rating if x.rating else 0),
            x.price_per_night if x.price_per_night else float('inf')
        )
    )[:top_n]

# global search function
async def run_search(params):
    try:
        return await asyncio.to_thread(lambda: client.search(params).as_dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# search for flights
async def search_flights(flight_request: FlightRequest):
    return_date = (
        datetime.strptime(flight_request.outbound_date, "%Y-%m-%d") +
        timedelta(days=flight_request.trip_duration)
    ).strftime("%Y-%m-%d")

    params = {
        "engine": "google_flights",
        "departure_id": flight_request.source.upper(),
        "arrival_id": flight_request.destination.upper(),
        "outbound_date": flight_request.outbound_date,
        "return_date": return_date
    }

    return await run_search(params)

# search for hotels
async def search_hotels(hotel_request: HotelRequest):
    check_out_date = (
        datetime.strptime(hotel_request.check_in_date, "%Y-%m-%d") +
        timedelta(days=hotel_request.trip_duration)
    ).strftime("%Y-%m-%d")

    params = {
        "engine": "google_hotels",
        "q": hotel_request.location,
        "check_in_date": hotel_request.check_in_date,
        "check_out_date": check_out_date
    }

    return await run_search(params)

# handle data
def extract_flights(flights_raw):
    formatted = []
    for key in ['best_flights', 'other_flights']:
        for item in flights_raw.get(key, []):
            segments = []
            for f in item.get('flights', []):
                segments.append({
                    'from_id': f.get('departure_airport', {}).get('id'),
                    'from_name': f.get('departure_airport', {}).get('name'),
                    'to_id': f.get('arrival_airport', {}).get('id'),
                    'to_name': f.get('arrival_airport', {}).get('name'),
                    'departure_time': f.get('departure_airport', {}).get('time'),
                    'arrival_time': f.get('arrival_airport', {}).get('time'),
                    'airline': f.get('airline'),
                    'travel_class': f.get('travel_class')
                })

            formatted.append({
                'segments': segments,
                'total_duration': item.get('total_duration'),
                'price': item.get('price')
            })
    return formatted

def extract_hotels(hotels_raw):
    formatted = []
    for h in hotels_raw.get("properties", [])[:30]:
        formatted.append({
            "name": h.get("name"),
            "Type": h.get("type"),
            "price_per_night": h.get("rate_per_night", {}).get("extracted_lowest"),
            "total_price": h.get("total_rate", {}).get("extracted_lowest"),
            "rating": h.get("overall_rating"),
            "amenities": (h.get("amenities") or [])[:5]
        })
    return formatted

# generate full itinerary
async def generate_itinerary(destinations, flights, hotels,
                             check_in_date, check_out_date,
                             trip_duration, budget, interests, trip_type):

    check_in, check_out, days = resolve_trip_dates(
        check_in_date, check_out_date, trip_duration
    )

    llm = initialize_llm()

    agent = Agent(
        role="Travel Itinerary Planner",
        goal="Create a personalized, realistic travel itinerary using real-world activities",
        backstory="""
        You are an expert travel planner who builds detailed itineraries.
        You ALWAYS use web search to find real attractions, restaurants, and experiences.
        You optimize plans based on budget, vibe, and trip type.
        """,
        tools=[exa_tool],
        llm=llm,
        verbose=True
    )

    task = Task(
        description=f"""
        Create a {days}-day itinerary.

        Destinations: {", ".join(destinations)}
        Budget: {budget}
        Trip Type: {trip_type}
        Interests: {interests}

        Flights: {flights}
        Hotels: {hotels}

        Dates: {check_in} to {check_out}

        Include daily plans, food, activities, and logistics.
        """,
        agent=agent,
        expected_output="""A well-structured, visually appealing itinerary in markdown format, including flight, hotel, 
        and day-wise breakdown with emojis, headers, and bullet points."""
        )

    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential)

    result = await asyncio.to_thread(crew.kickoff)
    return str(result)

# FastAPI endpoints
@app.post("/search_flights/", response_model=AIResponse)
async def get_flights(flight_request: FlightRequest):
    raw = await search_flights(flight_request)
    flights = [FlightInfo(**f) for f in extract_flights(raw)]
    return AIResponse(
        flights=flights,
        top_flights=get_top_flights(flights)
    )

@app.post("/search_hotels/", response_model=AIResponse)
async def get_hotels(hotel_request: HotelRequest):

    raw = await search_hotels(hotel_request)
    hotels = [HotelInfo(**h) for h in extract_hotels(raw)]

    return AIResponse(
        hotels=hotels,
        top_hotels=get_top_hotels(hotels)
    )

@app.post("/generate/itinerary", response_model=AIResponse)
async def get_itinerary(itinerary_request: ItineraryRequest,
                        flight_request: Optional[FlightRequest] = None,
                        hotel_request: Optional[HotelRequest] = None):

    flights, hotels, top_flights, top_hotels = [], [], [], []

    if itinerary_request.include_flights and flight_request:
        raw_flights = await search_flights(flight_request)
        flights = [FlightInfo(**f) for f in extract_flights(raw_flights)]
        top_flights = get_top_flights(flights)

    if itinerary_request.include_hotels and hotel_request:
        raw_hotels = await search_hotels(hotel_request)
        hotels = [HotelInfo(**h) for h in extract_hotels(raw_hotels)]
        top_hotels = get_top_hotels(hotels)

    itinerary = await generate_itinerary(
        itinerary_request.destinations,
        top_flights,
        top_hotels,
        itinerary_request.check_in_date,
        itinerary_request.check_out_date,
        itinerary_request.trip_duration,
        itinerary_request.budget,
        itinerary_request.interests,
        itinerary_request.trip_type
    )

    return AIResponse(flights=flights, hotels=hotels, top_flights=top_flights, 
                    top_hotels=top_hotels, itinerary=itinerary)