# Routing, interchanges and filters

## The router

- Runs for any car with a final destination, whatever its load. It never runs for a default E or L without one, except through a home division.
- Tries up to seven trains. Hops go through interchanges first, then yards if "routing via yards" is on, default off, then staging if "routing via staging" is on, default off, and only staging tracks with no load-changing option.
- Needs room only at the first hop, and tests train length at the first hop only. The final spur may be full.
- If the first hop is full and a route exists, the car is sent to the current spur's alternate or a yard rather than held. Otherwise the car waits.
- If any single train can deliver the car directly, no two-train path is used. The train build option to service all cars with a final destination overrides that.
- "Could not find a first or last hop" in the report means a gap at a hop or no room there. The audit's `routing-gap` finding checks for a chain of trains between every shipping spur and every receiver.
- The router writes its lines to the report only at the Detailed and Very Detailed router levels.

## Alternates

- Only a spur can have an alternate. The alternate is used when the spur is full and shares a direction with it.
- An alternate never appears in any move-ordered track list, so it is never a direct destination and never a routing hop. "Can't send directly to alternate" is the report line.
- An interchange set as an alternate loses its exchange role and traps cars through the same-route rule. The audit reports `interchange-as-alternate` and `alternate-ignored`.
- For overflow on a yard or interchange use a pool, or move count bias.

## Interchanges

- A car set out on an interchange whose Pick ups is Any can only be pulled by a train on a **different route**. The test is by route id, so two trains on one route are both barred. Naming trains or routes in Pick ups lifts it.
- Routed, the "only cars with a final destination" option, exists on interchanges and staging. It refuses any car with no final destination, except cabooses and FRED cars. With it on, the custom search fallback cannot leave a car there.
- Pick ups and Set outs lists hold train or route ids and are read on interchanges and spurs. Yards return Any whatever is stored, and the audit reports `yard-pickup-list` and `yard-drop-list`. Changing the option from train to route clears the list.
- Interchanges can be descriptive rather than physical. That is a modelling choice.
- The `setup_interchange` action sets trains in, trains out, Routed and destinations in one step.

## The Destinations filter

- Holds **location** ids, not tracks, and exists on interchange and staging only. A filter on a yard or spur is ignored on read. The audit reports `destinations-ignored`.
- Exclude only inverts the checkboxes; the stored list is always the accepted locations. Writes keep that.
- As a gate on the car's track (D6, B8): the next location the train would use must be admitted, or the car has no exit. The audit reports `interchange-no-exit`.
- As a gate on the destination track (E6): the car's **final** destination must be admitted. A car with no final destination passes.
- Interim yards and interchanges are not tested, so excluding a yard does not stop a car passing through it. Either exclude every final destination reached through that yard, or turn on the EXTREME option in car routing, which tests each hop against the car's track.
- A filter that leaves out the location a schedule names makes the builder skip that spur and fall to the route search, so cars scatter. Accept all is the usual fix.

## Directions

- Direction is a bitmask on the location, the track and each route stop. The stop's direction must be served by the location (C4, D8) and by the track (C9, D14, G4). A local switcher is exempt.
- Enabling every direction on a location makes direction a filter tool rather than geography.
- The audit reports `route-direction-mismatch` for a stop the location cannot serve, and `track-direction-unserved` for a track no stop serves.

## Through cars, terminal and local moves

- "Allow cars to travel from origin to terminal" off blocks a car from the first stop to the last. Passenger cars, cabooses and FRED are exempt.
- "Send all car pick ups to terminal" sends cars picked up after the origin only to the terminal.
- A local switcher is a train whose stops all share one split name. Only a switcher, a passenger car, a caboose or a FRED car can be set out at the same split location; same-track moves are refused except for those cars.
- Spur to spur, yard to yard and interchange to interchange moves by a switcher each need their Settings option. Spur to spur is off by default, and so are the other two. The audit reports `switcher-local-off`.
- A car moves once per train, except through quick service tracks, which pull clones.

## Hyphen names

A location name splits only when the text after a hyphen is a whole number or starts with `(`. So `Town-(yard)` and `Town-2` print as Town, while `Town-yard` stays two words and does not split. The split name is what paperwork shows and what the same-location rules compare. Location objects stay separate, so different trains can work them. The audit reports `hyphen-no-split`.

## Divisions

Locations and cars carry a division. A car with a home division and no final destination gets one before the load test, by load type. An empty goes home: a home yard first, then home staging, then a home spur. A load on a track outside its division goes to a home spur or home staging. A load already at home goes to any spur or staging. A custom empty counts as empty. Cars with no division are unaffected.

## Checking a setup

The Track Destinations tool and the check destinations tool warn about types a destination does not service. The build report is the judge. `ops_why_not` with a train named walks the router gates for a final destination.

Checked against JMRI 5.16 source, tag v5.16.
