# Operations Pro showcase: guide

This is a tour of the Juniper Falls & Northern, an invented railroad built to show what JMRI Operations Pro can do. Each case is something you can build on your own railroad, shown working. Some are setups that people on the JMRI user list asked about. The rest cover the ways a car can be routed.

You don't need to know how the plugin works inside. You ask Claude in plain words and it answers from the railroad's files. The questions below are examples, so put them your own way.

## How to use it

Copy the operations folder into a scratch JMRI profile, or point Claude at it. Nothing in it needs changing, and the active day is Tuesday.

Pick a case. Each one follows the same order:

| Heading | What it gives you |
|---|---|
| What you can build | The result, in a sentence |
| How it works | The idea, and the JMRI setting behind it |
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
**How it works:** The spur has to accept empties before its schedule can load them. Brae Feed Mill's load options let an empty in, and the first line of its schedule receives it. The car leaves with Feed for the dairy.
**Find it:** `Brae Feed Mill`, `Dunmere Dairy`, `Feed Mill Loading`, `Dairy Receiving`, `LOCAL-B`, `JFN 101`, `JFN 102`
**See it work:** Ask "Can JFN 101 go to Brae Feed Mill on LOCAL-B?" Claude says yes. After the first session JFN 101 is on the mill with Feed, bound for Dunmere Dairy. In the next session it reaches the dairy.
**Try this:** Ask Claude to set Brae Feed Mill to accept only Feed. The hopper can no longer go there, and Claude says why: the mill no longer takes an empty hopper.

### U02. A schedule applied to a car already on a spur

**What you can build:** A schedule added to a spur that already holds a car, with that car taking its load and destination from the schedule.
**How it works:** A car already on the spur has to be given the schedule. JMRI's Set Car window has an option to apply it, and JFN 201 was set up that way on Brae Cannery. It carries the schedule's load and final destination.
**Find it:** `Brae Cannery`, `Cannery`, `Grocery Dock`, `Grocery Receiving`, `JFN 201`
**See it work:** Ask "What load and final destination does JFN 201 have?" It has Canned, bound for Grocery Dock. After the first session it is at Grocery Dock as an empty, and the `LOCAL-B` manifest shows it set out there.
**Try this:** Ask Claude to place a boxcar on Brae Cannery without applying the schedule, then to check the railroad. Claude reports that the schedule was not applied to that car.

### U03. Custom loads give cars a purpose

**What you can build:** Cars that travel for a reason: each carries a custom load to a named customer, while default cars stay on a yard.
**How it works:** JFN 301 and JFN 302 were given a Lumber load and a final destination, so they go to Lumber Dealer. `WNDR 1` and `WNDR 2` are default cars with no schedule. Dunmere Yard takes them, and they only ever sit on a yard.
**Find it:** `Brae Lumber`, `Lumber Dealer`, `Lumber Shipping`, `Lumber Receiving`, `Dunmere Yard`, `JFN 301`, `JFN 302`, `WNDR 1`, `WNDR 2`
**See it work:** After the first session both Lumber cars are at Lumber Dealer as empties. Ask "Can WNDR 1 go to Brae Lumber on LOCAL-B?" Claude says no, and lists the type, road and load as the reasons.
**Try this:** Ask Claude to remove the schedule from Lumber Dealer. It only notes the unused schedule. In a session the Lumber cars still reach the spur, because it is their final destination.

### U04. A local move inside one location

**What you can build:** A move inside one location: a one-stop route that takes a car from the yard to a spur in the same town.
**How it works:** `SAWYER SWITCHER` has a route with one stop, and that stop allows local moves. JFN 401 carries Semolina from Sawyer Yard to the spur that receives it.
**Find it:** `Sawyer`, `Sawyer Yard`, `Sawyer Pasta Plant`, `Sawyer Pasta Plant Schedule`, `SAWYER SWITCHER`, `JFN 401`
**See it work:** After the first session JFN 401 is on Sawyer Pasta Plant. Ask "Can JFN 401 go to Sawyer Pasta Plant on SAWYER SWITCHER?" Claude says yes, with nothing in the way.
**Try this:** Ask Claude to turn off pick ups and local moves at that stop. The build moves no cars, and Claude explains why.

### U05. Move counts and priority

