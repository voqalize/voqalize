# What each section shows on screen

Each section below is what the visitor sees beside Tanvi when she opens it. Names, prices and numbers inside the drawn apps are examples, not real customers.

## shift: Why voice, why now

There is no visible headline. Every scene carries the small label "Why voice, why now". It is a four-scene carousel with arrows, dots and swipe. It moves to the next scene on its own when the motion ends, and scene 4 holds for six seconds before going back to scene 1.

- Scene 1. Heading: "We talk to our tech all day." Text: "We dictate messages and notes, ask the car for music, and tell the phone who to call." Four spoken lines appear one by one, each with a small voice wave and a label: "Reply to Sam: running ten minutes late." (Messages), "Play something calm." (Car), "Call Mom." (Phone), "Note to self: send the deck by Friday." (Notes).
- Scene 2. Heading: "Software still wants clicks." Text: "For forty years we learned the computer's language of menus, forms and gestures. It's time it learned ours." The gesture words appear in turn: Click. Scroll. Pinch. Tap. Type. Swipe. Shake to undo. The last one shakes.
- Scene 3. Heading: "What if every app listened?" Text: "One sentence, and a change of mind halfway. The app keeps up." A phone shows a flight app for Fri, Oct 16, NYC to Austin. The person says "Book a Friday morning flight to Austin." The agent says "Here are your flights." Three flights appear: 7:10 AM $214, 8:05 AM $189, 11:40 AM $236. The person says "Pick the one around 8 AM.", and the 8:05 is picked. The person says "Aisle seat, please.", and a seat map shows 14C, aisle. Then "Actually, make it a window.", and it changes to 14A, window. Last comes a green tick, "Booking confirmed, Fri, Oct 16, 8:05 AM, NYC to Austin, seat 14A", and the agent says "Done. Seat 14A on the 8:05."
- Scene 4. Large heading: "Voqalize brings a voice-first interface to the apps you already have." Text: "Your customers talk to it the way they talk to a person, and change their minds halfway. It understands what they ask and does it." Nine animated voice bars.

Things on screen she can point to:
- The flight scene, where the visitor changes their mind from an aisle seat to a window and the app keeps up.
- The gesture list ending in "Shake to undo", which shakes.
- The four everyday voice lines in scene 1, such as "Call Mom."

## action: How it works

Label "How it works". Headline: "One sentence, there and back." Lede: "Voqalize is voice AI infrastructure that sits between your app and the brain behind it."

