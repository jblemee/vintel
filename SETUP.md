# Vintel Setup

This document describes the settings available in the Vintel application.

## Settings Dialog

The settings dialog has three panes: *Quick Setup*, *Jumpbridges*, and *Chat Channels*.

The *Jumpbridges* pane allows you to specify a source for jumpbridges to be 
rendered on the maps.   You may specify either a DOTLAN jumpbridge list id or an URL to
a file containing your own jumpbridge list.   More details on the format of the file
can be seen in the application pane or in *Quick Setup* below.

The *Chat Channels* pane allows you to specify EVE chat channels to monitor for
intelligence reports.   You must keep this chat channel open in a tab in game
and have *Log Chat to File* selected in EVE Settings > Chat.   Vintel monitors and
processes these log files on your local disk.

The *Quick Setup* 

## Quick Setup

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
   bottom of the DOTLAN universe page.  Vintel also recognizes the custom region
   providencecatch.

This is what the Vintel defaults would look like as a quick configuration entry:

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

## Other Menu Settings

### File > Clear Cache

If you notice any weirdness with maps or avatars, you may try flushing the Vintel
cache.  Avatars and maps will be redownloaded.

### Chat > Show Chat

Hide the chat history on the right side of the screen

### Chat > Show Chat Avatars

Do not show character portraits in the chat history.   Unfortunately selecting this
doesn't yet make the chat window more compact.

### Sound > Activate Sound

This should be checked to enable sound in Vintel.

## Sound > Sound Setup ...

Test the sound configuration.

## Sound > Spoken Notifications

Doesn't work on Windows 10, what does it do?

## Region

Select a region from the quick region shortcuts configured in *Quick Settings*

## Region > Other Region

Select from a list of all known EVE regions.

## Region > Custom Region ...

Displays a freeform text box to enter a standard or custom region by name.

## K.O.S.

Activate some of the Kill On Sight processing and warnings.

## Window > Always On Top

Keep this window above all other windows.

## Window > Frameless Main Window

Remove OS decorations from the window: titlebar, menubar, ...    Once activated a *Restore Frame* button will
be available in the upper left corner of the screen.  Click that to restore the window decorations.

## Window > Transparency

Set the window opacity.