**What you can build:** Control over which track gets the cars, using move counts, which win here over a High priority.
**How it works:** Each track keeps a count of its moves, and JMRI tries the lowest count first. Hollis Track 1 has High priority but 100 moves. Hollis Track 2 has no priority and no moves, so it gets the cars.
**Find it:** `Hollis Mill`, `Hollis Track 1`, `Hollis Track 2`, `LOCAL-H`, `GNDX 501`, `GNDX 502`, `GNDX 503`
**See it work:** After the first session all three gondolas are on Hollis Track 2. Ask "What order will GNDX 501 try the tracks at Hollis Mill on LOCAL-H?" Claude puts Hollis Track 2 first.
**Try this:** Ask Claude to set Hollis Track 2 to 200 moves. The order turns round, and the first session puts all three cars on Hollis Track 1.

### U06. Departure staging with generated custom loads

**What you can build:** Departure staging that sends out cars with a purpose: tracks give cars a generated load, and they go on to the industries that receive it.
**How it works:** `West Custom` holds only cars that leave with a generated load, Machinery, and it refuses empties. `West Mixed` ships Machinery and empties. Two depots receive the Machinery.
**Find it:** `West Custom`, `West Mixed`, `East Mixed`, `Brae Depot`, `Dunmere Depot`, `CUSTOM`, `MIXED`, `JFN 601`, `JFN 611`, `JFN 614`
**See it work:** Ask "Why did JFN 601 go where it did on CUSTOM?" Claude explains that the staging track gave it a Machinery load and sent it through Carrow Yard to Brae Depot. In the next session `LOCAL-B` delivers it there and it comes off as an empty. `MIXED` carries JFN 611 to 613 toward a depot, and JFN 614 leaves as an empty for East Mixed.
**Try this:** Ask Claude to remove both depot schedules. It notes only that they are unused, and the train still builds. West Custom can also load a car for a staging track, so the car goes toward East Mixed instead.

### U07. Two staging tracks swapping full trains

**What you can build:** Two staging tracks that swap full trains in one session, and swap back in the next.
**How it works:** A staging track full of cars would normally block the train coming in. `West Swap` and `East Swap` both use planned pick ups at 100 percent, so each track counts its cars as already leaving.
**Find it:** `West Swap`, `East Swap`, `SWAP-E`, `SWAP-W`, `SWPX 1`, `SWPX 11`, `JFN 51`, `JFN 53`
**See it work:** In the first session `SWAP-E` takes SWPX 1 to 6 to East Swap, and `SWAP-W` takes SWPX 11 to 16 to West Swap. That is 12 cars in one session. The next session reverses them.
**Try this:** Ask Claude to set East Swap's planned pick ups to 0. Claude warns about it first. `SWAP-E` then fails to build because East Swap is occupied, and `SWAP-W` still builds.

### U08. A fiddle yard of virtual spurs

**What you can build:** A fiddle yard of virtual spurs: their schedules send cars on to named customers, with a random line to vary the traffic.
**How it works:** `Fiddle North` and `Fiddle South` are spurs whose schedule lines name the track the car goes to next. The south line is set to random 25 percent, with a wait of one, so traffic varies.
**Find it:** `Fiddle North`, `Fiddle South`, `Parts Depot`, `Tool Depot`, `Parts Receiving`, `Tools Receiving`, `FIDDLE JOB`, `JFN 801`, `JFN 802`, `JFN 803`, `JFN 804`, `JFN 805`, `JFN 806`
**See it work:** `FIDDLE JOB` takes all six cars to the fiddle yard. Cars on Fiddle North carry Parts for Parts Depot, and cars on Fiddle South carry Tools for Tool Depot from the second session. By the third session more Parts cars have been delivered than Tools cars.
**Try this:** Ask Claude to take the random setting off Fiddle South. Both of its lines then work like Fiddle North's.

### U09. One schedule for several spurs

**What you can build:** One schedule shared by several spurs, with nothing to copy.
**How it works:** `Grain Receiving` is assigned to both elevators. There is one schedule to keep up.
**Find it:** `Elevator A`, `Elevator B`, `Grain Receiving`, `JFN 901`, `JFN 902`
**See it work:** Ask "What schedule do Elevator A and Elevator B use?" Both use the same one. After the first session one car sits empty on each elevator.
**Try this:** Ask Claude to copy the schedule and point Elevator B at the copy. It works and Claude raises nothing, so sharing is your choice.

### U10. A mixed default and custom spur

