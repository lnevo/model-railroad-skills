# Operations Pro showcase: guide

This is a tour of the Juniper Falls & Northern, an invented railroad built to show what JMRI Operations Pro can do. Each case is something you can build on your own railroad, shown working. Some are setups that people on the JMRI user list asked about. The rest cover the ways a car can be routed.

You don't need to know how the plugin works inside. You ask Claude in plain words and it answers from the railroad's files. The questions below are examples, so put them your own way.

## How to use it

Copy the operations folder into a scratch JMRI profile, or point Claude at it. Nothing in it needs changing, and the active day is Tuesday.

Pick a case. Each one follows the same order:

| Heading | What it gives you |
|---|---|
| What you can build | The result, in a sentence |
| Why you'd want it | What it adds to operations on a layout |
| How it works | The idea, the JMRI setting behind it, and what to watch for |
| Set it up | Where it is in JMRI, and what to ask Claude |
| Find it | The locations, tracks, trains and cars to look at |
| See it work | What to ask Claude, and what you should see |
| Try this | A change to make on a copy, and what it teaches |

A few things help as you go:

- A session here means one round of building and running the trains. The first session is the one after you open the folder.
- All 18 trains build in the first session. After that, staging trains start to run out of cars: `CUSTOM`, `MIXED` and `MODE` have nothing to run from the second session, and `HOP OUT` from the third. That is by design, so a failed build there is expected.
- Name the train when you ask about a car. Without one, Claude picks a train itself and may give you a different answer.
- Make Try this changes on a scratch copy, never on the shipped folder. If you want Claude to explain a build after a change, ask it to run a real build on the copy first.
- Cars, locations, trains and routes carry their case code in their comment, such as [U07], so you can search for it in the Operations windows. Tracks don't, so use their names.

## What a check of the railroad reports

If you ask Claude to check the whole railroad, it reports three notes. None is an error, and all three are there on purpose:

- A warning on `West Custom`. This staging track refuses empties, which is the point of case U06.
- Two notes on `Ferris Transfer`. Its pick ups name one route on purpose, as case R07 shows, so the two other routes that call at Ferris Junction are not on the list.

---

## Part 1: use-cases

These cases cover the everyday work of a railroad: giving cars a reason to move, deciding where they go, running staging, making up trains and running a session.

### U01. Industries that receive empties

**What you can build:** An industry that takes empties and ships them loaded: a mill loads an empty hopper with Feed for a dairy.
**Why you'd want it:** Most real industries ship as well as receive. A car arrives empty and leaves loaded, so a crew has something to pull as well as something to spot.
**How it works:** The spur has to accept empties before its schedule can load them. Brae Feed Mill's load options let an empty in, and the first line of its schedule receives it. The car leaves with Feed for the dairy. A spur with a schedule refuses any car that no line matches, so the line has to name the car type.
**Set it up:** In Edit Spur Track, use Load Options to let the empty in, then choose a schedule under Optional Schedule. Give it a line with the car type, Receive E, a load under Ship and a Destination. Ask Claude: "Make this spur take empty hoppers and ship Feed to the dairy."
**Find it:** `Brae Feed Mill`, `Dunmere Dairy`, `Feed Mill Loading`, `Dairy Receiving`, `LOCAL-B`, `JFN 101`, `JFN 102`
**See it work:** Ask "Can JFN 101 go to Brae Feed Mill on LOCAL-B?" Claude says yes. After the first session JFN 101 is on the mill with Feed, bound for Dunmere Dairy. In the next session it reaches the dairy.
**Try this:** Ask Claude to set Brae Feed Mill to accept only Feed. The hopper can no longer go there, and Claude says why: the mill no longer takes an empty hopper.

### U02. A schedule applied to a car already on a spur

**What you can build:** A schedule added to a spur that already holds a car, with that car taking its load and destination from the schedule.
**Why you'd want it:** You will often add a schedule after cars are already sitting at the industry. This gets those cars working without a trip away and back.
**How it works:** A car already on the spur has to be given the schedule. JMRI's Set Car window has an option to apply it, and JFN 201 was set up that way on Brae Cannery. It carries the schedule's load and final destination. Nothing else goes back to parked cars, so adding a schedule on its own does nothing for them.
**Set it up:** Open Set Car and change the car's track. When the new track is a spur with a schedule, JMRI asks whether to apply it, so answer yes. Ask Claude: "Deliver this car to Brae Cannery and apply the schedule."
**Find it:** `Brae Cannery`, `Cannery`, `Grocery Dock`, `Grocery Receiving`, `JFN 201`
**See it work:** Ask "What load and final destination does JFN 201 have?" It has Canned, bound for Grocery Dock. After the first session it is at Grocery Dock as an empty, and the `LOCAL-B` manifest shows it set out there.
**Try this:** Ask Claude to place a boxcar on Brae Cannery without applying the schedule, then to check the railroad. Claude reports that the schedule was not applied to that car.

### U03. Custom loads give cars a purpose

**What you can build:** Cars that travel for a reason: each carries a custom load to a named customer, while default cars stay on a yard.
**Why you'd want it:** Custom loads turn a car move into a shipment with a customer at each end. Crews can see why a car is going somewhere, and the same car can do different jobs.
**How it works:** JFN 301 and JFN 302 were given a Lumber load and a final destination, so they go to Lumber Dealer. `WNDR 1` and `WNDR 2` are default cars with no schedule. Dunmere Yard takes them, and they only ever sit on a yard. A car with a custom load looks for a spur that wants it, at every location. A default car only looks along the route of the train being built.
**Set it up:** Add the load in the Car Loads window. Then give the shipper and the customer schedules that ship and receive it. Ask Claude: "Add a Lumber load that Brae Lumber ships to Lumber Dealer."
**Find it:** `Brae Lumber`, `Lumber Dealer`, `Lumber Shipping`, `Lumber Receiving`, `Dunmere Yard`, `JFN 301`, `JFN 302`, `WNDR 1`, `WNDR 2`
**See it work:** After the first session both Lumber cars are at Lumber Dealer as empties. Ask "Can WNDR 1 go to Brae Lumber on LOCAL-B?" Claude says no, and lists the type, road and load as the reasons.
**Try this:** Ask Claude to remove the schedule from Lumber Dealer. It only notes the unused schedule. In a session the Lumber cars still reach the spur, because it is their final destination.

### U04. A local move inside one location

**What you can build:** A move inside one location: a one-stop route that takes a car from the yard to a spur in the same town.
**Why you'd want it:** Real switch jobs often work a single town or plant. This lets a job spend its whole time in one place, moving cars from the yard to the industries.
**How it works:** `SAWYER SWITCHER` has a route with one stop, and that stop allows local moves. JFN 401 carries Semolina from Sawyer Yard to the spur that receives it. A train with one stop never leaves, so all its work has to be local moves.
**Set it up:** In Edit Route, make a route with one location and tick Local moves? for that stop. Then give a train that route. Ask Claude: "Add a switcher that works only inside Sawyer."
**Find it:** `Sawyer`, `Sawyer Yard`, `Sawyer Pasta Plant`, `Sawyer Pasta Plant Schedule`, `SAWYER SWITCHER`, `JFN 401`
**See it work:** After the first session JFN 401 is on Sawyer Pasta Plant. Ask "Can JFN 401 go to Sawyer Pasta Plant on SAWYER SWITCHER?" Claude says yes, with nothing in the way.
**Try this:** Ask Claude to turn off pick ups and local moves at that stop. The build moves no cars, and Claude explains why.

