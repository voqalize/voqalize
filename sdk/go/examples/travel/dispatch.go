package travel

import (
	"fmt"

	"github.com/voqalize/voqalize/sdk/go/brain"
)

// dispatchTool mutates brain state and drives the browser via in.Action(...) —
// which the SDK relays as the RTVI ui_command the /travel console renders. The
// returned string is fed back to the model as the tool result. Payloads mirror
// the Python travel brain so the same console screens drive.
func (b *TravelBrain) dispatchTool(in *brain.Interaction, name string, args map[string]any) string {
	switch name {
	case "open_dashboard":
		in.Action("open_dashboard", nil)
		return "dashboard open"

	case "open_itinerary":
		in.Action("open_itinerary", map[string]any{"name": getStr(args, "name")})
		return "opened " + getStr(args, "name")

	case "create_itinerary":
		it := map[string]any{
			"name":         getStr(args, "name"),
			"coordinator":  getStr(args, "coordinator"),
			"destination":  getStr(args, "destination"),
			"start_date":   getStr(args, "start_date"),
			"end_date":     getStr(args, "end_date"),
			"summary":      getStr(args, "summary"),
			"families":     []any{},
			"legs":         []any{},
			"hotel_cities": []any{},
		}
		b.itinerary = it
		in.Action("create_itinerary", map[string]any{"itinerary": it})
		return fmt.Sprintf("created '%s'", getStr(args, "name"))

	case "set_trip_structure":
		families := asSlice(args["families"])
		legs := normalizeIDs(args["legs"], "leg")
		cities := asSlice(args["hotel_cities"])
		if b.itinerary != nil {
			b.itinerary["families"] = families
			b.itinerary["legs"] = legs
			b.itinerary["hotel_cities"] = cities
		}
		in.Action("set_trip_structure", map[string]any{"families": families, "legs": legs, "hotel_cities": cities})
		return fmt.Sprintf("structure set (%d families, %d legs)", len(families), len(legs))

	case "search_flights":
		legID := getStr(args, "leg_id")
		options := normalizeIDs(args["options"], "f")
		b.flights[legID] = options
		in.Action("search_flights", map[string]any{"leg_id": legID, "options": options})
		return fmt.Sprintf("showing %d flights for %s", len(options), legID)

	case "show_flights":
		in.Action("show_flights", map[string]any{"leg_id": getStr(args, "leg_id")})
		return "shown"

	case "select_flight":
		b.selected[fmt.Sprintf("flight:%s", getStr(args, "leg_id"))] = getStr(args, "option_id")
		in.Action("select_flight", map[string]any{"leg_id": getStr(args, "leg_id"), "option_id": getStr(args, "option_id")})
		return "flight selected"

	case "search_hotels":
		city := getStr(args, "city")
		options := normalizeIDs(args["options"], "h")
		b.hotels[city] = options
		in.Action("search_hotels", map[string]any{"city": city, "options": options})
		return fmt.Sprintf("showing %d hotels in %s", len(options), city)

	case "show_hotels":
		in.Action("show_hotels", map[string]any{"city": getStr(args, "city")})
		return "shown"

	case "select_hotel":
		b.selected[fmt.Sprintf("hotel:%s", getStr(args, "city"))] = getStr(args, "option_id")
		in.Action("select_hotel", map[string]any{"city": getStr(args, "city"), "option_id": getStr(args, "option_id")})
		return "hotel selected"

	case "generate_day_plan":
		days := asSlice(args["days"])
		summary := getStr(args, "summary")
		in.Action("generate_day_plan", map[string]any{"days": days, "summary": summary})
		return fmt.Sprintf("building a %d-day plan", len(days))

	case "set_day_plan":
		// The args map IS the day plan (day, date, title, transport, meals,
		// activities) — the console reads it under the `plan` key.
		in.Action("set_day_plan", map[string]any{"plan": args})
		return "day updated"

	case "get_active_itinerary":
		// Prefer the live browser snapshot (reflects hand edits); else our own.
		if len(b.browserState) > 0 {
			return fmt.Sprintf("%v", b.browserState)
		}
		if b.itinerary != nil {
			return fmt.Sprintf("%v", map[string]any{"itinerary": b.itinerary, "selected": b.selected})
		}
		return "no itinerary open"
	}
	return "unknown tool"
}

func getStr(args map[string]any, key string) string {
	if v, ok := args[key].(string); ok {
		return v
	}
	return ""
}

func asSlice(v any) []any {
	if s, ok := v.([]any); ok {
		return s
	}
	return []any{}
}

// normalizeIDs ensures every option/leg dict has a stable string id.
func normalizeIDs(v any, prefix string) []any {
	items := asSlice(v)
	out := make([]any, 0, len(items))
	for i, raw := range items {
		m, ok := raw.(map[string]any)
		if !ok {
			m = map[string]any{}
		}
		if id, _ := m["id"].(string); id == "" {
			m["id"] = fmt.Sprintf("%s%d", prefix, i+1)
		}
		out = append(out, m)
	}
	return out
}