**What you can build:** One industry that takes both default and custom cars, using a second virtual spur, with one name on the paperwork.
**How it works:** `Freight House` takes the default cars, and a second spur, `Freight House-(2)`, takes the Crates line. JMRI leaves off the hyphen and what follows when it prints a name.
**Find it:** `Freight House`, `Freight House-(2)`, `Crates Receiving`, `FRHX 1`, `JFN 1001`
**See it work:** After the first session FRHX 1 is on Freight House and JFN 1001, with Crates, is on Freight House-(2). The `LOCAL-B` manifest says "to Freight House" for both.
**Try this:** Ask "Can FRHX 1 go to Freight House-(2)?" Claude says no, because that spur's schedule line receives Crates and the car is empty.

### U11. Spurs and yards in balance

**What you can build:** A spur that keeps working when full: the train that brings new cars pulls the old ones, and cars return to their own lead.
**How it works:** `Mill Spur` holds two cars. Planned pick ups let it take new cars while the same train pulls the old ones. Cars of road MILX return to their own lead.
**Find it:** `Mill Spur`, `Bakery`, `Carrow Mill Lead`, `Mill Flour`, `Bakery Receiving`, `MILX 1101`, `MILX 1102`, `MILX 1103`, `MILX 1104`
**See it work:** After the first session two cars are on Mill Spur with Flour for Bakery, and two are on Carrow Mill Lead. In the second session the first pair reaches Bakery and the second pair is on the spur. In the third, the second pair is at Bakery and the first pair is back on the lead.
**Try this:** After the first session on a copy, ask Claude to set Mill Spur's planned pick ups to 0. Claude says the track is full, and the next session leaves the spur empty.

### U12. Normal and aggressive mode

**What you can build:** A staging train with a locomotive change that builds in both normal and aggressive mode.
**How it works:** `MODE` changes locomotives at Brae and ends in staging. Aggressive is a build option, and this train works with it on or off.
**Find it:** `West Mode`, `East Mode`, `Brae Stockyard`, `MODE`, `MODX 1`, `MODX 2`, `MODX 3`, `MODX 4`, `MODX 5`
**See it work:** In the first session five cars leave West Mode, one for Brae Stockyard and four for East Mode. Ask "Does anything change if I turn on aggressive mode?" Claude compares the builds and finds no change.
**Try this:** With aggressive on, ask Claude to limit the MODE stop at Brae to a train length of 100 feet. MODE fails to build. Claude says the train would be 4 feet over leaving Brae, and that 2 cars leaving staging have nowhere to go.

### U13. Caboose, kernel, locomotive change and consist

**What you can build:** Trains with the right equipment: a required caboose, a kernel that stays together, a locomotive change, and consists that swap ends.
**How it works:** `LOCAL-H` requires a caboose. The kernel `Brae Set` moves as one. `MODE` changes locomotives at Brae. The consists `West Pair` and `East Pair` swap ends with their trains.
**Find it:** `Carrow Caboose Track`, `Dunmere Team`, `Brae Set`, `Brae Engine Track`, `LOCAL-H`, `LOCAL-B`, `MODE`, `SWAP-E`, `SWAP-W`, `JFN 1301`, `JFN 1302`, `KRNX 1`, `KRNX 2`, `KRNX 3`, `JFN 51`, `JFN 55`, `JFN 56`, `JFN 57`
**See it work:** Every `LOCAL-H` build carries one of the two cabooses and sets it out on Carrow Caboose Track, taking turns. KRNX 1 to 3 stay together on Dunmere Team. The `MODE` manifest says "Locomotive change at Brae".
**Try this:** Ask Claude to let any route pick up from Carrow Caboose Track. It warns you first. Over three sessions `LOCAL-H` takes one caboose, then the other, then fails to build, because a car won't leave the track on the route that set it out.

### U14. Train schedule days

**What you can build:** Operating days: each day has its own list of trains, and a schedule line can set cars out on one day only.
**How it works:** Tuesday lists all 18 trains and Saturday lists six. Tuesday is the active day and has been applied, which sets each train's Build box. The schedule line `Tuesday Dock` sets cars out on Tuesday only.
**Find it:** `Tuesday`, `Saturday`, `Tuesday Dock`, `Brae Day Track`, `DAYX 1`, `LOCAL-B`
**See it work:** Ask "What days are set up?" Tuesday has 18 trains, Saturday has 6, and Tuesday is active. The build report says so too. After the first session DAYX 1 is on Tuesday Dock.
**Try this:** Ask Claude to make Saturday the active day and apply it. JMRI then builds exactly the six Saturday trains. DAYX 1 can't go to Tuesday Dock, and Claude gives both reasons: `LOCAL-B` is not on the list, and the line is for Tuesday.