### U05. Move counts and priority

**What you can build:** Control over which track gets the cars, using move counts, which win here over a High priority.
**Why you'd want it:** When two tracks could take the same cars, this is how you favour one. It spreads traffic or concentrates it without changing any train.
**How it works:** Each track keeps a count of its moves, and JMRI tries the lowest count first. Hollis Track 1 has High priority but 100 moves. Hollis Track 2 has no priority and no moves, so it gets the cars. Priority only decides which cars are looked at first, never where they go. Tracks with a schedule also come ahead of those without one, whatever their count.
**Set it up:** In Edit Location, turn on Tools, Show Track Moves, and edit the Moves column. Adding a track in that window resets the counts at that location, so set them last. Ask Claude: "Make cars prefer Hollis Track 2 over Hollis Track 1."
**Find it:** `Hollis Mill`, `Hollis Track 1`, `Hollis Track 2`, `LOCAL-H`, `GNDX 501`, `GNDX 502`, `GNDX 503`
**See it work:** After the first session all three gondolas are on Hollis Track 2. Ask "What order will GNDX 501 try the tracks at Hollis Mill on LOCAL-H?" Claude puts Hollis Track 2 first.
**Try this:** Ask Claude to set Hollis Track 2 to 200 moves. The order turns round, and the first session puts all three cars on Hollis Track 1.

### U06. Departure staging with generated custom loads

**What you can build:** Departure staging that sends out cars with a purpose: tracks give cars a generated load, and they go on to the industries that receive it.
**Why you'd want it:** Trains from staging arrive with real business for your industries, not just empties looking for a place to go. It feeds the layout from the rest of the world.
**How it works:** `West Custom` holds only cars that leave with a generated load, Machinery, and it refuses empties. `West Mixed` ships Machinery and empties. Two depots receive the Machinery. Only a default empty is given a generated load, and the spur's schedule line must name that load. Every car on a departure track must get a destination, or the build fails, so West Custom's refusal of empties is a real choice.
**Set it up:** In Edit Staging Track, tick Generate custom loads for spurs serviced by this train, or Generate custom loads for any spur (multiple trains). Give the receiving spurs schedule lines that name the load. Ask Claude: "Make West Custom generate Machinery loads for the depots."
**Find it:** `West Custom`, `West Mixed`, `East Mixed`, `Brae Depot`, `Dunmere Depot`, `CUSTOM`, `MIXED`, `JFN 601`, `JFN 611`, `JFN 614`
**See it work:** Ask "Why did JFN 601 go where it did on CUSTOM?" Claude explains that the staging track gave it a Machinery load and sent it through Carrow Yard to Brae Depot. In the next session `LOCAL-B` delivers it there and it comes off as an empty. `MIXED` carries JFN 611 to 613 toward a depot, and JFN 614 leaves as an empty for East Mixed.
**Try this:** Ask Claude to remove both depot schedules. It notes only that they are unused, and the train still builds. West Custom can also load a car for a staging track, so the car goes toward East Mixed instead.

### U07. Two staging tracks swapping full trains

**What you can build:** Two staging tracks that swap full trains in one session, and swap back in the next.
**Why you'd want it:** Two fleets of cars can trade places between the ends of a line, so a through freight keeps running every session with little staging work by hand.
**How it works:** A staging track full of cars would normally block the train coming in. `West Swap` and `East Swap` both use planned pick ups at 100 percent, so each track counts its cars as already leaving. Terminating a train into staging fills that track, which is why the setting is needed at both ends.
**Set it up:** In Edit Staging Track, open Tools, Planned Pick Ups, and set it to 100 on both tracks. Ask Claude: "Let West Swap and East Swap trade full trains in one session."
**Find it:** `West Swap`, `East Swap`, `SWAP-E`, `SWAP-W`, `SWPX 1`, `SWPX 11`, `JFN 51`, `JFN 53`
**See it work:** In the first session `SWAP-E` takes SWPX 1 to 6 to East Swap, and `SWAP-W` takes SWPX 11 to 16 to West Swap. That is 12 cars in one session. The next session reverses them.
**Try this:** Ask Claude to set East Swap's planned pick ups to 0. Claude warns about it first. `SWAP-E` then fails to build because East Swap is occupied, and `SWAP-W` still builds.

### U08. A fiddle yard of virtual spurs

**What you can build:** A fiddle yard of virtual spurs: their schedules send cars on to named customers, with a random line to vary the traffic.
**Why you'd want it:** A fiddle yard stands in for a busy district without the track. Here a short yard feeds cars on to customers, and a random line stops every session looking the same.
**How it works:** `Fiddle North` and `Fiddle South` are spurs whose schedule lines name the track the car goes to next. The south line is set to random 25 percent, with a wait of one, so traffic varies. Random is a percentage for that line, and Wait holds the load change until a set number of builds have passed. A line's Destination is where the car goes next, so one short yard can feed many places.
**Set it up:** On each spur's schedule, fill in the Destination and track, and use the Random and Wait columns on the lines you want to vary. Ask Claude: "Send cars from Fiddle South to Tool Depot on about one try in four."
**Find it:** `Fiddle North`, `Fiddle South`, `Parts Depot`, `Tool Depot`, `Parts Receiving`, `Tools Receiving`, `FIDDLE JOB`, `JFN 801`, `JFN 802`, `JFN 803`, `JFN 804`, `JFN 805`, `JFN 806`
**See it work:** `FIDDLE JOB` takes all six cars to the fiddle yard. Cars on Fiddle North carry Parts for Parts Depot, and cars on Fiddle South carry Tools for Tool Depot from the second session. By the third session more Parts cars have been delivered than Tools cars.
**Try this:** Ask Claude to take the random setting off Fiddle South. Both of its lines then work like Fiddle North's.

### U09. One schedule for several spurs

**What you can build:** One schedule shared by several spurs, with nothing to copy.
**Why you'd want it:** Several similar customers often take the same traffic. One schedule keeps them in step, and one change reaches them all.
**How it works:** `Grain Receiving` is assigned to both elevators. There is one schedule to keep up. Both spurs read the same lines, so a change to the schedule reaches both.
**Set it up:** In Edit Spur Track, choose the same schedule under Optional Schedule on each spur. Assigning a different schedule from the schedule's own edit window resets move counts everywhere, so set those last. Ask Claude: "Use Grain Receiving on both elevators."
**Find it:** `Elevator A`, `Elevator B`, `Grain Receiving`, `JFN 901`, `JFN 902`
**See it work:** Ask "What schedule do Elevator A and Elevator B use?" Both use the same one. After the first session one car sits empty on each elevator.
**Try this:** Ask Claude to copy the schedule and point Elevator B at the copy. It works and Claude raises nothing, so sharing is your choice.

### U10. A mixed default and custom spur

