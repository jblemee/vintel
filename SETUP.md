# Vintel Setup

This document describes the settings available in the Vintel application.

## Quick Config

The first pane of the settings allows you to paste a quick configuration JSON
blob that may be provided by your alliance.

1. **dotlan_jb_id** The id of a jumpbridge list from DOTLAN.  Include just the id,
   i.e. from ht<i></i>tp://evemaps.dotlan.net/bridges/**XXXXxxxx** use the XXXXxxxx
2. **jumpbridge_url** A url to a file containing your bridge list.   Each line
   in the file should contain two systems separated by a `<->`.   i.e.
   `HED-GP <-> 36N-HZ`
3. **channels** A JSON list of the channels to be monitored.
4. **kos_url** A URL to your alliances KOS server.
5. **region_name** The default region to load on launch.  Later, the application will
   remember the last region viewed and load that when you restart.
6. **quick_regions** The regions listed here are automatically added to the
   application's *Region* menu.  Any name starting with a dash will be interpreted
   as a separator and will draw a horizontal line between entries.  Each entry
   should have a **label** field which is how it will appear in the menu.  Each
   may also have a **region** field which can be used to override the region name
   used when looking up this system on DOTLAN if the label is not an exact match
   (spaces will be automatically converted to underscores).

   The **region** should match a DOTLAN url - i.e. ht<i></i>tp://evemaps.dotlan.net/map/**Catch**.
   The **region** can also be one of the special or combined maps listed at the
   bottom of the DOTLAN universe page.


```
{
  "dotlan_jb_id": "",
  "jumpbridge_url": "",
  "channels": [
    "TheCitadel",
    "North Provi Intel",
    "North Catch Intel",
    "North Querious Intel"
  ],
  "kos_url": "http://kos.cva-eve.org/api/",
  "region_name": "Catch",
  "quick_regions": [
    {"label": "Catch"},
    {"label": "Providence"},
    {"label": "Querious"},
    {"label": "---"},
    {"label": "Provi / Catch", "region": "providencecatch"},
    {"label": "Provi / Catch (compact)", "region": "Providence-catch"}
  ]
}
```