### U15. An automation

**What you can build:** An automation that builds and terminates a session's trains in the order you choose, with no dialog to stop it.
**How it works:** `Evening Session` builds `LOCAL-H` and `LOCAL-B`, then runs `Close Out`, which terminates `LOCAL-B`. It waits for that, then terminates `LOCAL-H`. It is not the startup automation.
**Find it:** `Evening Session`, `Close Out`, `LOCAL-H`, `LOCAL-B`
**See it work:** Ask "What are the steps in Evening Session?" It has five. Set as the startup automation on a copy, real JMRI ran all five, and both trains ended not built.
**Try this:** Ask Claude to add a yes or no message step. It refuses unless you tell it dialogs are allowed.

### U16. Manual build lines

**What you can build:** A train that takes one chosen car, using a manual build line.
**How it works:** A manual build line on `LOCAL-H` tells it to take TEMX 1 from Hollis Team.
**Find it:** `Hollis Team`, `Oakhaven Team`, `LOCAL-H`, `TEMX 1`
**See it work:** The first session puts TEMX 1 on Oakhaven Team. Ask "Why did TEMX 1 move on LOCAL-H?" Claude points to the manual build line.
**Try this:** Ask Claude to delete the line and set the Hollis stop to 1 move. TEMX 1 stays on Hollis Team.

### U17. Paperwork

**What you can build:** Paperwork of your own: colours, font, a valid line, a track field, changed phrases and a railroad name for one train.
**How it works:** The manifest has red pick ups, blue set outs and green local moves, in font size 10. It prints a valid line and a track field on pick up lines. One train, `LOCAL-B`, has its own railroad name. An apostrophe in a phrase has to be doubled.
**Find it:** `LOCAL-B`, `FIDDLE JOB`
**See it work:** The `LOCAL-B` manifest starts "Brae Branch Lines" and prints "Conductor's copy, valid ..." with one apostrophe. `FIDDLE JOB` prints JMRI's default, "My JMRI Railroad", because the railroad has no name set.
**Try this:** Ask Claude to set the valid line to "Valid {0". It refuses, because a brace has to open a numbered value such as {0}.

### U18. Passenger blocking

**What you can build:** A passenger train whose cars stay in the order you set, on station spurs only it serves.
**How it works:** FLYX 1 to 5 have blocking numbers -5, 10, 20, 40 and 70. The station spurs serve `VALLEY FLYER` only.
**Find it:** `Carrow Station`, `Northwood Station`, `VALLEY FLYER`, `FLYX 1`, `FLYX 2`, `FLYX 3`, `FLYX 4`, `FLYX 5`
**See it work:** The `VALLEY FLYER` manifest picks up FLYX 1, 2, 3, 4 and 5 in that order, and sets all five out at Northwood Station.
**Try this:** Ask Claude to set FLYX 5's blocking number to -9. FLYX 5 is then picked up first.

### U19. Track pools

**What you can build:** A pool of tracks that share their length, with a minimum and maximum on each.
**How it works:** `Hollis Pool` has two tracks. Pool 1 is 100 feet, with a minimum of 100 and a maximum of 150. Pool 2 is 300 feet, with a minimum of 100. A track can borrow length from the other.
**Find it:** `Hollis Pool 1`, `Hollis Pool 2`, `Hollis Pool`, `POOX 1901`, `POOX 1902`, `POOX 1903`, `POOX 1904`, `POOX 1905`, `POOX 1906`
**See it work:** The first session spreads six 40-foot flatcars three and three. Pool 1 borrows length to do it, and stays between its 100 and 150.
**Try this:** Ask Claude to raise Pool 1's minimum to 350. It refuses, because the minimums would add up to more than the pool's 400 feet.

### U20. On-time build order

**What you can build:** Trains with departure times, and the choice of whether they must be built in that order.
**How it works:** `FIDDLE JOB` departs at 08:45, `LOCAL-B` at 09:00 and `LOCAL-H` at 10:00. The option "Build on time" is off here.
**Find it:** `LOCAL-B`, `LOCAL-H`, `FIDDLE JOB`
**See it work:** With the option off, you can build `LOCAL-H` in one session and `LOCAL-B` in the next, and both build.
**Try this:** Ask Claude to turn on Build on time, build `LOCAL-H`, then build `LOCAL-B`. `LOCAL-B` is refused because it departs earlier. JMRI shows Error and writes no build report, so ask Claude why. Changing `LOCAL-B` to depart at 11 clears it.