**What you can build:** One industry that takes both default and custom cars, using a second virtual spur, with one name on the paperwork.
**Why you'd want it:** A freight house or team track often handles ordinary cars and a special shipment at the same address. Crews see one place on the paperwork, while JMRI treats the two kinds separately.
**How it works:** `Freight House` takes the default cars, and a second spur, `Freight House-(2)`, takes the Crates line. JMRI leaves off the hyphen and what follows when it prints a name. A spur with no schedule refuses custom loads, and a schedule refuses cars no line matches. Two spurs let each kind of car have its own rules.
**Set it up:** Add a second spur at the location with the same name plus a hyphen, and give only that one the schedule. Ask Claude: "Add a second spur for Freight House that takes the Crates line."
**Find it:** `Freight House`, `Freight House-(2)`, `Crates Receiving`, `FRHX 1`, `JFN 1001`
**See it work:** After the first session FRHX 1 is on Freight House and JFN 1001, with Crates, is on Freight House-(2). The `LOCAL-B` manifest says "to Freight House" for both.
**Try this:** Ask "Can FRHX 1 go to Freight House-(2)?" Claude says no, because that spur's schedule line receives Crates and the car is empty.

### U11. Spurs and yards in balance

**What you can build:** A spur that keeps working when full: the train that brings new cars pulls the old ones, and cars return to their own lead.
**Why you'd want it:** Busy industries are the first to fill. This keeps them working at capacity, with the same train swapping the old cars for new ones, which is a satisfying switching job.
**How it works:** `Mill Spur` holds two cars. Planned pick ups let it take new cars while the same train pulls the old ones. Cars of road MILX return to their own lead. Without this, cars already on the spur count against its length until they are pulled, so a full spur refuses the next car even when the train will clear it.
**Set it up:** In Edit Spur Track, open Tools, Planned Pick Ups, and set a percentage. Use Road Options on a lead track to keep it to your own cars. Ask Claude: "Let Mill Spur take new cars while the same train pulls the old ones."
**Find it:** `Mill Spur`, `Bakery`, `Carrow Mill Lead`, `Mill Flour`, `Bakery Receiving`, `MILX 1101`, `MILX 1102`, `MILX 1103`, `MILX 1104`
**See it work:** After the first session two cars are on Mill Spur with Flour for Bakery, and two are on Carrow Mill Lead. In the second session the first pair reaches Bakery and the second pair is on the spur. In the third, the second pair is at Bakery and the first pair is back on the lead.
**Try this:** After the first session on a copy, ask Claude to set Mill Spur's planned pick ups to 0. Claude says the track is full, and the next session leaves the spur empty.

### U12. Normal and aggressive mode

**What you can build:** A staging train with a locomotive change that builds in both normal and aggressive mode.
**Why you'd want it:** If you turn on aggressive mode to get more swaps on full spurs, you will want to know your trains still build. This shows a staging train that works either way.
**How it works:** `MODE` changes locomotives at Brae and ends in staging. Aggressive is a build option, and this train works with it on or off. Normal makes one pass over the cars. Aggressive makes two to four, and later passes revisit cars skipped earlier. Staging trains have to clear their track in both.
**Set it up:** Aggressive is under Build Options in the Options window, from Tools in OperationsPro Settings. Number of Passes During Build is beside it. Ask Claude: "Does anything change if I turn on aggressive mode?"
**Find it:** `West Mode`, `East Mode`, `Brae Stockyard`, `MODE`, `MODX 1`, `MODX 2`, `MODX 3`, `MODX 4`, `MODX 5`
**See it work:** In the first session five cars leave West Mode, one for Brae Stockyard and four for East Mode. Ask "Does anything change if I turn on aggressive mode?" Claude compares the builds and finds no change.
**Try this:** With aggressive on, ask Claude to limit the MODE stop at Brae to a train length of 100 feet. MODE fails to build. Claude says the train would be 4 feet over leaving Brae, and that 2 cars leaving staging have nowhere to go.

### U13. Caboose, kernel, locomotive change and consist

**What you can build:** Trains with the right equipment: a required caboose, a kernel that stays together, a locomotive change, and consists that swap ends.
**Why you'd want it:** Equipment rules make trains look right. A caboose on the local, a cut of cars that never splits and a power change at a crew change are all part of how a real railroad runs.
**How it works:** `LOCAL-H` requires a caboose. The kernel `Brae Set` moves as one. `MODE` changes locomotives at Brae. The consists `West Pair` and `East Pair` swap ends with their trains. A kernel counts as one move, and its cars must all be on one track or the whole build fails. A consist is used through its lead locomotive.
**Set it up:** Require the caboose in Edit Train. Set Kernel in Edit Car and Consist in Edit Locomotive. A Locomotive change at a stop is in Train Build Options, from Tools in Edit Train. Ask Claude: "Make Brae Set a kernel, and have LOCAL-H require a caboose."
**Find it:** `Carrow Caboose Track`, `Dunmere Team`, `Brae Set`, `Brae Engine Track`, `LOCAL-H`, `LOCAL-B`, `MODE`, `SWAP-E`, `SWAP-W`, `JFN 1301`, `JFN 1302`, `KRNX 1`, `KRNX 2`, `KRNX 3`, `JFN 51`, `JFN 55`, `JFN 56`, `JFN 57`
**See it work:** Every `LOCAL-H` build carries one of the two cabooses and sets it out on Carrow Caboose Track, taking turns. KRNX 1 to 3 stay together on Dunmere Team. The `MODE` manifest says "Locomotive change at Brae".
**Try this:** Ask Claude to let any route pick up from Carrow Caboose Track. It warns you first. Over three sessions `LOCAL-H` takes one caboose, then the other, then fails to build, because a car won't leave the track on the route that set it out.

### U14. Train schedule days

**What you can build:** Operating days: each day has its own list of trains, and a schedule line can set cars out on one day only.
**Why you'd want it:** Weekday and weekend timetables give a railroad a rhythm. You can run a full Tuesday and a quiet Saturday from the same layout, with some customers open only on certain days.
**How it works:** Tuesday lists all 18 trains and Saturday lists six. Tuesday is the active day and has been applied, which sets each train's Build box. The schedule line `Tuesday Dock` sets cars out on Tuesday only. Activate sets the day, and applying it sets each train's Build box. They are two separate steps, and a schedule line with a day only acts when that day is active.
**Set it up:** In the Train Schedules window, tick the trains for each day, use Activate for the day you want, then apply it. Set a line's day on the schedule itself. Ask Claude: "Make Saturday a six-train day and make it active."
**Find it:** `Tuesday`, `Saturday`, `Tuesday Dock`, `Brae Day Track`, `DAYX 1`, `LOCAL-B`
**See it work:** Ask "What days are set up?" Tuesday has 18 trains, Saturday has 6, and Tuesday is active. The build report says so too. After the first session DAYX 1 is on Tuesday Dock.
**Try this:** Ask Claude to make Saturday the active day and apply it. JMRI then builds exactly the six Saturday trains. DAYX 1 can't go to Tuesday Dock, and Claude gives both reasons: `LOCAL-B` is not on the list, and the line is for Tuesday.

### U15. An automation

