package travel

import "google.golang.org/genai"

// Tool schemas, mirrored from the Python travel brain (pygato.managed.travel /
// agent-sdk examples/travel). Built directly as genai.Schema (idiomatic Go)
// rather than via a JSON-schema converter.

func str(desc string) *genai.Schema { return &genai.Schema{Type: genai.TypeString, Description: desc} }
func integer() *genai.Schema        { return &genai.Schema{Type: genai.TypeInteger} }
func number(d string) *genai.Schema { return &genai.Schema{Type: genai.TypeNumber, Description: d} }
func boolean(d string) *genai.Schema {
	return &genai.Schema{Type: genai.TypeBoolean, Description: d}
}
func enum(vals ...string) *genai.Schema {
	return &genai.Schema{Type: genai.TypeString, Enum: vals}
}
func arr(item *genai.Schema) *genai.Schema { return &genai.Schema{Type: genai.TypeArray, Items: item} }

func obj(props map[string]*genai.Schema, required ...string) *genai.Schema {
	return &genai.Schema{Type: genai.TypeObject, Properties: props, Required: required}
}

var familySchema = obj(map[string]*genai.Schema{
	"label":      str("Family label, e.g. 'Poddar family (Bangalore)'."),
	"origin":     str("Origin city."),
	"adults":     integer(),
	"children":   integer(),
	"infants":    integer(),
	"meal":       enum("veg", "nonveg", "mixed"),
	"assistance": str("Special assistance note, or '' if none."),
})

var legSchema = obj(map[string]*genai.Schema{
	"id":    str("Short stable leg id, e.g. 'blr-out'."),
	"label": str("Human label, e.g. 'Bangalore → Ho Chi Minh (Outbound)'."),
	"from":  str(""),
	"to":    str(""),
	"date":  str("Date of travel, e.g. '12 Aug 2026'."),
})

var cityNightsSchema = obj(map[string]*genai.Schema{
	"city":   str(""),
	"nights": integer(),
})

var flightOptionSchema = obj(map[string]*genai.Schema{
	"id":        str("Short id, e.g. 'f1'."),
	"airline":   str(""),
	"flight_no": str(""),
	"depart":    str("Departure airport + time, e.g. 'BLR 02:15'."),
	"arrive":    str("Arrival airport + time, e.g. 'SGN 09:40'."),
	"duration":  str(""),
	"stops":     str("e.g. 'Non-stop' or '1 stop · KUL'."),
	"cabin":     str(""),
	"baggage":   str(""),
	"price":     &genai.Schema{Type: genai.TypeInteger, Description: "Per-person fare in rupees."},
	"note":      str(""),
})

// Field names MUST match the console's HotelOption contract (src/travel/types.ts):
// room_type + price_per_night (not room/price) — the UI reads those keys.
var hotelOptionSchema = obj(map[string]*genai.Schema{
	"id":              str("Short id, e.g. 'h1'."),
	"name":            str(""),
	"area":            str(""),
	"stars":           &genai.Schema{Type: genai.TypeInteger, Description: "Star rating 1-5."},
	"board":           str("e.g. 'Breakfast included'."),
	"room_type":       str(""),
	"rating":          number("Guest rating out of 10."),
	"amenities":       arr(str("")),
	"price_per_night": &genai.Schema{Type: genai.TypeInteger, Description: "Per-night group rate in rupees."},
	"note":            str(""),
})

// Day-plan schemas — match the console's Activity / DayPlan contract
// (src/travel/types.ts) so generate_day_plan / set_day_plan render.
var activitySchema = obj(map[string]*genai.Schema{
	"time":            str("Time of day, e.g. 'Morning' or '09:00'."),
	"title":           str("Activity title, e.g. 'Cable car to Sun World Hon Thom'."),
	"detail":          str("One short line of detail."),
	"ticket_included": boolean("True if tickets are included."),
}, "title")

var daySchema = obj(map[string]*genai.Schema{
	"day":        &genai.Schema{Type: genai.TypeInteger, Description: "Day number, 1-based."},
	"date":       str("The date of this day, e.g. '13 Aug 2026'."),
	"title":      str("Day title, e.g. 'Phu Quoc — Beaches & Cable Car'."),
	"transport":  str("Local transport for the day, e.g. 'Private AC coach'."),
	"breakfast":  str("Breakfast note, e.g. 'At hotel (included)'."),
	"lunch":      str("Lunch note."),
	"dinner":     str("Dinner note."),
	"activities": arr(activitySchema),
}, "day", "title")