### U21. Divisions

**What you can build:** Cars that go home: a home division sends empties to the home yard and loads to the home spur.
**How it works:** Northwood is in the division `North`, and the NWRX cars have it as their home division. JMRI gives them a final destination when the train builds.
**Find it:** `North`, `Northwood Yard`, `Malt House`, `Malt House Receiving`, `NWRX 1`, `NWRX 2`, `NWRX 3`
**See it work:** `EAST FREIGHT` takes NWRX 1 to 3 to Ferris Yard. NWRX 1 and 2 are bound for Northwood Yard and NWRX 3 for Malt House. In the next session `NORTH JOB` delivers them.
**Try this:** Ask Claude to clear NWRX 1's home division. It gets no final destination after the first session, but it still reaches Northwood Yard in the next.

### U22. Hazmat, buffer and idler cars, LCL

**What you can build:** Special traffic: a buffer car, hazardous tank cars, idlers in a kernel that print as one load, and an LCL boxcar on a dock.
**How it works:** On `TURN`, HZMX 9 is a Buffer that rides first out of staging. HZMX 1 to 3 are hazardous tank cars for Linden Refinery. HZMX 11 to 13 are the kernel `Girder Load` for Linden Steel, and the idlers print as Girder. LCLX 1 is a boxcar marked as passenger that works as less-than-carload on a dock.
**Find it:** `Turn A`, `Turn B`, `Linden Refinery`, `Linden Steel`, `Girder Load`, `Carrow LCL Dock`, `TURN`, `HZMX 9`, `HZMX 3`, `HZMX 12`, `LCLX 1`
**See it work:** The `TURN` manifest lists HZMX 9 Buffer as the first pick up, and shows HZMX 3 as hazardous. LCLX 1 is on Carrow LCL Dock after every session, and the `LOCAL-B` manifest shows both its pick up and its set out.
**Try this:** Ask Claude to turn off the passenger setting on HZMX 9. It no longer rides, and the manifest shows a move from Turn A to Turn B instead of a pick up.

### U23. Backups

**What you can build:** A backup set you can return to after a bad change.
**How it works:** The folder holds one backup set. Claude also takes a backup before every change it makes.
**Find it:** (the `backups/` folder, no object)
**See it work:** Ask "What backups do I have?" Claude lists the set: six files, complete. On a scratch copy, ask Claude to delete a car and then restore that backup. The car comes back.

### U24. A RIP track

**What you can build:** A RIP track where a loaded car keeps its load on arrival.
**How it works:** `Carrow RIP` has "Disable load change" set, so a car arrives with the load it left with.
**Find it:** `Carrow RIP`, `Hollis Shop Lead`, `LOCAL-H`, `RIPX 1`
**See it work:** In the first session `LOCAL-H` takes RIPX 1 from Hollis Shop Lead to Carrow RIP, and it stays loaded.
**Try this:** Ask Claude to clear that setting. RIPX 1 then arrives empty.

---

## Part 2: routing variations

Each case here has one car that shows the route. Ask whether the car can reach a place on a named train, and Claude tells you the route JMRI 5.16 takes. Cases R01 to R05 and R19 start simple and grow. The rest show the settings that steer a route.

### R01. One train direct

**What you can build:** A car delivered by one train, with the schedule turning its load into an empty.
**How it works:** `LOCAL-H` reaches the spur itself, so no routing is needed. The schedule at Oakhaven Cannery takes the peas and makes the car an empty.
**Find it:** `Oakhaven Cannery`, `Cannery Peas`, `LOCAL-H`, `JFN 5101`
**See it work:** Ask "Can JFN 5101 go to Oakhaven Cannery on LOCAL-H?" Claude says yes, on a single train. The first session puts it on the spur as an empty.
**Try this:** Ask Claude to turn off set outs for `LOCAL-H` at Oakhaven. The car can no longer go there, and Claude says the stop does not set out cars.

### R02. Two trains through an interchange