**What you can build:** An automation that builds and terminates a session's trains in the order you choose, with no dialog to stop it.
**Why you'd want it:** An automation runs the routine parts of a session for you, the same way each time, so you can get on with operating or preparing the next session.
**How it works:** `Evening Session` builds `LOCAL-H` and `LOCAL-B`, then runs `Close Out`, which terminates `LOCAL-B`. It waits for that, then terminates `LOCAL-H`. It is not the startup automation. A step with a message waits at the JMRI computer until someone answers. A wait for a train needs someone else to terminate it, which is why `Close Out` is a second automation. A startup automation runs every time JMRI loads the train file.
**Set it up:** In the Edit Automation window, add steps such as Build Train, Run Automation, Wait for Train to Terminate and Terminate Train. Ask Claude: "Write an automation that builds these two trains and terminates them in order."
**Find it:** `Evening Session`, `Close Out`, `LOCAL-H`, `LOCAL-B`
**See it work:** Ask "What are the steps in Evening Session?" It has five. Set as the startup automation on a copy, real JMRI ran all five, and both trains ended not built.
**Try this:** Ask Claude to add a yes or no message step. It refuses unless you tell it dialogs are allowed.

### U16. Manual build lines

**What you can build:** A train that takes one chosen car, using a manual build line.
**Why you'd want it:** Sometimes one car has to move today: a car for a story, a special shipment, or a car you want out of the way. This does it without changing the railroad's normal rules.
**How it works:** A manual build line on `LOCAL-H` tells it to take TEMX 1 from Hollis Team. A line can name the type, road, load, stop, pick up track, destination and count, so it can ask for a kind of car as well as a single one.
**Set it up:** In Edit Train, open Tools, Train Manual Build, add a line and use Save Manual Build. Ask Claude: "Have LOCAL-H take TEMX 1 from Hollis Team."
**Find it:** `Hollis Team`, `Oakhaven Team`, `LOCAL-H`, `TEMX 1`
**See it work:** The first session puts TEMX 1 on Oakhaven Team. Ask "Why did TEMX 1 move on LOCAL-H?" Claude points to the manual build line.
**Try this:** Ask Claude to delete the line and set the Hollis stop to 1 move. TEMX 1 stays on Hollis Team.

### U17. Paperwork

**What you can build:** Paperwork of your own: colours, font, a valid line, a track field, changed phrases and a railroad name for one train.
**Why you'd want it:** Paperwork is what crews read all session. Clear colours and your own wording make a manifest faster to work from, and a branch line can have its own name.
**How it works:** The manifest has red pick ups, blue set outs and green local moves, in font size 10. It prints a valid line and a track field on pick up lines. One train, `LOCAL-B`, has its own railroad name. An apostrophe in a phrase has to be doubled. Text with a number in braces, such as {0}, is filled in by JMRI, so a stray brace breaks the line.
**Set it up:** Colours, Font and Print Valid are in Manifest Print Options, from Tools in OperationsPro Settings. Phrases are in Edit Manifest Text. A train's name is Optional Railroad Name for this Train, in Manifest Options, from Tools in Edit Train. Ask Claude: "Print pick ups in red and set outs in blue."
**Find it:** `LOCAL-B`, `FIDDLE JOB`
**See it work:** The `LOCAL-B` manifest starts "Brae Branch Lines" and prints "Conductor's copy, valid ..." with one apostrophe. `FIDDLE JOB` prints JMRI's default, "My JMRI Railroad", because the railroad has no name set.
**Try this:** Ask Claude to set the valid line to "Valid {0". It refuses, because a brace has to open a numbered value such as {0}.

### U18. Passenger blocking

**What you can build:** A passenger train whose cars stay in the order you set, on station spurs only it serves.
**Why you'd want it:** A passenger train should come together the same way every day, with the head-end cars up front. Blocking keeps that order without any switching by hand.
**How it works:** FLYX 1 to 5 have blocking numbers -5, 10, 20, 40 and 70. The station spurs serve `VALLEY FLYER` only. Negative numbers go to the front, most negative first. Zero and above go to the rear in rising order, ahead of any caboose.
**Set it up:** In Edit Car, tick Passenger and set Blocking Order. Name the train on each station spur under Select trains or routes for pick ups, and the same for set outs. Ask Claude: "Put the baggage car first on VALLEY FLYER."
**Find it:** `Carrow Station`, `Northwood Station`, `VALLEY FLYER`, `FLYX 1`, `FLYX 2`, `FLYX 3`, `FLYX 4`, `FLYX 5`
**See it work:** The `VALLEY FLYER` manifest picks up FLYX 1, 2, 3, 4 and 5 in that order, and sets all five out at Northwood Station.
**Try this:** Ask Claude to set FLYX 5's blocking number to -9. FLYX 5 is then picked up first.

### U19. Track pools

**What you can build:** A pool of tracks that share their length, with a minimum and maximum on each.
**Why you'd want it:** Yards and interchanges are often really one long stretch of rail. A pool lets the tracks share space, so a short track can borrow room when it needs to.
**How it works:** `Hollis Pool` has two tracks. Pool 1 is 100 feet, with a minimum of 100 and a maximum of 150. Pool 2 is 300 feet, with a minimum of 100. A track can borrow length from the other. The minimums can't add up to more than the tracks' combined length. A pool shares length, but the builder doesn't search the tracks as one.
**Set it up:** In Edit Spur Track or Edit Yard Track, open Tools, Track Pools. Add a name under Pool name, then set each track's minimum, and tick Enable User Specified Maximum* for a maximum. Ask Claude: "Pool these two tracks with a 100-foot minimum on each."
**Find it:** `Hollis Pool 1`, `Hollis Pool 2`, `Hollis Pool`, `POOX 1901`, `POOX 1902`, `POOX 1903`, `POOX 1904`, `POOX 1905`, `POOX 1906`
**See it work:** The first session spreads six 40-foot flatcars three and three. Pool 1 borrows length to do it, and stays between its 100 and 150.
**Try this:** Ask Claude to raise Pool 1's minimum to 350. It refuses, because the minimums would add up to more than the pool's 400 feet.

### U20. On-time build order

**What you can build:** Trains with departure times, and the choice of whether they must be built in that order.
**Why you'd want it:** Departure times make a timetable feel real. On Time adds the discipline of building trains in the order they leave, for when you want a strict schedule.
**How it works:** `FIDDLE JOB` departs at 08:45, `LOCAL-B` at 09:00 and `LOCAL-H` at 10:00. The option "Build on time" is off here. With On Time on, a train may not depart earlier than the last one built. With it off, departure times only feed the times on the paperwork and some timing checks.
**Set it up:** Set Departure Time in Edit Train. On Time is under Build Options in the Options window, from Tools in OperationsPro Settings. Ask Claude: "Show me the departure order of these three trains."
**Find it:** `LOCAL-B`, `LOCAL-H`, `FIDDLE JOB`
**See it work:** With the option off, you can build `LOCAL-H` in one session and `LOCAL-B` in the next, and both build.
**Try this:** Ask Claude to turn on Build on time, build `LOCAL-H`, then build `LOCAL-B`. `LOCAL-B` is refused because it departs earlier. JMRI shows Error and writes no build report, so ask Claude why. Changing `LOCAL-B` to depart at 11 clears it.

### U21. Divisions

