# schematic-maps on AnyRail's example layouts

Plugin 0.1.53 drew 37 of the 38 example layouts that AnyRail publishes at [anyrail.com/examples](https://www.anyrail.com/examples), with no hints or preferences: each plan's own track, read as it is.

## Credits

The layouts are the work of their designers, published by DRail Software, the maker of AnyRail, on its [examples page](https://www.anyrail.com/examples). Each one below carries the title and designer AnyRail gives it; "not credited" means the page names no one. The pictures are AnyRail's drawings of each plan, exported from AnyRail with the plan. The schematic sheets are this plugin's output. The plans themselves are not in this repository.

## How they were run

Each plan was opened in AnyRail and exported as JMRI XML, then drawn with `schematic plan` and `schematic draw --no-preferences`, on a Mac, three plans at a time, with a 600 s limit (900 s for the last three). A *big band* (100 or more switches, or 20 or more independent loops) gets the plugin's lighter search, which the run logs. *Faults* are places where two tracks cross or lie on top of each other on the sheet; *label faults* are labels that found no clear spot.

## Results

| Sample | Layout (as AnyRail titles it) | Designer | Switches | Time | Faults | Label faults | Search |
|---|---|---|---|---|---|---|---|
| [D1](#d1) | N: Russ Haigh, an oval mini On18 layout | Russ Haigh | 3 | 0.2 s | 0 | 0 of 7 | full |
| [D2](#d2) | N: Russ Haigh, a 24" x 48" mini On18 layout | Russ Haigh | 8 | 0.3 s | 0 | 0 of 13 | full |
| [D3](#d3) | N gauge 1200mm x 2400mm (4' x 8') | not credited | 22 | 3.6 s | 3 | 0 of 26 | full |
| [D4](#d4) | H0: A station with underground run around loop | not credited | 31 | 2.5 s | 0 | 0 of 35 | full |
| [D5](#d5) | N: Peter, Layout 5 | Peter | 15 | 0.2 s | 0 | 0 of 25 | full |
| [D6](#d6) | N: Jeff Partridge, Heavy Rail | Jeff Partridge | 1105 | no sheet (900 s limit) |  |  |  |
| [D7](#d7) | H0: Bill Coxe, Attic floor plan | Bill Coxe | 52 | 230 s | 1 | 0 of 57 | full |
| [D8](#d8) | N: Bert de Vries, Two stations | Bert de Vries | 23 | 1.9 s | 0 | 0 of 27 | full |
| [D9](#d9) | H0: Dave Gann, Hudson Central Railroad | Dave Gann | 21 | 3.1 s | 0 | 0 of 25 | full |
| [D10](#d10) | Chicago to St. Louis | Marc Shaw | 139 | 265 s | 12 | 8 of 145 | lighter |
| [D11](#d11) | H0: Eric Consemulder, club layout | Eric Consemulder | 105 | 22 s | 19 | 7 of 121 | lighter |
| [D12](#d12) | H0: Zoltán Rigó, Big Station | Zoltán Rigó | 48 | 3.8 s | 1 | 6 of 59 | full |
| [D13](#d13) | 00: Andy Hutcheon Loft layout | Andy Hutcheon | 40 | 313 s | 5 | 0 of 45 | full |
| [D14](#d14) | H0: Michael Carver | Michael Carver | 22 | 2.4 s | 0 | 0 of 31 | full |
| [D15](#d15) | H0: Rob Boone, Coal mine theme | Rob Boone | 26 | 0.5 s | 0 | 0 of 37 | full |
| [D16](#d16) | H0: Peter Hanenberg, Waldeck | Peter Hanenberg | 28 | 1.8 s | 0 | 0 of 32 | full |
| [D17](#d17) | H0: Alain Lissoir, Belgian Railways | Alain Lissoir | 164 | 578 s | 24 | 25 of 172 | lighter |
| [D18](#d18) | H0: Merv Hourigan, Newcastle Station | Merv Hourigan | 144 | 833 s | 2 | 11 of 167 | full |
| [D19](#d19) | H0: John MacDonald, Real water | John MacDonald | 24 | 8.7 s | 0 | 0 of 29 | full |
| [D20](#d20) | H0: Rien de Koning, Königsbach | Rien de Koning | 13 | 2.1 s | 1 | 0 of 18 | full |
| [D21](#d21) | H0: Jack Biermans, A large city layout | Jack Biermans | 20 | 5.6 s | 4 | 0 of 24 | full |
| [D22](#d22) | H0: Cambria Pine Railroad | Ray DeWeese | 32 | 1.3 s | 0 | 2 of 45 | full |
| [D23](#d23) | H0: Flats Industrial RR | Isaac Fabris | 15 | 0.4 s | 0 | 0 of 19 | full |
| [D24](#d24) | H0: Gateway Western Sub 6 | Isaac Fabris | 65 | 63 s | 11 | 0 of 69 | lighter |
| [D25](#d25) | H0: Mike Malley, Loft Layout | Mike Malley | 54 | 0.6 s | 0 | 3 of 73 | full |
| [D26](#d26) | On30/On18: Russ Haigh, FC&P layout | Russ Haigh | 29 | 3.7 s | 0 | 0 of 35 | full |
| [D27](#d27) | N gauge 4200mm x 2000mm (13.75' x 6.5') | not credited | 50 | 9.7 s | 1 | 0 of 56 | full |
| [D28](#d28) | N: Martin de Widt, Middeldam | Martin de Widt | 42 | 2.0 s | 0 | 0 of 50 | full |
| [D29](#d29) | N: Peter, Layout 2 | Peter | 7 | 0.3 s | 0 | 0 of 12 | full |
| [D30](#d30) | N: Allok, Radiata Springs | not credited | 12 | 0.4 s | 0 | 0 of 16 | full |
| [D31](#d31) | On3: Cambria Pine Railroad | Ray DeWeese | 24 | 12 s | 1 | 0 of 31 | full |
| [D32](#d32) | H0: Russ Haigh, On30 SSW layout | Russ Haigh | 19 | 0.3 s | 0 | 0 of 26 | full |
| [D33](#d33) | Passau | Chaz | 3 | 0.3 s | 0 | 0 of 7 | full |
| [D34](#d34) | Schwarzenberg | Christian | 92 | 573 s | 3 | 15 of 103 | full |
| [D35](#d35) | Christmas layout | Rich Erickson | 10 | 0.8 s | 2 | 0 of 15 | full |
| [D36](#d36) | Trix Express | Herman | 22 | 0.4 s | 0 | 0 of 30 | full |
| [D37](#d37) | Z: Chris Manvell, Exhibition layout | Chris Manvell | 40 | 46 s | 6 | 0 of 45 | full |
| [D38](#d38) | Z: Chaz, 69th Street Philadelphia | Chaz | 69 | 49 s | 8 | 1 of 75 | full |

## Sheets

Each picture links to the full-size file.

### D1

**N: Russ Haigh, an oval mini On18 layout**, designer: Russ Haigh. 3 switches.

<table><tr><td valign="top"><a href="plans/D1.jpg"><img src="plans/D1.jpg" width="200" alt="AnyRail drawing of N: Russ Haigh, an oval mini On18 layout"></a></td><td valign="top"><a href="sheets/D1.svg"><img src="sheets/D1.svg" width="560" alt="schematic sheet of sample 1"></a></td></tr></table>

### D2

**N: Russ Haigh, a 24" x 48" mini On18 layout**, designer: Russ Haigh. 8 switches.

<table><tr><td valign="top"><a href="plans/D2.jpg"><img src="plans/D2.jpg" width="200" alt="AnyRail drawing of N: Russ Haigh, a 24" x 48" mini On18 layout"></a></td><td valign="top"><a href="sheets/D2.svg"><img src="sheets/D2.svg" width="560" alt="schematic sheet of sample 2"></a></td></tr></table>

### D3

**N gauge 1200mm x 2400mm (4' x 8')**, designer: not credited. 22 switches.

<table><tr><td valign="top"><a href="plans/D3.jpg"><img src="plans/D3.jpg" width="200" alt="AnyRail drawing of N gauge 1200mm x 2400mm (4' x 8')"></a></td><td valign="top"><a href="sheets/D3.svg"><img src="sheets/D3.svg" width="560" alt="schematic sheet of sample 3"></a></td></tr></table>

### D4

**H0: A station with underground run around loop**, designer: not credited. 31 switches.

<table><tr><td valign="top"><a href="plans/D4.jpg"><img src="plans/D4.jpg" width="200" alt="AnyRail drawing of H0: A station with underground run around loop"></a></td><td valign="top"><a href="sheets/D4.svg"><img src="sheets/D4.svg" width="560" alt="schematic sheet of sample 4"></a></td></tr></table>

### D5

**N: Peter, Layout 5**, designer: Peter. 15 switches.

<table><tr><td valign="top"><a href="plans/D5.jpg"><img src="plans/D5.jpg" width="200" alt="AnyRail drawing of N: Peter, Layout 5"></a></td><td valign="top"><a href="sheets/D5.svg"><img src="sheets/D5.svg" width="560" alt="schematic sheet of sample 5"></a></td></tr></table>

### D6

**N: Jeff Partridge, Heavy Rail**, designer: Jeff Partridge. 1105 switches.

<table><tr><td valign="top"><a href="plans/D6.jpg"><img src="plans/D6.jpg" width="200" alt="AnyRail drawing of N: Jeff Partridge, Heavy Rail"></a></td><td valign="top">No sheet: the run did not finish within its time limit.</td></tr></table>

### D7

**H0: Bill Coxe, Attic floor plan**, designer: Bill Coxe. 52 switches.

<table><tr><td valign="top"><a href="plans/D7.jpg"><img src="plans/D7.jpg" width="200" alt="AnyRail drawing of H0: Bill Coxe, Attic floor plan"></a></td><td valign="top"><a href="sheets/D7.svg"><img src="sheets/D7.svg" width="560" alt="schematic sheet of sample 7"></a></td></tr></table>

### D8

**N: Bert de Vries, Two stations**, designer: Bert de Vries. 23 switches.

<table><tr><td valign="top"><a href="plans/D8.jpg"><img src="plans/D8.jpg" width="200" alt="AnyRail drawing of N: Bert de Vries, Two stations"></a></td><td valign="top"><a href="sheets/D8.svg"><img src="sheets/D8.svg" width="560" alt="schematic sheet of sample 8"></a></td></tr></table>

### D9

**H0: Dave Gann, Hudson Central Railroad**, designer: Dave Gann. 21 switches.

<table><tr><td valign="top"><a href="plans/D9.jpg"><img src="plans/D9.jpg" width="200" alt="AnyRail drawing of H0: Dave Gann, Hudson Central Railroad"></a></td><td valign="top"><a href="sheets/D9.svg"><img src="sheets/D9.svg" width="560" alt="schematic sheet of sample 9"></a></td></tr></table>

### D10

**Chicago to St. Louis**, designer: Marc Shaw. 139 switches.

<table><tr><td valign="top"><a href="plans/D10.jpg"><img src="plans/D10.jpg" width="200" alt="AnyRail drawing of Chicago to St. Louis"></a></td><td valign="top"><a href="sheets/D10.svg"><img src="sheets/D10.svg" width="560" alt="schematic sheet of sample 10"></a></td></tr></table>

### D11

**H0: Eric Consemulder, club layout**, designer: Eric Consemulder. 105 switches.

<table><tr><td valign="top"><a href="plans/D11.jpg"><img src="plans/D11.jpg" width="200" alt="AnyRail drawing of H0: Eric Consemulder, club layout"></a></td><td valign="top"><a href="sheets/D11.svg"><img src="sheets/D11.svg" width="560" alt="schematic sheet of sample 11"></a></td></tr></table>

### D12

**H0: Zoltán Rigó, Big Station**, designer: Zoltán Rigó. 48 switches.

<table><tr><td valign="top">No AnyRail drawing exported for this plan.</td><td valign="top"><a href="sheets/D12.svg"><img src="sheets/D12.svg" width="560" alt="schematic sheet of sample 12"></a></td></tr></table>

### D13

**00: Andy Hutcheon Loft layout**, designer: Andy Hutcheon. 40 switches.

<table><tr><td valign="top"><a href="plans/D13.jpg"><img src="plans/D13.jpg" width="200" alt="AnyRail drawing of 00: Andy Hutcheon Loft layout"></a></td><td valign="top"><a href="sheets/D13.svg"><img src="sheets/D13.svg" width="560" alt="schematic sheet of sample 13"></a></td></tr></table>

### D14

**H0: Michael Carver**, designer: Michael Carver. 22 switches.

<table><tr><td valign="top"><a href="plans/D14.jpg"><img src="plans/D14.jpg" width="200" alt="AnyRail drawing of H0: Michael Carver"></a></td><td valign="top"><a href="sheets/D14.svg"><img src="sheets/D14.svg" width="560" alt="schematic sheet of sample 14"></a></td></tr></table>

### D15

**H0: Rob Boone, Coal mine theme**, designer: Rob Boone. 26 switches.

<table><tr><td valign="top"><a href="plans/D15.jpg"><img src="plans/D15.jpg" width="200" alt="AnyRail drawing of H0: Rob Boone, Coal mine theme"></a></td><td valign="top"><a href="sheets/D15.svg"><img src="sheets/D15.svg" width="560" alt="schematic sheet of sample 15"></a></td></tr></table>

### D16

**H0: Peter Hanenberg, Waldeck**, designer: Peter Hanenberg. 28 switches.

<table><tr><td valign="top"><a href="plans/D16.jpg"><img src="plans/D16.jpg" width="200" alt="AnyRail drawing of H0: Peter Hanenberg, Waldeck"></a></td><td valign="top"><a href="sheets/D16.svg"><img src="sheets/D16.svg" width="560" alt="schematic sheet of sample 16"></a></td></tr></table>

### D17

**H0: Alain Lissoir, Belgian Railways**, designer: Alain Lissoir. 164 switches.

<table><tr><td valign="top"><a href="plans/D17.jpg"><img src="plans/D17.jpg" width="200" alt="AnyRail drawing of H0: Alain Lissoir, Belgian Railways"></a></td><td valign="top"><a href="sheets/D17.svg"><img src="sheets/D17.svg" width="560" alt="schematic sheet of sample 17"></a></td></tr></table>

### D18

**H0: Merv Hourigan, Newcastle Station**, designer: Merv Hourigan. 144 switches.

<table><tr><td valign="top"><a href="plans/D18.jpg"><img src="plans/D18.jpg" width="200" alt="AnyRail drawing of H0: Merv Hourigan, Newcastle Station"></a></td><td valign="top"><a href="sheets/D18.svg"><img src="sheets/D18.svg" width="560" alt="schematic sheet of sample 18"></a></td></tr></table>

### D19

**H0: John MacDonald, Real water**, designer: John MacDonald. 24 switches.

<table><tr><td valign="top"><a href="plans/D19.jpg"><img src="plans/D19.jpg" width="200" alt="AnyRail drawing of H0: John MacDonald, Real water"></a></td><td valign="top"><a href="sheets/D19.svg"><img src="sheets/D19.svg" width="560" alt="schematic sheet of sample 19"></a></td></tr></table>

### D20

**H0: Rien de Koning, Königsbach**, designer: Rien de Koning. 13 switches.

<table><tr><td valign="top"><a href="plans/D20.jpg"><img src="plans/D20.jpg" width="200" alt="AnyRail drawing of H0: Rien de Koning, Königsbach"></a></td><td valign="top"><a href="sheets/D20.svg"><img src="sheets/D20.svg" width="560" alt="schematic sheet of sample 20"></a></td></tr></table>

### D21

**H0: Jack Biermans, A large city layout**, designer: Jack Biermans. 20 switches.

<table><tr><td valign="top"><a href="plans/D21.jpg"><img src="plans/D21.jpg" width="200" alt="AnyRail drawing of H0: Jack Biermans, A large city layout"></a></td><td valign="top"><a href="sheets/D21.svg"><img src="sheets/D21.svg" width="560" alt="schematic sheet of sample 21"></a></td></tr></table>

### D22

**H0: Cambria Pine Railroad**, designer: Ray DeWeese. 32 switches.

<table><tr><td valign="top"><a href="plans/D22.jpg"><img src="plans/D22.jpg" width="200" alt="AnyRail drawing of H0: Cambria Pine Railroad"></a></td><td valign="top"><a href="sheets/D22.svg"><img src="sheets/D22.svg" width="560" alt="schematic sheet of sample 22"></a></td></tr></table>

### D23

**H0: Flats Industrial RR**, designer: Isaac Fabris. 15 switches.

<table><tr><td valign="top"><a href="plans/D23.jpg"><img src="plans/D23.jpg" width="200" alt="AnyRail drawing of H0: Flats Industrial RR"></a></td><td valign="top"><a href="sheets/D23.svg"><img src="sheets/D23.svg" width="560" alt="schematic sheet of sample 23"></a></td></tr></table>

### D24

**H0: Gateway Western Sub 6**, designer: Isaac Fabris. 65 switches.

<table><tr><td valign="top"><a href="plans/D24.jpg"><img src="plans/D24.jpg" width="200" alt="AnyRail drawing of H0: Gateway Western Sub 6"></a></td><td valign="top"><a href="sheets/D24.svg"><img src="sheets/D24.svg" width="560" alt="schematic sheet of sample 24"></a></td></tr></table>

### D25

**H0: Mike Malley, Loft Layout**, designer: Mike Malley. 54 switches.

<table><tr><td valign="top"><a href="plans/D25.jpg"><img src="plans/D25.jpg" width="200" alt="AnyRail drawing of H0: Mike Malley, Loft Layout"></a></td><td valign="top"><a href="sheets/D25.svg"><img src="sheets/D25.svg" width="560" alt="schematic sheet of sample 25"></a></td></tr></table>

### D26

**On30/On18: Russ Haigh, FC&P layout**, designer: Russ Haigh. 29 switches.

<table><tr><td valign="top"><a href="plans/D26.jpg"><img src="plans/D26.jpg" width="200" alt="AnyRail drawing of On30/On18: Russ Haigh, FC&P layout"></a></td><td valign="top"><a href="sheets/D26.svg"><img src="sheets/D26.svg" width="560" alt="schematic sheet of sample 26"></a></td></tr></table>

### D27

**N gauge 4200mm x 2000mm (13.75' x 6.5')**, designer: not credited. 50 switches.

<table><tr><td valign="top"><a href="plans/D27.jpg"><img src="plans/D27.jpg" width="200" alt="AnyRail drawing of N gauge 4200mm x 2000mm (13.75' x 6.5')"></a></td><td valign="top"><a href="sheets/D27.svg"><img src="sheets/D27.svg" width="560" alt="schematic sheet of sample 27"></a></td></tr></table>

### D28

**N: Martin de Widt, Middeldam**, designer: Martin de Widt. 42 switches.

<table><tr><td valign="top"><a href="plans/D28.jpg"><img src="plans/D28.jpg" width="200" alt="AnyRail drawing of N: Martin de Widt, Middeldam"></a></td><td valign="top"><a href="sheets/D28.svg"><img src="sheets/D28.svg" width="560" alt="schematic sheet of sample 28"></a></td></tr></table>

### D29

**N: Peter, Layout 2**, designer: Peter. 7 switches.

<table><tr><td valign="top"><a href="plans/D29.jpg"><img src="plans/D29.jpg" width="200" alt="AnyRail drawing of N: Peter, Layout 2"></a></td><td valign="top"><a href="sheets/D29.svg"><img src="sheets/D29.svg" width="560" alt="schematic sheet of sample 29"></a></td></tr></table>

### D30

**N: Allok, Radiata Springs**, designer: not credited. 12 switches.

<table><tr><td valign="top"><a href="plans/D30.jpg"><img src="plans/D30.jpg" width="200" alt="AnyRail drawing of N: Allok, Radiata Springs"></a></td><td valign="top"><a href="sheets/D30.svg"><img src="sheets/D30.svg" width="560" alt="schematic sheet of sample 30"></a></td></tr></table>

### D31

**On3: Cambria Pine Railroad**, designer: Ray DeWeese. 24 switches.

<table><tr><td valign="top"><a href="plans/D31.jpg"><img src="plans/D31.jpg" width="200" alt="AnyRail drawing of On3: Cambria Pine Railroad"></a></td><td valign="top"><a href="sheets/D31.svg"><img src="sheets/D31.svg" width="560" alt="schematic sheet of sample 31"></a></td></tr></table>

### D32

**H0: Russ Haigh, On30 SSW layout**, designer: Russ Haigh. 19 switches.

<table><tr><td valign="top"><a href="plans/D32.jpg"><img src="plans/D32.jpg" width="200" alt="AnyRail drawing of H0: Russ Haigh, On30 SSW layout"></a></td><td valign="top"><a href="sheets/D32.svg"><img src="sheets/D32.svg" width="560" alt="schematic sheet of sample 32"></a></td></tr></table>

### D33

**Passau**, designer: Chaz. 3 switches.

<table><tr><td valign="top"><a href="plans/D33.jpg"><img src="plans/D33.jpg" width="200" alt="AnyRail drawing of Passau"></a></td><td valign="top"><a href="sheets/D33.svg"><img src="sheets/D33.svg" width="560" alt="schematic sheet of sample 33"></a></td></tr></table>

### D34

**Schwarzenberg**, designer: Christian. 92 switches.

<table><tr><td valign="top"><a href="plans/D34.jpg"><img src="plans/D34.jpg" width="200" alt="AnyRail drawing of Schwarzenberg"></a></td><td valign="top"><a href="sheets/D34.svg"><img src="sheets/D34.svg" width="560" alt="schematic sheet of sample 34"></a></td></tr></table>

### D35

**Christmas layout**, designer: Rich Erickson. 10 switches.

<table><tr><td valign="top"><a href="plans/D35.jpg"><img src="plans/D35.jpg" width="200" alt="AnyRail drawing of Christmas layout"></a></td><td valign="top"><a href="sheets/D35.svg"><img src="sheets/D35.svg" width="560" alt="schematic sheet of sample 35"></a></td></tr></table>

### D36

**Trix Express**, designer: Herman. 22 switches.

<table><tr><td valign="top"><a href="plans/D36.jpg"><img src="plans/D36.jpg" width="200" alt="AnyRail drawing of Trix Express"></a></td><td valign="top"><a href="sheets/D36.svg"><img src="sheets/D36.svg" width="560" alt="schematic sheet of sample 36"></a></td></tr></table>

### D37

**Z: Chris Manvell, Exhibition layout**, designer: Chris Manvell. 40 switches.

<table><tr><td valign="top"><a href="plans/D37.jpg"><img src="plans/D37.jpg" width="200" alt="AnyRail drawing of Z: Chris Manvell, Exhibition layout"></a></td><td valign="top"><a href="sheets/D37.svg"><img src="sheets/D37.svg" width="560" alt="schematic sheet of sample 37"></a></td></tr></table>

### D38

**Z: Chaz, 69th Street Philadelphia**, designer: Chaz. 69 switches.

<table><tr><td valign="top"><a href="plans/D38.jpg"><img src="plans/D38.jpg" width="200" alt="AnyRail drawing of Z: Chaz, 69th Street Philadelphia"></a></td><td valign="top"><a href="sheets/D38.svg"><img src="sheets/D38.svg" width="560" alt="schematic sheet of sample 38"></a></td></tr></table>