**What you can build:** A car that changes trains at an interchange to reach a customer one train cannot serve.
**How it works:** `EAST FREIGHT` doesn't go to Northwood, so JMRI routes the car through the interchange at Ferris Exchange, and `NORTH JOB` finishes the trip.
**Find it:** `Ferris Exchange`, `Carrow Packing`, `Cold Store`, `EAST FREIGHT`, `NORTH JOB`, `JFN 5201`
**See it work:** Ask "Can JFN 5201 go to Cold Store on EAST FREIGHT?" Claude says yes, by two trains through Ferris Exchange. The first session leaves it there with Produce, and the next puts it on Cold Store as an empty.
**Try this:** Ask Claude to let Ferris Exchange send cars only to Linden. Claude blocks the change. In a build the car would stay at Carrow Packing with no destination.

### R03. Two trains through a yard

**What you can build:** A car that changes trains at a yard, with moves deciding which yard it uses.
**How it works:** Routing via yards is on. The foundry car rides `LOCAL-H` to Carrow Transfer, then `EAST FREIGHT` to the pipe yard. Carrow Transfer is chosen because it has fewer moves than Carrow Yard, so keep its moves at 0.
**Find it:** `Oakhaven Foundry`, `Carrow Transfer`, `Linden Pipe Yard`, `Foundry Casting`, `LOCAL-H`, `EAST FREIGHT`, `JFN 5301`
**See it work:** Ask "Can JFN 5301 go to Linden Pipe Yard on LOCAL-H?" Claude says yes, by two trains through Carrow Transfer. The first session takes it there, and the next takes it to the pipe yard.
**Try this:** Ask Claude to turn off routing via yards. Claude then finds no route, yet the car gets there anyway, because from Carrow it is a one-train trip. The option changes the answer here, not the result.

### R04. A chain of three trains

**What you can build:** A car carried by a chain of three trains, with a relay track between each.
**How it works:** No one train covers the trip. `LOCAL-H` reaches Carrow Relay, `EAST FREIGHT` reaches Ferris Relay, and `NORTH JOB` reaches Northwood Steel.
**Find it:** `Hollis Coil Mill`, `Carrow Relay`, `Ferris Relay`, `Northwood Steel`, `Coil Mill Shipping`, `LOCAL-H`, `EAST FREIGHT`, `NORTH JOB`, `JFN 5401`
**See it work:** Ask "Can JFN 5401 go to Northwood Steel on LOCAL-H?" Claude says yes, by 3 trains. The car moves one leg each session, and after the third it is at Northwood Steel as an empty.
**Try this:** Ask Claude to let Ferris Relay send cars only to Linden. Claude blocks the change. In a build the car would stop on Carrow Relay.

### R05. A route through staging

**What you can build:** A car routed through a staging track, to reach a spur its first train cannot serve in that direction.
**How it works:** Linden Pier can't be worked by an eastbound train. So `EAST FREIGHT` sets the car in staging on `Hop`, and `HOP OUT` brings it back the other way.
**Find it:** `Hop`, `Linden Pier`, `Carrow Salt Works`, `EAST FREIGHT`, `HOP OUT`, `JFN 5501`, `JFN 5502`
**See it work:** Ask "Can JFN 5501 go to Linden Pier?" Claude says yes, by two trains through staging at Hop. The first session sets it on Hop, and the next takes it to Linden Pier.
**Try this:** Ask Claude to turn off routing via staging. Claude then finds no route. `EAST FREIGHT` no longer takes the car, and `LOCAL-B` carries it to Dunmere Yard instead.

### R06. A Destinations filter as a gate

**What you can build:** An interchange that sends cars on to one destination only.
**How it works:** The Destinations filter on `Ferris Gate` lets cars go only to Pell Creek-(yard). So the car goes to `Pell Tank Track`, not `Gate Yard`.
**Find it:** `Ferris Gate`, `Pell Tank Track`, `Gate Yard`, `NORTH JOB`, `GTEX 1`
**See it work:** Ask "Can GTEX 1 go to Gate Yard on NORTH JOB?" Claude says no, and names the filter. The first session sets it on Pell Tank Track.
**Try this:** Ask Claude to set Ferris Gate's destinations to all. The first session then puts the car on Gate Yard.

### R07. Pick ups named by route

**What you can build:** A track whose pick ups are named by route, so the route that set a car out can pull it back.
**How it works:** A car set out on an interchange won't normally leave on the route that brought it. `Ferris Transfer` names `NORTH JOB`'s route in its pick ups, which allows it.
**Find it:** `Ferris Transfer`, `Northwood Shed`, `NORTH JOB`, `XFRX 1`
**See it work:** In the first session `NORTH JOB` sets XFRX 1 on Ferris Transfer. In the next, the same route pulls it back to Northwood Shed.
**Try this:** After the first session on a copy, ask Claude to set Ferris Transfer's pick ups to Any. The next build leaves XFRX 1 behind.