**What you can build:** Cars that go home: a home division sends empties to the home yard and loads to the home spur.
**Why you'd want it:** Railroads want their own cars back. Divisions send a car home after a trip away, so your cars keep working your territory instead of drifting around the layout.
**How it works:** Northwood is in the division `North`, and the NWRX cars have it as their home division. JMRI gives them a final destination when the train builds. A car with a home division and no final destination gets one at build, default load included. Empties head for the home division. A car leaving staging needs a reachable place in its division that takes it.
**Set it up:** In Edit Location, set Division. Then set Home Division on the car in Set Car. Ask Claude: "Put Northwood in a North division and make it home for the NWRX cars."
**Find it:** `North`, `Northwood Yard`, `Malt House`, `Malt House Receiving`, `NWRX 1`, `NWRX 2`, `NWRX 3`
**See it work:** `EAST FREIGHT` takes NWRX 1 to 3 to Ferris Yard. NWRX 1 and 2 are bound for Northwood Yard and NWRX 3 for Malt House. In the next session `NORTH JOB` delivers them.
**Try this:** Ask Claude to clear NWRX 1's home division. It gets no final destination after the first session, but it still reaches Northwood Yard in the next.

### U22. Hazmat, buffer and idler cars, LCL

**What you can build:** Special traffic: a buffer car, hazardous tank cars, idlers in a kernel that print as one load, and an LCL boxcar on a dock.
**Why you'd want it:** Special traffic adds interest. A tank train with a buffer, a long load on idlers and a daily LCL car all give crews something to think about beyond ordinary boxcars.
**How it works:** On `TURN`, HZMX 9 is a Buffer that rides first out of staging. HZMX 1 to 3 are hazardous tank cars for Linden Refinery. HZMX 11 to 13 are the kernel `Girder Load` for Linden Steel, and the idlers print as Girder. LCLX 1 is a boxcar marked as passenger that works as less-than-carload on a dock. Hazardous is a flag and a sort order, not a placement rule, so a buffer takes its place through Passenger and a negative blocking number. Kernel cars take the lead car's default load at build.
**Set it up:** In Edit Car, set Hazardous, Passenger and Blocking Order, and use Kernel for the idlers. Ask Claude: "Make HZMX 9 a buffer that leads TURN."
**Find it:** `Turn A`, `Turn B`, `Linden Refinery`, `Linden Steel`, `Girder Load`, `Carrow LCL Dock`, `TURN`, `HZMX 9`, `HZMX 3`, `HZMX 12`, `LCLX 1`
**See it work:** The `TURN` manifest lists HZMX 9 Buffer as the first pick up, and shows HZMX 3 as hazardous. LCLX 1 is on Carrow LCL Dock after every session, and the `LOCAL-B` manifest shows both its pick up and its set out.
**Try this:** Ask Claude to turn off the passenger setting on HZMX 9. It no longer rides, and the manifest shows a move from Turn A to Turn B instead of a pick up.

### U23. Backups

**What you can build:** A backup set you can return to after a bad change.
**Why you'd want it:** Operations changes are easy to make and hard to undo by memory. A backup before a big change lets you experiment freely.
**How it works:** The folder holds one backup set. Claude also takes a backup before every change it makes. JMRI has to be restarted to finish a restore. Its own automatic backups are made when it starts up, so you may have more sets than the one you made.
**Set it up:** In OperationsPro Settings, Tools has Backup and Restore. Auto Backup is in the same window. Ask Claude: "Back up the railroad before we start."
**Find it:** (the `backups/` folder, no object)
**See it work:** Ask "What backups do I have?" Claude lists the set: six files, complete. On a scratch copy, ask Claude to delete a car and then restore that backup. The car comes back.

### U24. A RIP track

**What you can build:** A RIP track where a loaded car keeps its load on arrival.
**Why you'd want it:** A shop track is a good reason for a car to leave service for a while. The car goes for repairs with its load, and nothing about the shipment is lost.
**How it works:** `Carrow RIP` has "Disable load change" set, so a car arrives with the load it left with. A delivery to a plain spur would normally swap the car's load. This setting stops that, and a schedule line's wait and pick up day still apply.
**Set it up:** In Edit Spur Track, open Load Options and tick Disable load change. Ask Claude: "Make Carrow RIP keep a car's load on arrival."
**Find it:** `Carrow RIP`, `Hollis Shop Lead`, `LOCAL-H`, `RIPX 1`
**See it work:** In the first session `LOCAL-H` takes RIPX 1 from Hollis Shop Lead to Carrow RIP, and it stays loaded.
**Try this:** Ask Claude to clear that setting. RIPX 1 then arrives empty.

---

## Part 2: routing variations

Each case here has one car that shows the route. Ask whether the car can reach a place on a named train, and Claude tells you the route JMRI 5.16 takes. Cases R01 to R05 and R19 start simple and grow. The rest show the settings that steer a route.

### R01. One train direct

**What you can build:** A car delivered by one train, with the schedule turning its load into an empty.
**Why you'd want it:** This is the simple case, and the one to get right first. Every longer route is built from single trips like this one.
**How it works:** `LOCAL-H` reaches the spur itself, so no routing is needed. The schedule at Oakhaven Cannery takes the peas and makes the car an empty. A car with a final destination is checked against the train first. If one train can do the whole trip, JMRI doesn't look for a longer route.
**Set it up:** Give the route a stop at the location, with Set outs? on, and give the spur a schedule. Ask Claude: "Can this car reach Oakhaven Cannery on LOCAL-H?"
**Find it:** `Oakhaven Cannery`, `Cannery Peas`, `LOCAL-H`, `JFN 5101`
**See it work:** Ask "Can JFN 5101 go to Oakhaven Cannery on LOCAL-H?" Claude says yes, on a single train. The first session puts it on the spur as an empty.
**Try this:** Ask Claude to turn off set outs for `LOCAL-H` at Oakhaven. The car can no longer go there, and Claude says the stop does not set out cars.

### R02. Two trains through an interchange

**What you can build:** A car that changes trains at an interchange to reach a customer one train cannot serve.
**Why you'd want it:** Interchanges are how cars change hands between jobs. A car moves over two sessions and two crews, which is the heart of a connected railroad.
**How it works:** `EAST FREIGHT` doesn't go to Northwood, so JMRI routes the car through the interchange at Ferris Exchange, and `NORTH JOB` finishes the trip. Routing runs for a car with a final destination. Every track on the way has to take the car, and an interchange's Destinations filter must allow its final destination. Room is checked at the first stop on the way, not at the far end.
**Set it up:** Enable Car Routing has to be on in the Options window. Add a Classification/Interchange track that both trains reach, and name the car's final track in the schedule. Ask Claude: "Find a route for Carrow Packing's cars to Cold Store."
**Find it:** `Ferris Exchange`, `Carrow Packing`, `Cold Store`, `EAST FREIGHT`, `NORTH JOB`, `JFN 5201`
**See it work:** Ask "Can JFN 5201 go to Cold Store on EAST FREIGHT?" Claude says yes, by two trains through Ferris Exchange. The first session leaves it there with Produce, and the next puts it on Cold Store as an empty.
**Try this:** Ask Claude to let Ferris Exchange send cars only to Linden. Claude blocks the change. In a build the car would stay at Carrow Packing with no destination.

### R03. Two trains through a yard