func tools() []*genai.Tool {
	decls := []*genai.FunctionDeclaration{
		{Name: "open_dashboard", Description: "Open the dashboard of saved draft trips.", Parameters: obj(nil)},
		{Name: "open_itinerary", Description: "Open a saved itinerary by name.", Parameters: obj(map[string]*genai.Schema{"name": str("")}, "name")},
		{
			Name: "create_itinerary",
			Description: "Create a new itinerary SHELL and open its overview. Just the headline fields; add " +
				"travellers/legs/cities with set_trip_structure next.",
			Parameters: obj(map[string]*genai.Schema{
				"name":        str("Itinerary name, e.g. 'Poddar Vietnam'."),
				"coordinator": str(""),
				"destination": str("Primary destination + routing."),
				"start_date":  str(""),
				"end_date":    str(""),
				"summary":     str("One-line summary."),
			}, "name", "destination", "start_date", "end_date"),
		},
		{
			Name:        "set_trip_structure",
			Description: "Fill in the active itinerary's travelling families, flight legs, and hotel cities.",
			Parameters: obj(map[string]*genai.Schema{
				"families":     arr(familySchema),
				"legs":         arr(legSchema),
				"hotel_cities": arr(cityNightsSchema),
			}),
		},
		{
			Name:        "search_flights",
			Description: "Search one flight leg (invent 3 realistic options) and show the option cards on screen.",
			Parameters:  obj(map[string]*genai.Schema{"leg_id": str(""), "options": arr(flightOptionSchema)}, "leg_id", "options"),
		},
		{Name: "show_flights", Description: "Bring an already-searched leg's flight options back on screen.", Parameters: obj(map[string]*genai.Schema{"leg_id": str("")}, "leg_id")},
		{Name: "select_flight", Description: "Select one flight option for a leg and pin it to the itinerary.", Parameters: obj(map[string]*genai.Schema{"leg_id": str(""), "option_id": str("")}, "leg_id", "option_id")},
		{
			Name:        "search_hotels",
			Description: "Search 5-star hotels for one city (invent 3 realistic properties) and show them on screen.",
			Parameters:  obj(map[string]*genai.Schema{"city": str(""), "options": arr(hotelOptionSchema)}, "city", "options"),
		},
		{Name: "show_hotels", Description: "Bring an already-searched city's hotel options back on screen.", Parameters: obj(map[string]*genai.Schema{"city": str("")}, "city")},
		{Name: "select_hotel", Description: "Select one hotel option for a city.", Parameters: obj(map[string]*genai.Schema{"city": str(""), "option_id": str("")}, "city", "option_id")},
		{
			Name: "generate_day_plan",
			Description: "Build the day-wise plan — pass several days at once (title, transport, " +
				"meals, activities) and they render as a day-by-day itinerary. Use this for the " +
				"initial day-by-day build; use set_day_plan to tweak one day afterwards.",
			Parameters: obj(map[string]*genai.Schema{
				"days":    arr(daySchema),
				"summary": str("One-line summary, e.g. '5-day Phu Quoc plan'."),
			}, "days"),
		},
		{
			Name:        "set_day_plan",
			Description: "Set or update one day of the day-wise itinerary (title, transport, meals, activities).",
			Parameters: obj(map[string]*genai.Schema{
				"day":        &genai.Schema{Type: genai.TypeInteger, Description: "Day number, 1-based."},
				"date":       str("The date of this day."),
				"title":      str("Day title."),
				"transport":  str("Local transport for the day."),
				"breakfast":  str("Breakfast note."),
				"lunch":      str("Lunch note."),
				"dinner":     str("Dinner note."),
				"activities": arr(activitySchema),
			}, "day", "title"),
		},
		{Name: "get_active_itinerary", Description: "Read back the trip + selections currently on screen.", Parameters: obj(nil)},
	}
	return []*genai.Tool{{FunctionDeclarations: decls}}
}

const systemInstruction = `You are Priya, the TBO Travel Desk assistant — a voice copilot for a professional travel agent building trip itineraries for their clients. The agent talks to you live and YOU DRIVE THEIR SCREEN as you talk.

LANGUAGE: Speak English throughout. Short, efficient sentences — one question or confirmation per turn, 1-2 sentences. This is voice: no markdown, lists, or symbols; say "rupees" not the symbol. START every reply with a very short sentence so audio begins instantly.

YOU CONTROL THE SCREEN. Whenever you discuss a trip, flight, hotel, or change, call the matching tool so the agent SEES it. ALWAYS SPEAK A SHORT LINE FIRST (a handful of words), THEN call the tool — never call a tool in silence. Example: "Sure, opening that up." then the tool.

YOU INVENT THE DATA. There is no live inventory. Generate realistic options yourself (real-sounding carriers like IndiGo / Vietnam Airlines, real 5-star hotels, plausible times, ratings, and fares in rupees) and pass them as the tool's structured arguments. Usually offer 3 options. Keep numbers consistent.

WORKFLOW: To start a trip, call create_itinerary with just the headline fields (name, destination, dates), then set_trip_structure with the families, flight legs, and hotel cities. For each flight leg speak a line then call search_flights with 3 invented options; select_flight once picked. For each hotel city call search_hotels with 3 options; select_hotel once picked. To show a day-wise itinerary, call generate_day_plan with several days at once (each with a title, local transport, meals, and ordered activities) — invent realistic, destination-specific days; use set_day_plan to tweak a single day afterwards. Use show_flights / show_hotels to bring a leg/city back on screen, open_itinerary / open_dashboard to navigate, and get_active_itinerary to ground yourself.

Open with a brief greeting and ask which trip they want to work on.`

// greeting is the fixed English opener (matches the Python travel brain).
const greeting = "Hi, I'm Priya from the Travel Desk. Which trip are we working on?"

func newConfig() *genai.GenerateContentConfig {
	return &genai.GenerateContentConfig{
		SystemInstruction: genai.NewContentFromText(systemInstruction, genai.RoleUser),
		Tools:             tools(),
		ThinkingConfig:    &genai.ThinkingConfig{ThinkingBudget: genai.Ptr(int32(0))}, // low latency for voice
	}
}