### R08. The Routed option

**What you can build:** Tracks that take routed cars only, while other cars go elsewhere.
**How it works:** `Ferris Routed` and `Hop` are set to take only cars that have a final destination.
**Find it:** `Ferris Routed`, `Hop`, `Routed Siding`, `Carrow Box Factory`, `Box Factory Loads`, `JFN 5801`, `BOXX 1`
**See it work:** Ask "Can BOXX 1 go to Ferris Routed?" Claude says no, because the car has no final destination. JFN 5801 has one. The first session puts it on Ferris Routed and BOXX 1 on Ferris Yard, and the next takes JFN 5801 to Routed Siding.
**Try this:** Ask Claude to turn off that setting on Ferris Routed. The first session then puts BOXX 1 there.

### R09. An alternate, then forward to yard

**What you can build:** An industry with an alternate track and a yard behind it, so cars still move when the spur is full.
**How it works:** `Oakhaven Plant` has `Plant Overflow` as its alternate track. When both are full, "forward to yard" sends the car to Oakhaven Yard, with the plant still as its final destination.
**Find it:** `Oakhaven Plant`, `Plant Overflow`, `Oakhaven Yard`, `Plant Stone`, `LOCAL-H`, `JFN 5901`, `JFN 5902`, `JFN 5903`, `JFN 5904`
**See it work:** In the first session four hoppers go out. Two reach Oakhaven Plant, one reaches Plant Overflow and one reaches Oakhaven Yard. Which car goes where depends on build order. Ask "Why did JFN 5901 go where it did on LOCAL-H?" Claude walks through the full tracks.
**Try this:** Ask Claude to turn off forward to yard. The car that would have gone to the yard stays on Hollis Quarry. The other three go as before.

### R10. Overflow handled by a pool

**What you can build:** Two interchanges in a pool, sharing their length so a whole cut of cars fits.
**How it works:** `Ferris Pool 1` and `Ferris Pool 2` are 120 feet each and share their length as `Ferris Pool`.
**Find it:** `Ferris Pool 1`, `Ferris Pool 2`, `Ferris Pool`, `Carrow Grain Co`, `Grain Elevator`, `OAKX 1`, `OAKX 2`, `OAKX 3`, `OAKX 4`, `OAKX 5`
**See it work:** Five 44-foot cars all fit, three and two, and none is left at Carrow Grain Co. In the second session all five are at Grain Elevator.
**Try this:** Ask Claude to remove the pool. Only two cars fit on each track, and OAKX 1 is left behind.

### R11. An A/D track with a switcher

**What you can build:** A yard worked in two steps: a transfer sets cars on an A/D track, and a switcher sorts them to the class tracks.
**How it works:** `KESSOCK TRANSFER` brings the cars to `Kessock A/D`. `KESSOCK SWITCHER` then moves them to the class tracks. The build option that allows local interchange moves is on.
**Find it:** `Kessock A/D`, `Kessock Class 1`, `Kessock Class 2`, `KESSOCK TRANSFER`, `KESSOCK SWITCHER`, `KESX 1`, `KESX 2`, `KESX 3`, `KESX 4`
**See it work:** In the first session KESX 1 to 4 arrive on Kessock A/D. In the next, the switcher moves all four to the class tracks, two on each.
**Try this:** Ask Claude to turn off that build option. The build moves no cars, and a check of the railroad warns about it.

### R12. A local switcher

**What you can build:** A local switcher that works spur to spur and yard to yard.
**How it works:** `SAWYER SWITCHER` works inside Sawyer. Build options allow local spur moves and yard moves.
**Find it:** `Sawyer Warehouse`, `Sawyer Yard 1`, `Sawyer Yard 2`, `SAWYER SWITCHER`, `SWYX 1`, `SWYX 2`
**See it work:** In the first session SWYX 1 moves spur to spur onto Sawyer Warehouse, and SWYX 2 moves yard to yard onto Sawyer Yard 2.
**Try this:** Ask Claude to turn off local spur moves. SWYX 1 stays put and SWYX 2 still moves, because yard to yard has its own option.

### R13. Through-car rules