**What you can build:** A car that changes trains at a yard, with moves deciding which yard it uses.
**Why you'd want it:** Not every railroad has interchange tracks everywhere. Yards can do the same job, which suits a railroad built around a hub yard.
**How it works:** Routing via yards is on. The foundry car rides `LOCAL-H` to Carrow Transfer, then `EAST FREIGHT` to the pipe yard. Carrow Transfer is chosen because it has fewer moves than Carrow Yard, so keep its moves at 0. Routing through yards is off unless you turn it on. Yards are tried with the fewest moves first, so the move count picks the hub.
**Set it up:** Tick Enable Car Routing via Yards in the Options window, from Tools in OperationsPro Settings. Ask Claude: "Let cars route through yards, and use Carrow Transfer."
**Find it:** `Oakhaven Foundry`, `Carrow Transfer`, `Linden Pipe Yard`, `Foundry Casting`, `LOCAL-H`, `EAST FREIGHT`, `JFN 5301`
**See it work:** Ask "Can JFN 5301 go to Linden Pipe Yard on LOCAL-H?" Claude says yes, by two trains through Carrow Transfer. The first session takes it there, and the next takes it to the pipe yard.
**Try this:** Ask Claude to turn off routing via yards. Claude then finds no route, yet the car gets there anyway, because from Carrow it is a one-train trip. The option changes the answer here, not the result.

### R04. A chain of three trains

**What you can build:** A car carried by a chain of three trains, with a relay track between each.
**Why you'd want it:** Long hauls feel like real railroading. One car takes several sessions and several crews to arrive, and you can follow it across the whole layout.
**How it works:** No one train covers the trip. `LOCAL-H` reaches Carrow Relay, `EAST FREIGHT` reaches Ferris Relay, and `NORTH JOB` reaches Northwood Steel. JMRI works out the whole chain, then moves the car one leg each time a train can take it. Each relay track must accept the car and allow its final destination.
**Set it up:** Make sure each train reaches the next relay track, and check each track's Track Destinations. Ask Claude: "Is there a chain of trains from Hollis Coil Mill to Northwood Steel?"
**Find it:** `Hollis Coil Mill`, `Carrow Relay`, `Ferris Relay`, `Northwood Steel`, `Coil Mill Shipping`, `LOCAL-H`, `EAST FREIGHT`, `NORTH JOB`, `JFN 5401`
**See it work:** Ask "Can JFN 5401 go to Northwood Steel on LOCAL-H?" Claude says yes, by 3 trains. The car moves one leg each session, and after the third it is at Northwood Steel as an empty.
**Try this:** Ask Claude to let Ferris Relay send cars only to Linden. Claude blocks the change. In a build the car would stop on Carrow Relay.

### R05. A route through staging

**What you can build:** A car routed through a staging track, to reach a spur its first train cannot serve in that direction.
**Why you'd want it:** Staging can act as a turning point. A car goes off the layout one way and comes back the other, which reaches a spur that faces the wrong way.
**How it works:** Linden Pier can't be worked by an eastbound train. So `EAST FREIGHT` sets the car in staging on `Hop`, and `HOP OUT` brings it back the other way. Routing through staging has its own option. Tracks a route uses have to allow the final destination, as they do for an interchange.
**Set it up:** Tick Enable Car Routing through Staging in the Options window, from Tools in OperationsPro Settings. Ask Claude: "Can a car reach Linden Pier through staging?"
**Find it:** `Hop`, `Linden Pier`, `Carrow Salt Works`, `EAST FREIGHT`, `HOP OUT`, `JFN 5501`, `JFN 5502`
**See it work:** Ask "Can JFN 5501 go to Linden Pier?" Claude says yes, by two trains through staging at Hop. The first session sets it on Hop, and the next takes it to Linden Pier.
**Try this:** Ask Claude to turn off routing via staging. Claude then finds no route. `EAST FREIGHT` no longer takes the car, and `LOCAL-B` carries it to Dunmere Yard instead.

### R06. A Destinations filter as a gate

**What you can build:** An interchange that sends cars on to one destination only.
**Why you'd want it:** A filter gives a track a job. It can keep a branch's interchange for that branch's traffic, so cars don't wander through it.
**How it works:** The Destinations filter on `Ferris Gate` lets cars go only to Pell Creek-(yard). So the car goes to `Pell Tank Track`, not `Gate Yard`. The filter holds locations, not tracks, and exists on interchange and staging tracks only. It also applies to a car's final destination, so leaving out a place a schedule names makes cars scatter.
**Set it up:** In Edit Classification/Interchange Track, open Tools, Track Destinations, and choose the locations. Check Destinations there tests the result. Ask Claude: "Make Ferris Gate send cars only to Pell Creek-(yard)."
**Find it:** `Ferris Gate`, `Pell Tank Track`, `Gate Yard`, `NORTH JOB`, `GTEX 1`
**See it work:** Ask "Can GTEX 1 go to Gate Yard on NORTH JOB?" Claude says no, and names the filter. The first session sets it on Pell Tank Track.
**Try this:** Ask Claude to set Ferris Gate's destinations to all. The first session then puts the car on Gate Yard.

### R07. Pick ups named by route

**What you can build:** A track whose pick ups are named by route, so the route that set a car out can pull it back.
**Why you'd want it:** A turn job often drops a car at the junction and collects it again later. This lets the same job do both, as a real out-and-back would.
**How it works:** A car set out on an interchange won't normally leave on the route that brought it. `Ferris Transfer` names `NORTH JOB`'s route in its pick ups, which allows it. With Pick ups on Any, a car on an interchange can only leave on a different route, even with a different train. Naming the train or route lifts that.
**Set it up:** In Edit Classification/Interchange Track, under Select trains or routes for pick ups, choose Routes and add the route. Ask Claude: "Let NORTH JOB's route pull cars back from Ferris Transfer."
**Find it:** `Ferris Transfer`, `Northwood Shed`, `NORTH JOB`, `XFRX 1`
**See it work:** In the first session `NORTH JOB` sets XFRX 1 on Ferris Transfer. In the next, the same route pulls it back to Northwood Shed.
**Try this:** After the first session on a copy, ask Claude to set Ferris Transfer's pick ups to Any. The next build leaves XFRX 1 behind.

### R08. The Routed option

**What you can build:** Tracks that take routed cars only, while other cars go elsewhere.
**Why you'd want it:** Some tracks exist for traffic with somewhere to go. This keeps a through interchange from filling up with cars that have no plans.
**How it works:** `Ferris Routed` and `Hop` are set to take only cars that have a final destination. It applies on interchange and staging tracks, and cabooses and FRED cars are exempt.
**Set it up:** Tick This track only accepts cars with a final destination (Routed) on the track's edit window. Ask Claude: "Make Ferris Routed take routed cars only."
**Find it:** `Ferris Routed`, `Hop`, `Routed Siding`, `Carrow Box Factory`, `Box Factory Loads`, `JFN 5801`, `BOXX 1`
**See it work:** Ask "Can BOXX 1 go to Ferris Routed?" Claude says no, because the car has no final destination. JFN 5801 has one. The first session puts it on Ferris Routed and BOXX 1 on Ferris Yard, and the next takes JFN 5801 to Routed Siding.
**Try this:** Ask Claude to turn off that setting on Ferris Routed. The first session then puts BOXX 1 there.

### R09. An alternate, then forward to yard

