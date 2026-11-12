# Photos

The crop and the lettering read both expect the same kind of photo. Take every photo the same way and the first batch needs few fixes.

## Set-up

1. **Side-on, at about car height.** Hold the phone level, square to the car, with its lens at the height of the car's side. A photo taken from above or at an angle makes the car look tilted and the lettering small.
2. **A short piece of track.** Put the car on a few inches of track beyond each coupler. The crop ends at the track and keeps about four ties past each coupler.
3. **A plain light backdrop.** A sheet of grey or off-white card behind the car. No creases, tape or objects. The crop finds the car by how it differs from the backdrop.
4. **The darker strip below the track is ignored.** The table or base under the track may show at the bottom of the frame. The crop stops at the track.
5. **The whole car, with room at each end.** Both couplers in frame, and some backdrop beyond them. Keep the car and its track in the lower two thirds of the frame, with plain backdrop above the roof. The search for the car covers the band from about a third to nine tenths of the way down the photo.
6. **Steady and sharp.** Rest the phone or use a timer. A photo whose sharpness score is under `review.blur_threshold` (600 by default) is flagged `blurry`. Lettering on a sharp, large photo reads far better: in the tests a hopper read correctly at 2400 px wide and not at 1200 px.
7. **The same set-up each time.** Same backdrop, same distance, same light. Start with five to ten cars of one type.

Avoid shadows across the lettering, glare on the car side, and a backdrop that matches the car's colour.

## File names and folders

Put the photos in `photos/incoming/`. JPG, PNG, HEIC, HEIF and TIFF files are read. Phone names such as `IMG_1234.jpg` are fine. A photo already in a batch or in the fleet is not read again. If a JPG and a converted copy of it share a name apart from the ending, only one is used.

## Locomotives

Start the file name with `loco_` or `engine_` (for example `loco_NW1776.jpg`) and the photo starts as a locomotive. Every other photo starts as a car, and `cards kind` switches it later.

A locomotive photo is cut round the locomotive over an even grey backdrop instead of the freight-car crop, so it needs a plain backdrop and the track under it, as for a car. See `locos.md`.

For a consist of two units, photograph each unit on its own, the two facing opposite ways, so the pair looks right side by side.

## HEIC

- On a Mac, HEIC photos from an iPhone convert with the built-in `sips` tool. Nothing to install.
- On Linux and Windows, run `pip install pillow-heif` in the card folder's environment, or convert the photos to JPG first. Without either, the photo is refused with a message saying so.

The photo is turned upright from its orientation tag when it is converted, so a phone held sideways is fine.