**What you can build:** A train with through-car rules, which limit the cars it carries to its terminal.
**How it works:** `THRU` won't carry a car from its first stop straight to its terminal. Cars it picks up along the way go to the terminal, not to the next stop.
**Find it:** `Dunmere Oil`, `Ferris Yard`, `THRU`, `OILX 1`, `OILX 2`
**See it work:** In the first session OILX 1 stops at Dunmere Oil, and OILX 2 goes to Ferris Yard.
**Try this:** Ask Claude to allow through cars on `THRU`. Both cars then go to Ferris Yard.

### R14. Service all cars with a final destination

**What you can build:** A choice of what a train does with final-destination cars when the stop they need is short of moves.
**How it works:** `EAST FREIGHT` has "service all" on. It matters only when the stop runs out of moves. As shipped, Linden has 20 moves, so both cars reach Linden Glazier in the first session either way.
**Find it:** `Carrow Glass Works`, `Linden Glazier`, `EAST FREIGHT`, `JFN 6401`, `JFN 6402`
**See it work:** The difference shows only on a copy with the Linden stop cut to 1 move, as below. Claude can't tell ahead of time how a build's moves will run out, so ask it to explain the build afterward.
**Try this:** On a copy, ask Claude to set the Linden stop to 1 move and try service all both ways. With it off, neither car moves. With it on, JFN 6402 goes to Ferris Yard and JFN 6401 to Carrow Yard, and they reach Linden Glazier over two trains.

### R15. Directions

**What you can build:** A track served from one direction, so only a train running that way works it.
**How it works:** `Linden Westside` is set for westbound trains. `EAST FREIGHT` is eastbound there and `HOP OUT` is westbound.
**Find it:** `Linden Westside`, `Carrow West Lead`, `EAST FREIGHT`, `HOP OUT`, `WSTX 1`
**See it work:** Ask "Can WSTX 1 go to Carrow on EAST FREIGHT?" Claude says no, and names the direction. On `HOP OUT` it can. The first session sets it on Carrow West Lead.
**Try this:** Ask Claude to set Linden Westside to both directions. `EAST FREIGHT` then takes the car to Hop, and `HOP OUT` brings it to Carrow West Lead in the next session.

### R16. Hyphen-named locations

**What you can build:** One town split into two locations that prints as one name on the paperwork.
**How it works:** `Pell Creek-(yard)` and `Pell Creek-(industries)` are two locations. JMRI leaves off the hyphen and what follows when it prints, so crews see Pell Creek.
**Find it:** `Pell Creek-(yard)`, `Pell Creek-(industries)`, `Pell Yard`, `Pell Brickworks`, `PELL SWITCHER`, `PELC 1`, `PELC 2`
**See it work:** In the first session `PELL SWITCHER` moves PELC 1 and 2 to Pell Brickworks. The manifest says "Scheduled work at Pell Creek" and shows neither ending.
**Try this:** Ask Claude to rename a location to `Pell Creek-industries`. It warns about the hyphen. The cars still move, and the change shows in the name on the paperwork.

### R17. A rest-of-the-world interchange

**What you can build:** A rest-of-the-world interchange, where empties come back loaded and loads come back empty.
**How it works:** `Brae Outside` stands for everywhere off the railroad. Its schedule `Outside World` has two lines: receive an empty and ship a load, and receive a load and ship an empty.
**Find it:** `Brae Outside`, `Carrow Outside Lead`, `Outside World`, `LOCAL-B`, `OUTX 1`, `OUTX 2`
**See it work:** After the first session OUTX 1 is on Brae Outside with a load, and OUTX 2 is on Carrow Outside Lead as an empty. The next session swaps them.
**Try this:** Ask Claude to remove the schedule. It notes that the schedule was unused, and a session gives the same loads, because a plain spur flips empties and loads by itself.

### R18. A descriptive interchange

**What you can build:** An interchange that stands for a connecting railroad, with no physical track.
**How it works:** `Northern Connection` is a track in the Operations files only. `EAST FREIGHT` sets cars out on it and `TURN` pulls them.
**Find it:** `Northern Connection`, `Turn A`, `EAST FREIGHT`, `TURN`, `CNXX 1`
**See it work:** In the first session `EAST FREIGHT` sets CNXX 1 on Northern Connection. In the next, `TURN` pulls it to Turn A, and the session after takes it to Turn B.

### R19. Staging to staging

**What you can build:** A train that runs from staging to staging, working a spur on the way and returning next session.
**How it works:** `TURN` leaves one staging track and ends on the other. At Linden it sets out cars and picks up another.
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