**What you can build:** An industry with an alternate track and a yard behind it, so cars still move when the spur is full.
**Why you'd want it:** Popular industries overflow. An alternate track stands in for a real overflow siding, and the yard holds the rest until there's room, so traffic keeps moving.
**How it works:** `Oakhaven Plant` has `Plant Overflow` as its alternate track. When both are full, "forward to yard" sends the car to Oakhaven Yard, with the plant still as its final destination. Only a spur can have an alternate, and the two must share a direction. An alternate is never a direct destination. JMRI has no window for forward to yard, and it is on unless turned off.
**Set it up:** In Edit Spur Track, open Tools, Alternate Track, and choose the track. Ask Claude: "Give Oakhaven Plant Plant Overflow as its alternate."
**Find it:** `Oakhaven Plant`, `Plant Overflow`, `Oakhaven Yard`, `Plant Stone`, `LOCAL-H`, `JFN 5901`, `JFN 5902`, `JFN 5903`, `JFN 5904`
**See it work:** In the first session four hoppers go out. Two reach Oakhaven Plant, one reaches Plant Overflow and one reaches Oakhaven Yard. Which car goes where depends on build order. Ask "Why did JFN 5901 go where it did on LOCAL-H?" Claude walks through the full tracks.
**Try this:** Ask Claude to turn off forward to yard. The car that would have gone to the yard stays on Hollis Quarry. The other three go as before.

### R10. Overflow handled by a pool

**What you can build:** Two interchanges in a pool, sharing their length so a whole cut of cars fits.
**Why you'd want it:** A busy junction can take a whole cut of cars. A pool gives you that without one long track, and it is the way to give a yard or interchange overflow.
**How it works:** `Ferris Pool 1` and `Ferris Pool 2` are 120 feet each and share their length as `Ferris Pool`. An alternate only works on a spur, so a pool is the answer for interchanges and yards.
**Set it up:** In Edit Classification/Interchange Track, open Tools, Track Pools, and put both tracks in one pool. Ask Claude: "Pool Ferris Pool 1 and Ferris Pool 2 so they share their length."
**Find it:** `Ferris Pool 1`, `Ferris Pool 2`, `Ferris Pool`, `Carrow Grain Co`, `Grain Elevator`, `OAKX 1`, `OAKX 2`, `OAKX 3`, `OAKX 4`, `OAKX 5`
**See it work:** Five 44-foot cars all fit, three and two, and none is left at Carrow Grain Co. In the second session all five are at Grain Elevator.
**Try this:** Ask Claude to remove the pool. Only two cars fit on each track, and OAKX 1 is left behind.

### R11. An A/D track with a switcher

**What you can build:** A yard worked in two steps: a transfer sets cars on an A/D track, and a switcher sorts them to the class tracks.
**Why you'd want it:** This is how a real classification yard works. A road train arrives on one track, and a yard job sorts the cars, so there's work for a yardmaster.
**How it works:** `KESSOCK TRANSFER` brings the cars to `Kessock A/D`. `KESSOCK SWITCHER` then moves them to the class tracks. The build option that allows local interchange moves is on. Yards ignore pick up and set out lists, so the arrival and class tracks here are interchanges. Each class track is set out by the switcher only. Moves from one interchange to another by a local train are off until you allow them.
**Set it up:** Tick Allow Local Classification/Interchange to C/I Moves in the Options window, from Tools in OperationsPro Settings. Then set each track's trains. Ask Claude: "Set up Kessock A/D for the transfer and class tracks for the switcher."
**Find it:** `Kessock A/D`, `Kessock Class 1`, `Kessock Class 2`, `KESSOCK TRANSFER`, `KESSOCK SWITCHER`, `KESX 1`, `KESX 2`, `KESX 3`, `KESX 4`
**See it work:** In the first session KESX 1 to 4 arrive on Kessock A/D. In the next, the switcher moves all four to the class tracks, two on each.
**Try this:** Ask Claude to turn off that build option. The build moves no cars, and a check of the railroad warns about it.

### R12. A local switcher

**What you can build:** A local switcher that works spur to spur and yard to yard.
**Why you'd want it:** A town switcher can spend a session rearranging cars. Moves between spurs and between yard tracks give it real work with no road train involved.
**How it works:** `SAWYER SWITCHER` works inside Sawyer. Build options allow local spur moves and yard moves. Spur moves and yard moves have an option each, so you can allow one without the other.
**Set it up:** Tick Allow Local Spur to Spur Moves and Allow Local Yard to Yard Moves in the Options window, from Tools in OperationsPro Settings. Ask Claude: "Let SAWYER SWITCHER move cars between spurs."
**Find it:** `Sawyer Warehouse`, `Sawyer Yard 1`, `Sawyer Yard 2`, `SAWYER SWITCHER`, `SWYX 1`, `SWYX 2`
**See it work:** In the first session SWYX 1 moves spur to spur onto Sawyer Warehouse, and SWYX 2 moves yard to yard onto Sawyer Yard 2.
**Try this:** Ask Claude to turn off local spur moves. SWYX 1 stays put and SWYX 2 still moves, because yard to yard has its own option.

### R13. Through-car rules

**What you can build:** A train with through-car rules, which limit the cars it carries to its terminal.
**Why you'd want it:** A road train and a way freight behave differently. These rules let a train do work along the line, or keep through cars moving, as you choose.
**How it works:** `THRU` won't carry a car from its first stop straight to its terminal. Cars it picks up along the way go to the terminal, not to the next stop. The two rules are separate settings, so you can use either on its own. Passenger cars and cabooses are not held to the rule.
**Set it up:** In Edit Train, open Tools, Train Build Options. Use Allow cars to travel from origin to terminal and Send all car pick ups to terminal. Ask Claude: "Stop THRU taking cars straight from its first stop to its terminal."
**Find it:** `Dunmere Oil`, `Ferris Yard`, `THRU`, `OILX 1`, `OILX 2`
**See it work:** In the first session OILX 1 stops at Dunmere Oil, and OILX 2 goes to Ferris Yard.
**Try this:** Ask Claude to allow through cars on `THRU`. Both cars then go to Ferris Yard.

### R14. Service all cars with a final destination

**What you can build:** A choice of what a train does with final-destination cars when the stop they need is short of moves.
**Why you'd want it:** It decides what happens on a busy day. A car can wait for the right train, or start moving and make its way there by other trains.
**How it works:** `EAST FREIGHT` has "service all" on. It matters only when the stop runs out of moves. As shipped, Linden has 20 moves, so both cars reach Linden Glazier in the first session either way. If one train could deliver a car, JMRI normally waits for that train. This option lets another route be used.
**Set it up:** In Edit Train, open Tools, Train Build Options, and tick Service all cars with a final destination (FD). Ask Claude: "Should EAST FREIGHT service all cars with a final destination?"
**Find it:** `Carrow Glass Works`, `Linden Glazier`, `EAST FREIGHT`, `JFN 6401`, `JFN 6402`
**See it work:** The difference shows only on a copy with the Linden stop cut to 1 move, as below. Claude can't tell ahead of time how a build's moves will run out, so ask it to explain the build afterward.
**Try this:** On a copy, ask Claude to set the Linden stop to 1 move and try service all both ways. With it off, neither car moves. With it on, JFN 6402 goes to Ferris Yard and JFN 6401 to Carrow Yard, and they reach Linden Glazier over two trains.