A diagram with three frames from left to right, joined by wires. Each wire has an out lane and a back lane, and the lane in use turns vermilion and carries a packet.
1. "Jewelry store app" (Your app): a store called AURUM with a search bar, "All jewelry", 48 results and six products: Silver hoops $220, Leaf drops $640, Pearl pendant $540, Ruby hoops $1,240, Jade studs $720, Gold ring $890. The shopper says "Gold earrings under $800 that go with a green dress." The voice travels on the "Voice" lane.
2. "Voqalize" (Voice infrastructure, in between). In the Listening panel, a waveform with noise at both ends gets these tags: Noise removed, Split into words, They finished, Speech to text. Then the text types out: "gold earrings under $800 that go with a green dress". "Clean text" goes to the brain.
3. "Your brain" (The jewelry store's backend, "Hosted by us, or by you"). It first shows "Waiting for the shopper", then "Heard" with the sentence. Three tool calls follow: catalog.search(earrings, gold, max 800), which finds 14; style.match("green dress"), with 2 matches; and inventory.check(2 items), in stock. The picks are Leaf drops $640 and Jade studs $720. Then Say: "These two go with green." and Do: set_filters(earrings, gold, under 800, green).
Back in Voqalize, the Speaking panel shows "These two go with green." as a waveform tagged Text to speech and Lips in sync. The "Speech and actions" lane carries a wave and a UI chip. In the store, the search fills "earrings", the chips Earrings, Gold, Under $800 and Goes with green appear, 48 results become 2 results, the two matches are ringed, and the reply "These two go with green." appears.

The numbered steps below, which are hidden on phones:
1. You speak. A shopper asks the store for gold earrings under $800 that go with a green dress.
2. Voqalize listens. It removes the noise, hears when they have finished and turns the voice into clean text.
3. Your brain decides. Your backend searches its own catalog, then returns what to say and what to do.
4. It speaks and acts. The character says the answer while the app sets the filters.

Things on screen she can point to:
- The result count dropping from 48 results to 2.
- The brain's Say and Do output: the words go to speech, and set_filters goes to the app.
- The "They finished" tag, which shows the moment Voqalize hears the end of the turn.
- "Hosted by us, or by you" on the brain frame.

## ways: Two ways to integrate

Label "Getting started". Headline: "Two ways to integrate." Lede: "Let us run the AI for you, or connect the agent you already have. Either way, nobody rebuilds the app."

Above the tabs is the line "Either way, Voqalize runs", followed by these tags: WebRTC, Speech-to-text, Text-to-speech, Turn-taking, Interruptions, Characters, Recording.

There are two tabs that advance on their own. Each step is a button, and a "Go to Console" button sits under the steps.

Tab 1, Plug & Play. The drawing is a browser window.
1. "Give us your web address." The field types https://yourstore.com.
2. "We learn your website. Every page becomes a knowledge base." The knowledge base shelves fill in: Products 96 pages, Policies 12 pages, Sizes and care 9 pages, Store and contact 7 pages.
3. "Pick a character, or create your own." Six faces and a plus tile appear, and Tess is picked.
4. "Paste one script tag." The pane shows "Paste this before </body>" and a script tag for widget.js with data-agent="yourstore".
5. "You are live." A drawn store page appears with Tess saying "Hi, welcome to Your Store. What brings you in today?"
The facts below read: "Live in under 5 minutes.", "You pay per conversation minute." and "Update what it knows any time, through our MCP."

Tab 2, Developer integration. The drawing is a dark terminal called your-app.
1. "Install the SDKs. In your frontend and your backend." The terminal types `pip install voqalize-agent-sdk` (backend) and `npm install @voqalize/client-transport` (frontend).
2. "Connect your backend. Two ways to dial in: we call your endpoint, or your backend calls us." The two options light up in turn. "We call you" reads "Voqalize dials your WebSocket", and "You call us" reads "Your backend connects out to Voqalize, no open port".
3. "Your brain decides. With your APIs, your database and your tools." Python code types out: from voqalize.sdk import Brain, serve; class YourAgent(Brain) with async def respond, and the comment "your agent, your APIs, your database".
4. "You are live." A dark store page appears with Tess saying "Your app is talking."
The facts below read: "SDKs for the stacks you already use.", "Your codebase and your agent stay as they are." and a "Read the docs" link.

Things on screen she can point to:
- The single script tag in Plug & Play.
- The knowledge base shelves counting the pages learned from the site.
- The two ways to dial in, where "You call us" needs no open port.
- Tess greeting visitors on the live store.

## handled: Why voice is hard to build

Label "Why voice is hard to build". Headline: "The hard part of voice is listening." Lede: "Put a voice on an app you already have, and this is the list your team writes on the whiteboard."

It is a whiteboard with "YOUR APP" in the middle. In about three seconds, seven notes slam on around it, each with a vermilion marker stroke and arrows into the app. Small scrawls appear too: VAD, barge-in, jitter, codecs, TURN servers, Safari??, voices?, retries, lip sync, and a sticky note reading servers?. The "Team's estimate" climbs from 2 weeks to 6 weeks to 3 months, circled. Then each note is highlighted in turn while its reason appears in a side panel titled "Why each one is hard". These are the seven:
1. When did they stop talking? A pause can be a full stop or someone thinking. Answer too early and you cut them off. Too late and it feels broken.
2. They cut in. People interrupt. The voice has to stop on the word, and the agent has to know what was actually heard.
3. Under a second. People take turns with gaps of about 200 milliseconds, across the ten languages studied (PNAS, 2009). Every step from the microphone to the reply has to fit.
4. Noise and echo. A television, traffic, a dog, and the agent's own voice coming back through the speaker. Only the person should get through.
5. Accents and languages. Names, numbers, addresses, sometimes two languages in one sentence.
6. Browsers and networks. Microphones, WebRTC, Safari and a weak connection on a train. The audio has to arrive anyway.
7. A voice and a face. Speech that starts while the reply is still being written, and lips that match it.
Then an eraser wipes the board, "+" and the Voqalize logo appear beside YOUR APP, the seven notes come back ticked, and the board reads "All seven, handled." The last panel line is: "Add Voqalize and all seven are handled. Your team keeps building the app. We take care of the listening." During a live call, the line "Try it now. Interrupt me while I am talking." shows below.

Things on screen she can point to:
- The team's estimate climbing to 3 months.
- The 200 millisecond turn-taking gap.
- "Try it now. Interrupt me while I am talking.", which invites the visitor to interrupt her.

## worlds: Use cases

Label "Use cases". Headline: "Same app. Now it listens." Lede: "Any screen people struggle with is a place for a voice. Six everyday ones."

There are six tabs that advance on their own. Each tab shows a drawn phone app beside the quote, under "They say", and a "Today" versus "With Voqalize" line.
1. Jewelry store, app Aurum Jewels. The person says "Gold earrings under $800 that go with a green dress." A scrolling shop grid narrows to "2 of 214 pieces" with the chips Earrings, Gold, Under $800 and Green dress. Gold hoops $640 and Gold leaf drops $720 are marked "Goes with green". The reply is "These two go with green. The hoops are $640." Today: "Seven filters and some guessing."
2. Banking, app Tidewell Bank. The person says "I want to buy a car. How much loan would I need, and which offer is cheapest?" The home screen ("Good morning, Maya", checking $12,400) slides to a Car loan view: car price $26,000, less $8,000 down, so the loan needed counts up to $18,000. Three offers follow, cheapest first: Lakeside Credit Union 5.9% APR $347/mo (marked Cheapest), Northline Bank 6.8% $355/mo, and Dealer financing 7.9% $364/mo. The reply is "About $18,000. The credit union offer is the cheapest." Today: "Four screens and a spreadsheet."
3. Long forms, a Change of address form. The person says "My address is 14 Elm Street, apartment 3B, Austin, 78701." The form scrolls to New address and fills the street, the apartment and the city. The state list opens and lands on Texas, and then the ZIP fills. The reply is "Got it. Austin, Texas?" Today: "Fourteen fields and a list of fifty states."
4. Contracts, a Supply agreement. The person says "Which clauses here would worry a buyer?" The document jumps from Page 3 to Page 18 of 40 and marks clauses 7.2 Auto-renewal, 9.1 Liability cap (with one changed line tinted) and 12.4 Exclusivity. The reply is "Three. I have marked each one." Today: "Forty pages and a highlighter."
5. Cab booking, app Ride. The person says "Get me a ride to the airport. Something bigger, we have four bags." The destination fills with Airport, Departures, and a map draws the route (22 min, 14 mi). Three rides appear: Go $28, Comfort $34 and XL $46 (6 seats, 4+ bags), and XL is picked. The reply is "An XL is six minutes away. Book it?"
6. Food delivery, app Order in. The person says "Reorder Friday's pizza, but a large, and no olives." Friday's Margherita opens, the size slides to Large ($14 to $18), the olives fly off, and "Place order, $18" appears for the same address, 14 Elm St. The reply is "Large, no olives, same address. Place it?"

Things on screen she can point to:
- The state list landing on Texas by itself.
- The olives flying off the pizza.
- The three contract clauses marked on page 18 of 40.

## cast: Characters

Label "Characters". Headline: "Every voice agent should have a face." Lede: "Before we hear someone's words, we read their face. A nod or a small smile tells us we were heard. Voqalize characters give your app those same signals."

A row of three signals sits under the lede, each underlined in vermilion: Listens, Thinks, Responds.

A still grid of tiles, all the same size, each playing a real idle loop of the character: Tanvi, Tara, Tushar, Tanya, Tess, Trisha. The last tile is "Create yours", an empty outline of a head and shoulders with a plus badge. The closing line is "Pick one of ours, or create your own for your brand."

Things on screen she can point to:
- Herself, Tanvi, first in the grid, alongside five other characters.
- The three signals: Listens, Thinks, Responds.
- The "Create yours" tile for a character made for a brand.

## pricing: Pricing

Label "Pricing". Headline: "Pricing is per minute of conversation." Lede: "Sign up and the first 300 conversation minutes are free. Speech in both directions, turn-taking, the connection and the character are all in the minute."

There are two switches. Billing is Annual (the default, tagged "2 months free") or Monthly, and annual means ten months paid for twelve. Currency is USD (the default) or INR. The footnote reads "Prices exclude tax." in USD and "Prices exclude GST." in INR, with a link "What a minute includes, and common questions".

Free: "Build against the real thing."
- $0 (₹0), free forever. 300 free minutes at signup. 1 session at once.
- Up to one application. Every feature, ungated. Docs, SDKs, MCP and the demos.
- Button: Start free.

Starter: "One workflow in production."
- Annual: $83/mo, $990 billed yearly (₹8,333/mo, ₹99,990 billed yearly).
- Monthly: $99/mo (₹9,999/mo), billed monthly.
- 3,000 minutes a month included. Extra minutes cost $0.03/min (₹2.70/min). 5 sessions at once.
- Up to two applications. Email support, next business day.
- Button: Choose Starter.

Growth: flagged "Most teams", "Several workflows, or one that peaks."
- Annual: $416/mo, $4,990 billed yearly (₹41,666/mo, ₹499,990 billed yearly).
- Monthly: $499/mo (₹49,999/mo), billed monthly.
- 18,000 minutes a month included. Extra minutes cost $0.027/min (₹2.43/min). 25 sessions at once.
- Everything in Starter, plus: up to five applications, your custom character, your custom voice, a Forward Deployed Engineer for tech support, priority support in a shared Slack channel, and a 99.5% uptime SLA.
- Button: Choose Growth.

Enterprise: "Voice is load bearing."
- Price: "Talk to us", quoted for your volume.
- Everything in Growth, plus: speech models deployed in your VPC; SSO, DPA and a 99.9% uptime SLA; a named account manager; and bring your own TTS and STT.
- Button: Talk to us (it opens the page to book a call with Samkeet, in a new tab).

Things on screen she can point to:
- The 300 free minutes at signup.
- Growth, marked "Most teams", with a custom character and voice.
- The Annual switch with "2 months free", which takes Starter from $99 to $83 a month.
- The INR switch, which shows rupee prices excluding GST.