### R15. Directions

**What you can build:** A track served from one direction, so only a train running that way works it.
**Why you'd want it:** A spur that faces one way is real railroading. It decides which job can work a customer, and it can force a run-around or a trip back from staging.
**How it works:** `Linden Westside` is set for westbound trains. `EAST FREIGHT` is eastbound there and `HOP OUT` is westbound. A track's direction has to match the train's direction at that stop, which comes from the route. A train going the other way can't work it at all.
**Set it up:** Set the direction checkboxes on the track's edit window, and the Train Direction column in Edit Route. Ask Claude: "Which trains can work Linden Westside?"
**Find it:** `Linden Westside`, `Carrow West Lead`, `EAST FREIGHT`, `HOP OUT`, `WSTX 1`
**See it work:** Ask "Can WSTX 1 go to Carrow on EAST FREIGHT?" Claude says no, and names the direction. On `HOP OUT` it can. The first session sets it on Carrow West Lead.
**Try this:** Ask Claude to set Linden Westside to both directions. `EAST FREIGHT` then takes the car to Hop, and `HOP OUT` brings it to Carrow West Lead in the next session.

### R16. Hyphen-named locations

**What you can build:** One town split into two locations that prints as one name on the paperwork.
**Why you'd want it:** Some towns need separate yard and industry locations for routing. Crews still see one town on the paperwork, so the split stays behind the scenes.
**How it works:** `Pell Creek-(yard)` and `Pell Creek-(industries)` are two locations. JMRI leaves off the hyphen and what follows when it prints, so crews see Pell Creek. JMRI treats them as two locations for everything else, so routes and tracks stay separate while `PELL SWITCHER` works the town.
**Set it up:** Name both locations with the town, a hyphen and a word, in the Locations window. Ask Claude: "Split Pell Creek into a yard and an industries location."
**Find it:** `Pell Creek-(yard)`, `Pell Creek-(industries)`, `Pell Yard`, `Pell Brickworks`, `PELL SWITCHER`, `PELC 1`, `PELC 2`
**See it work:** In the first session `PELL SWITCHER` moves PELC 1 and 2 to Pell Brickworks. The manifest says "Scheduled work at Pell Creek" and shows neither ending.
**Try this:** Ask Claude to rename a location to `Pell Creek-industries`. It warns about the hyphen. The cars still move, and the change shows in the name on the paperwork.

### R17. A rest-of-the-world interchange

**What you can build:** A rest-of-the-world interchange, where empties come back loaded and loads come back empty.
**Why you'd want it:** It stands for all the railroads you don't model. Cars leave and come back changed, so the layout has both incoming and outgoing traffic without a big staging yard.
**How it works:** `Brae Outside` stands for everywhere off the railroad. Its schedule `Outside World` has two lines: receive an empty and ship a load, and receive a load and ship an empty. An interchange can't have a schedule, so this has to be a spur. A plain spur swaps E and L by itself, and the schedule makes the swap explicit.
**Set it up:** Add a spur with a schedule of two lines, one for each load, in Match mode. Ask Claude: "Make Brae Outside a rest-of-the-world spur that sends cars back loaded."
**Find it:** `Brae Outside`, `Carrow Outside Lead`, `Outside World`, `LOCAL-B`, `OUTX 1`, `OUTX 2`
**See it work:** After the first session OUTX 1 is on Brae Outside with a load, and OUTX 2 is on Carrow Outside Lead as an empty. The next session swaps them.
**Try this:** Ask Claude to remove the schedule. It notes that the schedule was unused, and a session gives the same loads, because a plain spur flips empties and loads by itself.

### R18. A descriptive interchange

**What you can build:** An interchange that stands for a connecting railroad, with no physical track.
**Why you'd want it:** You can show a connection with another railroad where there's no room to model it. Crews get the paperwork and the traffic, and the cars move in the files.
**How it works:** `Northern Connection` is a track in the Operations files only. `EAST FREIGHT` sets cars out on it and `TURN` pulls them. A set out list and a pick up list keep the track to these two trains. Because nothing is physically there, it is your choice how the cars get handled at the layout.
**Set it up:** In Edit Classification/Interchange Track, under Select trains or routes for set outs and for pick ups, choose Trains and name them. Add a Comment saying it is not a physical track. Ask Claude: "Add Northern Connection, set out by EAST FREIGHT and pulled by TURN."
**Find it:** `Northern Connection`, `Turn A`, `EAST FREIGHT`, `TURN`, `CNXX 1`
**See it work:** In the first session `EAST FREIGHT` sets CNXX 1 on Northern Connection. In the next, `TURN` pulls it to Turn A, and the session after takes it to Turn B.

### R19. Staging to staging

**What you can build:** A train that runs from staging to staging, working a spur on the way and returning next session.
**Why you'd want it:** A through train with no home on the layout is a natural staging train. It runs out and back, doing some work on the way, then waits to run the other way.
**How it works:** `TURN` leaves one staging track and ends on the other. At Linden it sets out cars and picks up another. Allow cars to return to staging appears in the Options window as well as on the train.
**Set it up:** Give the train a route that starts and ends at the staging location. Allow cars to return to staging is in Train Build Options, from Tools in Edit Train. Ask Claude: "Set up TURN to run from Turn A to Turn B, working Linden Team."
**Find it:** `Turn A`, `Turn B`, `Linden Team`, `TURN`, `TRNX 1`, `TRNX 2`, `TRNX 3`
**See it work:** In the first session `TURN` leaves Turn A, sets TRNX 1 and 2 on Linden Team, picks up TRNX 3 and ends on Turn B. In the next it leaves Turn B, and TRNX 1 and 2 end on Turn A while TRNX 3 returns to Linden Team.
**Try this:** Ask Claude to turn off return to staging on `TURN`. On its own that changes nothing.

---

## Known limits

These are things the showcase leaves out, or that Claude can't tell you yet:

- A permanent custom load lost on arrival in staging is still an open problem, so no case builds it.
- Claude reads the files as they stand before a build. It can't always foresee what a build uses up along the way: moves, train length, or room taken by other cars bound for the same track. It says so when that applies, as in R09 and R14. A real build shows what happens.
- An automation that waits for a train it has itself terminated never finishes in JMRI 5.16. Use a second automation to do the terminating, as in U15.
- When Build on time stops a train in JMRI 5.16, there is no build report to read. Claude can still find out why by trying the build on a copy, as in U20.
- The plugin can't set a car's final destination by itself, add a car to a built train, write a train's build or terminate scripts, or change a track's type.
- Claude doesn't follow a load generated for a staging-to-staging move, so it can miss why such a car stays.
- Claude leaves two things to a real build: a locomotive with no track at the terminal, which fails that build, and overlapping dates in a staging pool.
- Answers can run long. Ask Claude for only what is failing, or for one name.
- A few overlaps are kept on purpose. After the first session the fiddle yard, `Carrow Box Factory` and `Carrow Glass Works` take boxcars from other cases, and `Carrow Salt Works` takes empty covered hoppers.

## The exact detail

Every case here was run in real JMRI 5.16. For the exact tool calls, the rule behind each answer and the tests, see REFERENCE.md beside this guide.
